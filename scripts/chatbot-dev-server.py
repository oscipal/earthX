"""Throwaway local server so the chatbot read tools can be clicked, not just curled.

NOT part of the M7a plan (docs/plans/m7a-chatbot-lesewerkzeuge.md §5 keeps a
`POST /chat` route out until M6 settles login and the LLM contract) and not run by
CI or any test. It exists only so Víctor can look at the three tools from the
frontend while experimenting on this branch (24.09.2026/25.09.2026 conversation).
Lives only on the branch dev/chatbot-playground, which is never merged into main.

`/call` wraps `earthx.chatbot.call_tool` directly (one tool call per request);
`/chat` runs one dialogue turn (`earthx.chatbot.reply`) with the local GGUF model
from `EARTHX_CHATBOT_LOCAL_MODEL` (06.10.2026 conversation). It lives outside
`backend/earthx` on purpose, so `earthx.chatbot` itself stays exactly what the plan
describes: read tools, the dialogue and a CLI, nothing that serves HTTP.

Run from the repo root, with the backend on the path:

    PYTHONPATH=backend .venv/Scripts/python.exe scripts/chatbot-dev-server.py

The STAC root is `EARTHX_CHATBOT_STAC_URL` (see earthx.chatbot.__main__); the
gateway's allowlist policy is unchanged, so only that one https host is ever
reached (plan m7a F5) — a public source by default, never anything local.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from fastapi import FastAPI  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from earthx.chatbot import TOOL_SPECS, CatalogTools, ModelError, call_tool, reply  # noqa: E402
from earthx.chatbot.local import LocalModel  # noqa: E402
from earthx.gateway import Gateway, host_of, policy_from_env  # noqa: E402

DEFAULT_STAC_URL = "https://earth-search.aws.element84.com/v1"
STAC_URL = os.environ.get("EARTHX_CHATBOT_STAC_URL", DEFAULT_STAC_URL)
# `/chat` runs the local GGUF model only (no Anthropic key in this dev server);
# EARTHX_CHATBOT_GPU_LAYERS as in earthx.chatbot.__main__.
LOCAL_MODEL = os.environ.get("EARTHX_CHATBOT_LOCAL_MODEL", "")
GPU_LAYERS = int(os.environ.get("EARTHX_CHATBOT_GPU_LAYERS", "0"))
PORT = int(os.environ.get("EARTHX_CHATBOT_DEVSERVER_PORT", "8010"))

# `policy_from_env` reads EARTHX_ALLOWED_HOSTS; this dev server always talks to
# exactly the one STAC root above, so the allowlist is derived from it rather
# than left to whatever the shell happens to export.
_ALLOWED = {"EARTHX_ALLOWED_HOSTS": host_of(STAC_URL)}

app = FastAPI(title="earthx chatbot dev server (throwaway, not for CI)")


class CallBody(BaseModel):
    tool: str
    arguments: dict[str, Any] = {}


class ChatBody(BaseModel):
    # The whole transcript so far, ending with the new user message; the server
    # keeps nothing between requests (dialogue.reply is stateless).
    messages: list[dict[str, Any]]


_model: LocalModel | None = None
# One llama.cpp context serves one completion at a time.
_model_lock = asyncio.Lock()


@app.get("/tools")
def list_tools() -> list[dict[str, Any]]:
    return list(TOOL_SPECS)


@app.post("/call")
async def call(body: CallBody) -> dict[str, Any]:
    async with Gateway(policy_from_env(_ALLOWED)) as gateway:
        tools = CatalogTools(gateway, STAC_URL)
        return await call_tool(tools, body.tool, body.arguments)


@app.post("/chat")
async def chat(body: ChatBody) -> dict[str, Any]:
    global _model
    if not LOCAL_MODEL:
        return {"error": "set EARTHX_CHATBOT_LOCAL_MODEL to a GGUF file before starting this server"}
    async with _model_lock:
        try:
            if _model is None:
                _model = await asyncio.to_thread(LocalModel.from_file, LOCAL_MODEL, gpu_layers=GPU_LAYERS)
            async with Gateway(policy_from_env(_ALLOWED)) as gateway:
                answer = await reply(_model, CatalogTools(gateway, STAC_URL), body.messages)
        except (ModelError, ValueError) as error:
            return {"error": str(error)}
    return {"text": answer.text, "messages": answer.transcript, "stop_reason": answer.stop_reason}


if __name__ == "__main__":
    import uvicorn

    print(f"chatbot dev server (throwaway): http://127.0.0.1:{PORT}  ->  STAC root {STAC_URL}")
    print(f"local model for /chat: {LOCAL_MODEL or '(none)'}, GPU layers {GPU_LAYERS}")
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
