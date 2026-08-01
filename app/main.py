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
from app.generation import (
    filter_low_relevance,
    profile_for_mode,
    retrieval_query,
    trim_messages_to_context,
)
from app.index import HybridIndex
from app.learning_catalog import CatalogError, diagnostic_map, load_catalog, skill_map
from app.learning_memory import LearningMemory
from app.learning_review import ReviewError, review_answer
from app.ollama_client import OllamaClient, OllamaError
from app.prompts import build_context, system_prompt


Mode = Literal["chat", "tutor", "interviewer", "practice", "code"]


class ChatRequest(BaseModel):
    session_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    message: str = Field(min_length=1, max_length=20_000)
    mode: Mode = "chat"
    skill_id: str | None = Field(default=None, max_length=120)


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


class DiagnoseRequest(BaseModel):
    skill_id: str = Field(min_length=1, max_length=120)
    diagnostic_id: str = Field(min_length=1, max_length=160)
    answer: str = Field(min_length=1, max_length=20_000)


class LearningEvidenceRequest(BaseModel):
    skill_id: str = Field(min_length=1, max_length=120)
    axis: Literal["recall", "explain", "apply", "diagnose"]
    score: float = Field(ge=0, le=1)
    activity_id: str = Field(default="self-report", max_length=160)
    error_code: str | None = Field(default=None, max_length=120)
    note: str = Field(default="", max_length=2_000)


class DismissEvidenceRequest(BaseModel):
    dismissed: bool = True


class RuntimeState:
    def __init__(self) -> None:
        self.settings = load_settings()
        self.index = HybridIndex()
        self.learning = LearningMemory()
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


def _load_catalog_or_http() -> dict:
    if not state.settings.vault_path:
        raise HTTPException(status_code=400, detail="Сначала выберите Obsidian vault.")
    try:
        return load_catalog(state.settings.vault_path)
    except CatalogError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


def _selected_skill(catalog: dict, skill_id: str) -> dict:
    skill = skill_map(catalog).get(skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"Неизвестный навык: {skill_id}")
    return skill


def _learning_prompt_context(catalog: dict, skill: dict) -> str:
    profile = state.learning.skill_profile(skill["id"])
    axis_lines = []
    for axis, summary in profile["axes"].items():
        if summary["level"] == "unseen":
            axis_lines.append(f"- {axis}: ещё нет evidence")
        else:
            axis_lines.append(
                f"- {axis}: {summary['level']}, score={summary['score']}, "
                f"reliability={summary['reliability']}, "
                f"evidence={summary['evidence_count']}"
            )
    errors = ", ".join(item["code"] for item in profile["active_errors"])
    outcomes = "\n".join(f"- {outcome}" for outcome in skill["outcomes"])
    return (
        f"Текущий навык: {skill['title']} ({skill['id']}).\n"
        f"Ожидаемые результаты:\n{outcomes}\n"
        f"Текущее evidence по граням:\n" + "\n".join(axis_lines) + "\n"
        f"Повторяющиеся ошибки: {errors or 'не зафиксированы'}.\n"
        f"Всего активных evidence: {profile['evidence_count']}."
    )


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


@app.get("/api/learning/overview")
def learning_overview() -> dict:
    if not state.settings.vault_path:
        return {
            "available": False,
            "error": "Сначала выберите Obsidian vault.",
        }
    try:
        catalog = load_catalog(state.settings.vault_path)
    except CatalogError as error:
        return {"available": False, "error": str(error)}
    return {"available": True, **state.learning.overview(catalog)}


@app.get("/api/learning/skills/{skill_id}")
def learning_skill(skill_id: str) -> dict:
    catalog = _load_catalog_or_http()
    skill = _selected_skill(catalog, skill_id)
    return {
        "skill": skill,
        "profile": state.learning.skill_profile(skill_id),
        "evidence": state.learning.evidence(
            skill_id=skill_id,
            include_dismissed=True,
            limit=100,
        ),
    }


