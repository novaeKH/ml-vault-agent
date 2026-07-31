from __future__ import annotations

import asyncio
import json
import threading
import uuid
from collections.abc import Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import (
    PROJECT_ROOT,
    Settings,
    discover_vaults,
    load_settings,
    save_settings,
    validate_vault_path,
)
from app.index import HybridIndex
from app.ollama_client import OllamaClient, OllamaError
from app.prompts import build_context, system_prompt


Mode = Literal["chat", "tutor", "interviewer", "practice", "code"]


class ChatRequest(BaseModel):
    session_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    message: str = Field(min_length=1, max_length=20_000)
    mode: Mode = "chat"


class ResetRequest(BaseModel):
    session_id: str


class ReindexRequest(BaseModel):
    force: bool = False


class SettingsUpdate(BaseModel):
    vault_path: str | None = None
    ollama_url: str | None = None
    chat_model: str | None = None
    embedding_model: str | None = None
    top_k: int | None = None
    temperature: float | None = None
    context_chars: int | None = None
    history_messages: int | None = None


class RuntimeState:
    def __init__(self) -> None:
        self.settings = load_settings()
        self.index = HybridIndex()
        self.sessions: dict[str, list[dict[str, str]]] = {}
        self.lock = threading.RLock()
        self.indexing = False
        self.index_result: dict | None = None
        self.index_error = ""

    def client(self) -> OllamaClient:
        return OllamaClient(self.settings.ollama_url)

    def history(self, session_id: str) -> list[dict[str, str]]:
        with self.lock:
            return list(self.sessions.get(session_id, []))

    def append(self, session_id: str, role: str, content: str) -> None:
        with self.lock:
            history = self.sessions.setdefault(session_id, [])
            history.append({"role": role, "content": content})
            if len(history) > 40:
                del history[:-40]

    def reset(self, session_id: str) -> None:
        with self.lock:
            self.sessions.pop(session_id, None)


state = RuntimeState()


async def _perform_reindex(force: bool) -> None:
    with state.lock:
        if state.indexing:
            return
        state.indexing = True
        state.index_error = ""
    try:
        settings = state.settings
        client = state.client()
        embedder = client if client.available() else None
        result = await asyncio.to_thread(
            state.index.reindex,
            settings,
            embedder,
            force=force,
        )
        with state.lock:
            state.index_result = result
    except Exception as error:  # surfaced in the status panel
        with state.lock:
            state.index_error = str(error)
    finally:
        with state.lock:
            state.indexing = False


@asynccontextmanager
async def lifespan(_: FastAPI):
    if state.settings.vault_path:
        asyncio.create_task(_perform_reindex(force=False))
    yield


app = FastAPI(
    title="ML Vault Agent",
    version="0.2.0",
    docs_url="/api/docs",
    redoc_url=None,
    lifespan=lifespan,
)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "read_only_vault": True}


@app.get("/api/status")
def status() -> dict:
    settings = state.settings
    client = state.client()
    try:
        models = client.list_models()
        ollama_available = True
        ollama_error = ""
    except (OllamaError, ValueError, json.JSONDecodeError) as error:
        models = []
        ollama_available = False
        ollama_error = str(error)
    index_stats = state.index.stats()
    with state.lock:
        index_runtime = {
            "running": state.indexing,
            "last_result": state.index_result,
            "error": state.index_error,
        }
    vault_path = Path(settings.vault_path) if settings.vault_path else None
    return {
        "configured": bool(vault_path and vault_path.is_dir()),
        "vault_name": vault_path.name if vault_path else "",
        "vault_path": settings.vault_path,
        "vault_read_only": True,
        "candidates": discover_vaults(),
        "settings": settings.public_dict(),
        "ollama": {
            "available": ollama_available,
            "models": models,
            "error": ollama_error,
            "chat_model_ready": settings.chat_model in models,
            "embedding_model_ready": settings.embedding_model in models,
        },
        "index": index_stats,
        "indexing": index_runtime,
    }


