"""A local open-weight model behind the same ``ChatModel`` seam, run in-process.

The model is a GGUF file on disk, run by ``llama-cpp-python``. Nothing here opens a
connection: the file is loaded by path, never fetched, so the gateway rules have
nothing to clear (KLAERUNGEN B8). ``llama-cpp-python`` is an optional local
dependency and imported only when a local model is asked for.

The dialogue speaks the Messages API's shape (content blocks, ``tool_use``,
``tool_result``). This module translates it to the chat format the model's own
template reads, and the model's ``<tool_call>`` output back into ``tool_use``
blocks. The tag format is the one Qwen's template writes and asks for.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from earthx.chatbot.llm import ModelError

MAX_TOKENS = 4096
CONTEXT_TOKENS = 16384
# Qwen3's switch for an answer without a reasoning block, much faster on a CPU.
NO_THINK = "/no_think"

_TOOL_CALL = re.compile(r"<tool_call>\s*(.*?)\s*</tool_call>", re.DOTALL)
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)


class Completer(Protocol):
    """The part of ``llama_cpp.Llama`` used here."""

    def create_chat_completion(self, **kwargs: Any) -> Any: ...


class LocalModel:
    """``ChatModel`` over a local completer such as ``llama_cpp.Llama``."""

    def __init__(self, completer: Completer, *, max_tokens: int = MAX_TOKENS) -> None:
        self._completer = completer
        self._max_tokens = max_tokens
        self._ids = itertools.count(1)

    @classmethod
    def from_file(cls, path: str, *, gpu_layers: int = 0) -> LocalModel:
        """Load a GGUF file; ``gpu_layers`` layers go to the GPU if the runtime was built with one, -1 for all."""
        try:
            from llama_cpp import Llama
        except ImportError:
            raise ModelError("a local model needs llama-cpp-python in this environment") from None
        try:
            return cls(Llama(model_path=path, n_ctx=CONTEXT_TOKENS, n_gpu_layers=gpu_layers, verbose=False))
        except (OSError, ValueError) as error:
            raise ModelError(f"the local model could not be loaded: {type(error).__name__}") from None

    async def create(
        self,
        *,
        system: str,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]],
        allow_tools: bool,
    ) -> dict[str, Any]:
        request: dict[str, Any] = {
            "messages": [{"role": "system", "content": f"{system}\n{NO_THINK}"}, *_chat_messages(messages)],
            "max_tokens": self._max_tokens,
        }
        if allow_tools:
            request["tools"] = [_function(tool) for tool in tools]
        try:
            # The model runs on this machine's CPU; a thread keeps the event loop free.
            completion = await asyncio.to_thread(self._completer.create_chat_completion, **request)
            choice = completion["choices"][0]
            text = choice["message"].get("content") or ""
            finish_reason = choice.get("finish_reason")
        except Exception as error:  # any failure of the local runtime is a model error
            raise ModelError(f"the local model failed: {type(error).__name__}") from None
        if not isinstance(text, str):
            raise ModelError("the local model answered without text")
        return self._message(text, allow_tools, finish_reason)

    def _message(self, text: str, allow_tools: bool, finish_reason: object) -> dict[str, Any]:
        text = _THINK.sub("", text)
        calls = _TOOL_CALL.findall(text) if allow_tools else []
        prose = _TOOL_CALL.sub("", text).strip()
        content: list[dict[str, Any]] = [{"type": "text", "text": prose}] if prose else []
        content.extend(self._tool_use(raw) for raw in calls)
        if calls:
            stop_reason = "tool_use"
        elif finish_reason == "length":
            stop_reason = "max_tokens"
        else:
            stop_reason = "end_turn"
        return {"role": "assistant", "content": content, "stop_reason": stop_reason}

    def _tool_use(self, raw: str) -> dict[str, Any]:
        """A ``tool_use`` block; a call that is not valid JSON names no tool and so comes back as an error."""
        try:
            call = json.loads(raw)
        except ValueError:
            call = None
        name = call.get("name") if isinstance(call, dict) else None
        arguments = call.get("arguments", {}) if isinstance(call, dict) else {}
        return {"type": "tool_use", "id": f"call_{next(self._ids)}", "name": name, "input": arguments}


def _function(tool: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "parameters": tool["input_schema"],
        },
    }


def _chat_messages(messages: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Messages API transcript to chat messages: tool results become ``tool`` messages."""
    chat: list[dict[str, Any]] = []
    for message in messages:
        role, content = message.get("role"), message.get("content")
        if isinstance(content, str):
            chat.append({"role": role, "content": content})
            continue
        blocks = [block for block in content or [] if isinstance(block, Mapping)]
        text = "\n".join(b["text"] for b in blocks if b.get("type") == "text" and isinstance(b.get("text"), str))
        if role == "assistant":
            calls = [
                {
                    "id": b.get("id"),
                    "type": "function",
                    "function": {"name": b.get("name"), "arguments": json.dumps(b.get("input"), ensure_ascii=False)},
                }
                for b in blocks
                if b.get("type") == "tool_use"
            ]
            chat.append({"role": "assistant", "content": text, **({"tool_calls": calls} if calls else {})})
            continue
        for block in blocks:
            if block.get("type") == "tool_result":
                chat.append({"role": "tool", "tool_call_id": block.get("tool_use_id"), "content": block.get("content")})
        if text:
            chat.append({"role": "user", "content": text})
    return chat
