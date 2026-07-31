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

from app.code_validation import build_repair_instruction, validate_python_answer
from app.config import (
    DATA_DIR,
    PROJECT_ROOT,
    Settings,
    discover_vaults,
    load_settings,
    save_settings,
    validate_vault_path,
)
from app.generation import (
    filter_low_relevance,
    model_for_mode,
    profile_for_mode,
    should_use_retrieval,
    trim_messages_to_context,
    user_only_retrieval_query,
)
from app.index import HybridIndex
from app.ollama_client import ChatResult, OllamaClient, OllamaError
from app.prompts import build_context, system_prompt


Mode = Literal["chat", "tutor", "interviewer", "practice", "code", "code_builder"]


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
    code_model: str | None = None
    embedding_model: str | None = None
    top_k: int | None = None
    temperature: float | None = None
    context_chars: int | None = None
    history_messages: int | None = None
    code_max_attempts: int | None = None


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
    except Exception as error:
        with state.lock:
            state.index_error = str(error)
    finally:
        with state.lock:
            state.indexing = False


@asynccontextmanager
async def lifespan(_: FastAPI):
    if state.settings.vault_path:
        runtime_marker = DATA_DIR / "runtime-version.txt"
        try:
            previous_version = runtime_marker.read_text(encoding="utf-8").strip()
        except OSError:
            previous_version = ""
        force = previous_version != "0.3.0"
        asyncio.create_task(_perform_reindex(force=force))
        if force:
            try:
                runtime_marker.write_text("0.3.0\n", encoding="utf-8")
            except OSError:
                pass
    yield


