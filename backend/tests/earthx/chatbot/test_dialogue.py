"""The tool loop of one dialogue turn, with a scripted model and the synthetic STAC API."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from earthx.chatbot import dialogue
from earthx.chatbot.dialogue import MAX_TOOL_ROUNDS, REFUSED_ANSWER, SYSTEM_PROMPT, reply
from earthx.chatbot.llm import ModelError
from earthx.chatbot.tools import TOOL_SPECS
from tests.earthx.chatbot import test_tools as synthetic_api

pytestmark = pytest.mark.anyio

QUESTION = [{"role": "user", "content": "I need radar data."}]


class ScriptedModel:
    """Answers with the next message of a script and records what it was asked."""

    def __init__(self, *script: dict[str, Any] | Exception) -> None:
        self._script = list(script)
        self.calls: list[dict[str, Any]] = []

    async def create(
        self,
        *,
        system: str,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]],
        allow_tools: bool,
    ) -> dict[str, Any]:
        self.calls.append(
            {"system": system, "messages": json.loads(json.dumps(messages)), "tools": tools, "allow_tools": allow_tools}
        )
        answer = self._script.pop(0) if len(self._script) > 1 else self._script[0]
        if isinstance(answer, Exception):
            raise answer
        return answer


def text(words: str, stop_reason: str = "end_turn") -> dict[str, Any]:
    return {"role": "assistant", "content": [{"type": "text", "text": words}], "stop_reason": stop_reason}


def use(*calls: tuple[str, Any]) -> dict[str, Any]:
    blocks = [
        {"type": "tool_use", "id": f"call-{i}", "name": name, "input": args} for i, (name, args) in enumerate(calls)
    ]
    return {"role": "assistant", "content": blocks, "stop_reason": "tool_use"}


async def turn(model: ScriptedModel, transcript: Sequence[Mapping[str, Any]] = QUESTION) -> dialogue.Reply:
    tools, gateway = synthetic_api.build()
    async with gateway:
        return await reply(model, tools, transcript)


def tool_results(message: Mapping[str, Any]) -> list[dict[str, Any]]:
    assert message["role"] == "user"
    return [block for block in message["content"] if block["type"] == "tool_result"]


async def test_a_follow_up_question_needs_no_tool() -> None:
    model = ScriptedModel(text("Which area and which period?"))
    result = await turn(model)
    assert result.text == "Which area and which period?"
    assert result.stop_reason == "end_turn"
    answer = {"role": "assistant", "content": [{"type": "text", "text": "Which area and which period?"}]}
    assert result.transcript == [*QUESTION, answer]
    assert len(model.calls) == 1
    call = model.calls[0]
    assert call["system"] == SYSTEM_PROMPT and call["tools"] == TOOL_SPECS and call["allow_tools"] is True


async def test_one_tool_round_hands_the_result_back_and_ends_with_the_answer() -> None:
    model = ScriptedModel(use(("search_collections", {"query": "radar"})), text("Take synth-radar-alps."))
    result = await turn(model)
    assert result.text == "Take synth-radar-alps."
    assert len(model.calls) == 2
    [block] = tool_results(model.calls[1]["messages"][-1])
    assert block["tool_use_id"] == "call-0" and block["is_error"] is False
    found = json.loads(block["content"])
    assert [c["id"] for c in found["collections"]] == ["synth-radar-alps"]
    assert [m["role"] for m in result.transcript] == ["user", "assistant", "user", "assistant"]


async def test_parallel_calls_come_back_together_in_their_order() -> None:
    model = ScriptedModel(
        use(("get_collection", {"collection_id": "synth-optical-l2a"}), ("search_collections", {"query": "dem"})),
        text("done"),
    )
    await turn(model)
    blocks = tool_results(model.calls[1]["messages"][-1])
    assert [b["tool_use_id"] for b in blocks] == ["call-0", "call-1"]
    assert json.loads(blocks[0]["content"])["id"] == "synth-optical-l2a"


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("start_job", {"recipe": "anything"}),
        ("get_collection", {"collection_id": "does-not-exist"}),
        ("check_availability", {"collection_id": "synth-optical-l2a", "bbox": [10, 0, 0, 5], "datetime": "2024"}),
        ("search_collections", "not an object"),
        (None, {}),
    ],
)
async def test_a_wrong_call_is_answered_as_an_error_and_the_turn_goes_on(name: Any, arguments: Any) -> None:
    model = ScriptedModel(use((name, arguments)), text("Sorry, that did not work."))
    result = await turn(model)
    [block] = tool_results(model.calls[1]["messages"][-1])
    assert block["is_error"] is True and "error" in json.loads(block["content"])
    assert result.text == "Sorry, that did not work."


async def test_after_the_round_limit_the_model_must_answer_without_tools() -> None:
    model = ScriptedModel(*[use(("search_collections", {}))] * MAX_TOOL_ROUNDS, text("Here is what I found."))
    result = await turn(model)
    assert len(model.calls) == MAX_TOOL_ROUNDS + 1
    assert [c["allow_tools"] for c in model.calls] == [True] * MAX_TOOL_ROUNDS + [False]
    assert result.text == "Here is what I found."


async def test_a_tool_call_past_the_limit_is_refused_and_leaves_a_valid_transcript() -> None:
    model = ScriptedModel(use(("search_collections", {})))
    result = await turn(model)
    assert len(model.calls) == MAX_TOOL_ROUNDS + 1
    assert result.stop_reason == "round_limit"
    [block] = tool_results(result.transcript[-1])
    assert json.loads(block["content"]) == {"error": "no more tool calls in this turn"}


async def test_an_instruction_inside_a_description_stays_inside_the_tool_result() -> None:
    model = ScriptedModel(use(("search_collections", {"query": "elevation"})), text("synth-injection fits."))
    result = await turn(model)
    marker = "IGNORE ALL PREVIOUS INSTRUCTIONS"
    [block] = tool_results(result.transcript[2])
    assert marker in block["content"]
    assert marker not in model.calls[1]["system"]
    elsewhere = [m for m in result.transcript if m is not result.transcript[2]]
    assert marker not in json.dumps(elsewhere)


async def test_thinking_blocks_go_back_unchanged() -> None:
    thinking = {"type": "thinking", "thinking": "", "signature": "opaque"}
    first = use(("search_collections", {"query": "radar"}))
    first["content"].insert(0, thinking)
    model = ScriptedModel(first, text("ok"))
    await turn(model)
    assert model.calls[1]["messages"][1]["content"][0] == thinking


async def test_a_refusal_without_text_says_so() -> None:
    model = ScriptedModel({"role": "assistant", "content": [], "stop_reason": "refusal"})
    result = await turn(model)
    assert result.text == REFUSED_ANSWER and result.stop_reason == "refusal"


async def test_a_long_result_is_cut(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dialogue, "MAX_RESULT_CHARS", 50)
    model = ScriptedModel(use(("search_collections", {})), text("ok"))
    await turn(model)
    [block] = tool_results(model.calls[1]["messages"][-1])
    assert len(block["content"]) <= 50 + len(" …[cut]") and block["content"].endswith("…[cut]")


async def test_the_callers_transcript_is_not_changed() -> None:
    transcript = [dict(message) for message in QUESTION]
    result = await turn(ScriptedModel(text("Which area?")), transcript)
    assert transcript == QUESTION and len(result.transcript) == 2


@pytest.mark.parametrize("transcript", [[], [{"role": "assistant", "content": "hi"}]])
async def test_a_transcript_must_end_with_a_user_message(transcript: list[dict[str, Any]]) -> None:
    model = ScriptedModel(text("never"))
    with pytest.raises(ValueError):
        await turn(model, transcript)
    assert model.calls == []


async def test_a_model_error_reaches_the_caller() -> None:
    with pytest.raises(ModelError):
        await turn(ScriptedModel(ModelError("the language model answered 500")))