@app.post("/api/learning/diagnose")
def diagnose_learning_answer(request: DiagnoseRequest) -> dict:
    catalog = _load_catalog_or_http()
    skill = _selected_skill(catalog, request.skill_id)
    diagnostic_entry = diagnostic_map(catalog).get(request.diagnostic_id)
    if diagnostic_entry is None or diagnostic_entry[0] != request.skill_id:
        raise HTTPException(
            status_code=404,
            detail="Диагностический вопрос не относится к выбранному навыку.",
        )
    diagnostic = diagnostic_entry[1]
    try:
        review = review_answer(
            state.client(),
            model=state.settings.chat_model,
            skill=skill,
            diagnostic=diagnostic,
            answer=request.answer,
        )
    except OllamaError as error:
        raise HTTPException(
            status_code=503,
            detail=(
                f"{error}. Запустите Ollama и проверьте модель "
                f"`{state.settings.chat_model}`."
            ),
        ) from error
    except ReviewError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    event = state.learning.record_evidence(
        skill_id=request.skill_id,
        axis=diagnostic["axis"],
        evidence_kind="rubric",
        score=review["score"],
        confidence=0.7,
        activity_id=request.diagnostic_id,
        error_code=review["error_code"],
        note=review["feedback"],
        details={
            "criteria": review["criteria"],
            "reviewer": state.settings.chat_model,
            "catalog_id": catalog["catalog_id"],
        },
    )
    return {
        "ok": True,
        "review": review,
        "evidence": event,
        "profile": state.learning.skill_profile(request.skill_id),
    }


@app.post("/api/learning/evidence")
def add_learning_evidence(request: LearningEvidenceRequest) -> dict:
    catalog = _load_catalog_or_http()
    _selected_skill(catalog, request.skill_id)
    if request.error_code and request.error_code not in catalog["error_taxonomy"]:
        raise HTTPException(status_code=400, detail="Неизвестный тип ошибки.")
    event = state.learning.record_evidence(
        skill_id=request.skill_id,
        axis=request.axis,
        evidence_kind="self_report",
        score=request.score,
        confidence=0.35,
        activity_id=request.activity_id,
        error_code=request.error_code,
        note=request.note,
    )
    return {
        "ok": True,
        "evidence": event,
        "profile": state.learning.skill_profile(request.skill_id),
    }


@app.post("/api/learning/evidence/{event_id}/dismiss")
def dismiss_learning_evidence(
    event_id: int,
    request: DismissEvidenceRequest,
) -> dict:
    try:
        event = state.learning.set_dismissed(event_id, dismissed=request.dismissed)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {
        "ok": True,
        "evidence": event,
        "profile": state.learning.skill_profile(event["skill_id"]),
    }


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

    selected_skill: dict | None = None
    learning_context = ""
    if request.skill_id:
        catalog = _load_catalog_or_http()
        selected_skill = _selected_skill(catalog, request.skill_id)
        learning_context = _learning_prompt_context(catalog, selected_skill)

    previous_history = state.history(request.session_id)
    state.append(request.session_id, "user", message)
    search_query = retrieval_query(previous_history, message)
    if selected_skill:
        search_query = f"{search_query}\nТекущий навык: {selected_skill['title']}"
    settings = state.settings
    client = state.client()
    embedder = client if client.available() else None
    results = state.index.search(
        search_query,
        settings,
        embedder,
        mode=request.mode,
    )
    results = filter_low_relevance(results)
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
    profile = profile_for_mode(request.mode, settings.temperature)
    messages = [
        {
            "role": "system",
            "content": system_prompt(request.mode, context, learning_context),
        },
        *recent_history,
        {"role": "user", "content": message},
    ]
    messages = trim_messages_to_context(
        messages,
        num_ctx=profile.num_ctx,
        reserved_output_tokens=profile.num_predict,
    )

    def generate() -> Iterator[str]:
        yield _ndjson({"type": "meta", "session_id": request.session_id})
        yield _ndjson({"type": "sources", "sources": sources})
        answer_parts: list[str] = []
        try:
            for token in client.chat_stream(
                model=settings.chat_model,
                messages=messages,
                temperature=profile.temperature,
                num_ctx=profile.num_ctx,
                num_predict=profile.num_predict,
                top_p=profile.top_p,
                top_k=profile.top_k,
                min_p=profile.min_p,
                repeat_penalty=profile.repeat_penalty,
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