app = FastAPI(
    title="ML Vault Agent",
    version="0.3.0",
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
            "code_model_ready": settings.code_model in models,
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
    results = state.index.search(q, state.settings, embedder, mode=mode)
    return {"results": [result.to_dict() for result in filter_low_relevance(results)]}


def _ndjson(event: dict) -> str:
    return json.dumps(event, ensure_ascii=False) + "\n"


def _retrieve(
    *,
    message: str,
    mode: str,
    previous_history: list[dict[str, str]],
    client: OllamaClient,
) -> list:
    if not should_use_retrieval(message, mode):
        return []
    if not state.settings.vault_path:
        return []
    embedder = client if client.available() else None
    query = user_only_retrieval_query(previous_history, message)
    results = state.index.search(query, state.settings, embedder, mode=mode)
    return filter_low_relevance(results)


def _source_payload(results: list) -> list[dict]:
    return [
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


def _messages(
    *,
    mode: str,
    message: str,
    previous_history: list[dict[str, str]],
    results: list,
) -> tuple[list[dict[str, str]], object]:
    settings = state.settings
    profile = profile_for_mode(
        mode,
        fallback_temperature=settings.temperature if mode == "chat" else None,
    )
    context = build_context(
        [result.to_dict() for result in results],
        settings.context_chars,
    )
    recent_history = previous_history[-settings.history_messages :]
    messages = [
        {"role": "system", "content": system_prompt(mode, context)},
        *recent_history,
        {"role": "user", "content": message},
    ]
    messages = trim_messages_to_context(
        messages,
        num_ctx=profile.num_ctx,
        reserved_output_tokens=profile.num_predict,
    )
    return messages, profile


def _code_builder_result(
    *,
    client: OllamaClient,
    model: str,
    messages: list[dict[str, str]],
    profile,
    original_request: str,
) -> tuple[ChatResult, dict]:
    result = client.complete(model=model, messages=messages, profile=profile)
    validation = validate_python_answer(result.content)
    attempts = 0

    while attempts < state.settings.code_max_attempts:
        problem = ""
        if result.truncated:
            problem = (
                "Ответ достиг лимита генерации и оборвался. Верни полный ответ заново, "
                "сократив объяснения, но не код."
            )
        elif validation.found_python and not validation.valid:
            problem = validation.error
        if not problem:
            break

        attempts += 1
        repair_messages = [
            messages[0],
            {
                "role": "user",
                "content": build_repair_instruction(
                    original_request,
                    result.content,
                    problem,
                ),
            },
        ]
        result = client.complete(model=model, messages=repair_messages, profile=profile)
        validation = validate_python_answer(result.content)

    metadata = {
        "attempts": attempts + 1,
        "found_python": validation.found_python,
        "syntax_valid": validation.valid,
        "syntax_error": validation.error,
        "truncated": result.truncated,
        "done_reason": result.done_reason,
        "prompt_eval_count": result.prompt_eval_count,
        "eval_count": result.eval_count,
    }
    return result, metadata


@app.post("/api/chat")
def chat(request: ChatRequest) -> StreamingResponse:
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Сообщение пустое.")
    if not state.settings.vault_path and request.mode != "code_builder":
        raise HTTPException(status_code=400, detail="Сначала выберите Obsidian vault.")

    previous_history = state.history(request.session_id)
    state.append(request.session_id, "user", message)
    settings = state.settings
    client = state.client()
    results = _retrieve(
        message=message,
        mode=request.mode,
        previous_history=previous_history,
        client=client,
    )
    sources = _source_payload(results)
    messages, profile = _messages(
        mode=request.mode,
        message=message,
        previous_history=previous_history,
        results=results,
    )
    model = model_for_mode(settings, request.mode)

    def generate() -> Iterator[str]:
        yield _ndjson({"type": "meta", "session_id": request.session_id, "model": model})
        yield _ndjson({"type": "sources", "sources": sources})
        try:
            if request.mode == "code_builder":
                result, validation = _code_builder_result(
                    client=client,
                    model=model,
                    messages=messages,
                    profile=profile,
                    original_request=message,
                )
                answer = result.content.strip()
                for start in range(0, len(answer), 160):
                    yield _ndjson({"type": "token", "content": answer[start : start + 160]})
                yield _ndjson({"type": "validation", **validation})
                if validation["truncated"]:
                    yield _ndjson(
                        {
                            "type": "warning",
                            "message": "Ответ достиг лимита и может быть неполным.",
                        }
                    )
                if validation["found_python"] and not validation["syntax_valid"]:
                    yield _ndjson(
                        {
                            "type": "warning",
                            "message": (
                                "Python-код не прошёл статическую проверку: "
                                f"{validation['syntax_error']}"
                            ),
                        }
                    )
                if answer:
                    state.append(request.session_id, "assistant", answer)
                yield _ndjson({"type": "done", **validation})
                return

            answer_parts: list[str] = []
            done_reason = ""
            prompt_eval_count = 0
            eval_count = 0
            for event in client.chat_events(
                model=model,
                messages=messages,
                profile=profile,
            ):
                if event.thinking:
                    yield _ndjson({"type": "thinking", "content": event.thinking})
                if event.content:
                    answer_parts.append(event.content)
                    yield _ndjson({"type": "token", "content": event.content})
                if event.done:
                    done_reason = event.done_reason
                    prompt_eval_count = event.prompt_eval_count
                    eval_count = event.eval_count

            answer = "".join(answer_parts).strip()
            if answer:
                state.append(request.session_id, "assistant", answer)
            truncated = done_reason.casefold() in {"length", "max_tokens"}
            if truncated:
                yield _ndjson(
                    {
                        "type": "warning",
                        "message": "Ответ достиг лимита генерации и может быть неполным.",
                    }
                )
            yield _ndjson(
                {
                    "type": "done",
                    "done_reason": done_reason,
                    "truncated": truncated,
                    "prompt_eval_count": prompt_eval_count,
                    "eval_count": eval_count,
                }
            )
        except OllamaError as error:
            yield _ndjson(
                {
                    "type": "error",
                    "message": (
                        f"{error}. Запустите Ollama и проверьте модель "
                        f"`{model}` в настройках."
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
