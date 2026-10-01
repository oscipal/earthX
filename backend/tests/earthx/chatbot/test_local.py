"""The local model adapter with a stub runtime: no model file, no llama-cpp-python needed."""

from __future__ import annotations

import json
from typing import Any

import pytest

from earthx.chatbot.dialogue import reply
from earthx.chatbot.llm import ModelError
from earthx.chatbot.local import NO_THINK, LocalModel
from earthx.chatbot.tools import TOOL_SPECS
from tests.earthx.chatbot import test_tools as synthetic_api

pytestmark = pytest.mark.anyio


class StubRuntime:
    """Answers with the next text of a script and records each request."""

    def __init__(self, *texts: str, finish_reason: str = "stop") -> None:
        self._texts = list(texts)
        self._finish_reason = finish_reason
        self.requests: list[dict[str, Any]] = []

    def create_chat_completion(self, **kwargs: Any) -> dict[str, Any]:
        self.requests.append(kwargs)
        text = self._texts.pop(0) if len(self._texts) > 1 else self._texts[0]
        return {"choices": [{"message": {"role": "assistant", "content": text}, "finish_reason": self._finish_reason}]}


class BrokenRuntime:
    def create_chat_completion(self, **kwargs: Any) -> Any:
        raise RuntimeError("llama_decode returned -1")


async def ask(model: LocalModel, *, allow_tools: bool = True, messages: Any = None) -> dict[str, Any]:
    return await model.create(
        system="be brief",
        messages=messages or [{"role": "user", "content": "radar?"}],
        tools=TOOL_SPECS,
        allow_tools=allow_tools,
    )


async def test_plain_text_is_an_answer_and_the_reasoning_block_is_dropped() -> None:
    runtime = StubRuntime("<think>hm</think>\nWhich area?")
    message = await ask(LocalModel(runtime))
    assert message == {
        "role": "assistant",
        "content": [{"type": "text", "text": "Which area?"}],
        "stop_reason": "end_turn",
    }
    request = runtime.requests[0]
    assert request["messages"][0] == {"role": "system", "content": f"be brief\n{NO_THINK}"}
    assert [t["function"]["name"] for t in request["tools"]] == [s["name"] for s in TOOL_SPECS]
    assert request["tools"][0]["function"]["parameters"] == TOOL_SPECS[0]["input_schema"]


async def test_tool_calls_become_tool_use_blocks() -> None:
    text = (
        "Let me look.\n"
        '<tool_call>\n{"name": "search_collections", "arguments": {"query": "radar"}}\n</tool_call>\n'
        '<tool_call>{"name": "get_collection", "arguments": {"collection_id": "x"}}</tool_call>'
    )
    message = await ask(LocalModel(StubRuntime(text)))
    assert message["stop_reason"] == "tool_use"
    assert message["content"][0] == {"type": "text", "text": "Let me look."}
    uses = message["content"][1:]
    assert [(u["name"], u["input"]) for u in uses] == [
        ("search_collections", {"query": "radar"}),
        ("get_collection", {"collection_id": "x"}),
    ]
    assert len({u["id"] for u in uses}) == 2


@pytest.mark.parametrize("raw", ["not json", '["a list"]', '{"arguments": {}}'])
async def test_a_broken_tool_call_names_no_tool(raw: str) -> None:
    message = await ask(LocalModel(StubRuntime(f"<tool_call>{raw}</tool_call>")))
    [use] = message["content"]
    assert use["type"] == "tool_use" and use["name"] is None


async def test_without_tools_allowed_none_are_offered_and_tags_are_not_calls() -> None:
    runtime = StubRuntime('Done. <tool_call>{"name": "search_collections", "arguments": {}}</tool_call>')
    message = await ask(LocalModel(runtime), allow_tools=False)
    assert "tools" not in runtime.requests[0]
    assert message["stop_reason"] == "end_turn"
    assert message["content"] == [{"type": "text", "text": "Done."}]


async def test_a_cut_answer_reports_max_tokens() -> None:
    message = await ask(LocalModel(StubRuntime("Sentinel-1 is", finish_reason="length")))
    assert message["stop_reason"] == "max_tokens"


async def test_the_transcript_is_translated_to_chat_messages() -> None:
    runtime = StubRuntime("ok")
    transcript = [
        {"role": "user", "content": "radar?"},
        {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "", "signature": "x"},
                {"type": "text", "text": "Looking."},
                {"type": "tool_use", "id": "call_1", "name": "search_collections", "input": {"query": "radar"}},
            ],
        },
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "call_1", "content": '{"collections": []}'}],
        },
    ]
    await ask(LocalModel(runtime), messages=transcript)
    chat = runtime.requests[0]["messages"][1:]
    assert chat[0] == {"role": "user", "content": "radar?"}
    assert chat[1]["role"] == "assistant" and chat[1]["content"] == "Looking."
    [call] = chat[1]["tool_calls"]
    assert call["id"] == "call_1" and json.loads(call["function"]["arguments"]) == {"query": "radar"}
    assert chat[2] == {"role": "tool", "tool_call_id": "call_1", "content": '{"collections": []}'}


async def test_a_failing_runtime_is_a_model_error() -> None:
    with pytest.raises(ModelError, match="RuntimeError"):
        await ask(LocalModel(BrokenRuntime()))


@pytest.mark.parametrize("answer", [{}, {"choices": []}, {"choices": [{"message": {"content": 3}}]}])
async def test_an_unusable_completion_is_a_model_error(answer: Any) -> None:
    class Odd:
        def create_chat_completion(self, **kwargs: Any) -> Any:
            return answer

    with pytest.raises(ModelError):
        await ask(LocalModel(Odd()))


async def test_a_whole_turn_runs_the_read_tools_through_the_local_model() -> None:
    runtime = StubRuntime(
        '<tool_call>{"name": "search_collections", "arguments": {"query": "radar"}}</tool_call>',
        "synth-radar-alps fits.",
    )
    tools, gateway = synthetic_api.build()
    async with gateway:
        result = await reply(LocalModel(runtime), tools, [{"role": "user", "content": "radar?"}])
    assert result.text == "synth-radar-alps fits."
    tool_message = runtime.requests[1]["messages"][-1]
    assert tool_message["role"] == "tool" and "synth-radar-alps" in tool_message["content"]


def test_without_the_runtime_installed_loading_is_a_model_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    real_import = builtins.__import__

    def no_llama(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "llama_cpp":
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_llama)
    with pytest.raises(ModelError, match="llama-cpp-python"):
        LocalModel.from_file("model.gguf")