@app.put("/api/settings")
async def update_settings(update: SettingsUpdate) -> dict:
    current = state.settings.public_dict()
    incoming = update.model_dump(exclude_none=True)
    if "vault_path" in incoming:
        try:
            incoming["vault_path"] = validate_vault_path(incoming["vault_path"])
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    previous_vault = current["vault_path"]
    previous_embedding = current["embedding_model"]
    current.update(incoming)
    try:
        settings = Settings(**current).normalized()
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    with state.lock:
        state.settings = save_settings(settings)
    needs_force = (
        settings.vault_path != previous_vault
        or settings.embedding_model != previous_embedding
    )
    if settings.vault_path:
        asyncio.create_task(_perform_reindex(force=needs_force))
    return {"ok": True, "settings": settings.public_dict()}


@app.post("/api/reindex")
async def reindex(request: ReindexRequest) -> dict:
    if not state.settings.vault_path:
        raise HTTPException(status_code=400, detail="Сначала выберите Obsidian vault.")
    with state.lock:
        if state.indexing:
            return {"ok": True, "already_running": True}
    asyncio.create_task(_perform_reindex(force=request.force))
    return {"ok": True, "started": True, "force": request.force}


@app.post("/api/session/reset")
def reset_session(request: ResetRequest) -> dict:
    state.reset(request.session_id)
    return {"ok": True}


@app.get("/api/search")
def search(
    q: str = Query(min_length=1, max_length=2_000),
    mode: Mode = "chat",
) -> dict:
    client = state.client()
    embedder = client if client.available() else None
    results = state.index.search(
        q,
        state.settings,
        embedder,
        mode=mode,
    )
    return {"results": [result.to_dict() for result in results]}


def _ndjson(event: dict) -> str:
    return json.dumps(event, ensure_ascii=False) + "\n"


@app.post("/api/chat")
def chat(request: ChatRequest) -> StreamingResponse:
    message = request.message.strip()
    if not state.settings.vault_path:
        raise HTTPException(status_code=400, detail="Сначала выберите Obsidian vault.")
    if not message:
        raise HTTPException(status_code=400, detail="Сообщение пустое.")

    previous_history = state.history(request.session_id)
    state.append(request.session_id, "user", message)
    retrieval_history = previous_history[-4:] + [{"role": "user", "content": message}]
    retrieval_query = "\n".join(item["content"] for item in retrieval_history)
    settings = state.settings
    client = state.client()
    embedder = client if client.available() else None
    results = state.index.search(
        retrieval_query,
        settings,
        embedder,
        mode=request.mode,
    )
    sources = [
        {
            "title": result.title,
            "heading": result.heading,
            "file_path": result.file_path,
            "excerpt": result.excerpt,
            "score": result.score,
            "collection": result.collection,
        }
        for result in results
    ]
    context = build_context(
        [result.to_dict() for result in results],
        settings.context_chars,
    )
    recent_history = previous_history[-settings.history_messages :]
    messages = [
        {"role": "system", "content": system_prompt(request.mode, context)},
        *recent_history,
        {"role": "user", "content": message},
    ]

    def generate() -> Iterator[str]:
        yield _ndjson({"type": "meta", "session_id": request.session_id})
        yield _ndjson({"type": "sources", "sources": sources})
        answer_parts: list[str] = []
        try:
            for token in client.chat_stream(
                model=settings.chat_model,
                messages=messages,
                temperature=settings.temperature,
            ):
                answer_parts.append(token)
                yield _ndjson({"type": "token", "content": token})
            answer = "".join(answer_parts).strip()
            if answer:
                state.append(request.session_id, "assistant", answer)
            yield _ndjson({"type": "done"})
        except OllamaError as error:
            yield _ndjson(
                {
                    "type": "error",
                    "message": (
                        f"{error}. Запустите Ollama и проверьте модель "
                        f"`{settings.chat_model}` в настройках."
                    ),
                }
            )

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"},
    )


STATIC_DIR = PROJECT_ROOT / "app" / "static"
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
