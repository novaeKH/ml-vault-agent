from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from app.generation import GenerationProfile


class OllamaError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ChatEvent:
    content: str = ""
    thinking: str = ""
    done: bool = False
    done_reason: str = ""
    prompt_eval_count: int = 0
    eval_count: int = 0


@dataclass(slots=True)
class ChatResult:
    content: str = ""
    thinking: str = ""
    done_reason: str = ""
    prompt_eval_count: int = 0
    eval_count: int = 0
    raw_events: list[ChatEvent] = field(default_factory=list)

    @property
    def truncated(self) -> bool:
        return self.done_reason.casefold() in {"length", "max_tokens"}


class OllamaClient:
    def __init__(self, base_url: str, timeout: int = 600) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request(
        self,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout: int | None = None,
    ) -> urllib.response.addinfourl:
        data = None
        headers: dict[str, str] = {}
        method = "GET"
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
            method = "POST"
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            return urllib.request.urlopen(request, timeout=timeout or self.timeout)
        except (urllib.error.URLError, TimeoutError) as error:
            reason = getattr(error, "reason", error)
            raise OllamaError(f"Не удалось обратиться к Ollama: {reason}") from error

    def list_models(self) -> list[str]:
        with self._request("/api/tags", timeout=5) as response:
            payload = json.load(response)
        return sorted(
            {
                item.get("name") or item.get("model")
                for item in payload.get("models", [])
                if item.get("name") or item.get("model")
            }
        )

    def available(self) -> bool:
        try:
            self.list_models()
            return True
        except (OllamaError, ValueError, json.JSONDecodeError):
            return False

    def embed_documents(self, model: str, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        with self._request(
            "/api/embed",
            {"model": model, "input": texts, "truncate": True},
        ) as response:
            payload = json.load(response)
        embeddings = payload.get("embeddings")
        if not isinstance(embeddings, list) or len(embeddings) != len(texts):
            raise OllamaError("Ollama вернула некорректный пакет embeddings.")
        return embeddings

    def embed_query(self, model: str, query: str) -> list[float]:
        instructed_query = (
            "Instruct: Retrieve passages from a Russian-English Data Science and "
            "Machine Learning knowledge base that answer the user's question. "
            "Prefer mathematical and code-relevant causal explanations.\n"
            f"Query: {query}"
        )
        return self.embed_documents(model, [instructed_query])[0]

    def chat_events(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        profile: GenerationProfile,
    ) -> Iterator[ChatEvent]:
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "think": profile.think,
            "keep_alive": "10m",
            "options": {
                "temperature": profile.temperature,
                "top_p": profile.top_p,
                "top_k": profile.top_k,
                "min_p": profile.min_p,
                "num_ctx": profile.num_ctx,
                "num_predict": profile.num_predict,
                "repeat_penalty": profile.repeat_penalty,
            },
        }
        with self._request("/api/chat", payload) as response:
            for raw_line in response:
                if not raw_line.strip():
                    continue
                try:
                    payload_event = json.loads(raw_line)
                except json.JSONDecodeError as error:
                    raise OllamaError("Ollama вернула повреждённый stream.") from error
                if "error" in payload_event:
                    raise OllamaError(str(payload_event["error"]))
                message = payload_event.get("message", {})
                event = ChatEvent(
                    content=str(message.get("content", "") or ""),
                    thinking=str(message.get("thinking", "") or ""),
                    done=bool(payload_event.get("done", False)),
                    done_reason=str(payload_event.get("done_reason", "") or ""),
                    prompt_eval_count=int(payload_event.get("prompt_eval_count", 0) or 0),
                    eval_count=int(payload_event.get("eval_count", 0) or 0),
                )
                yield event
                if event.done:
                    break

    def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        profile: GenerationProfile,
    ) -> ChatResult:
        result = ChatResult()
        content_parts: list[str] = []
        thinking_parts: list[str] = []
        for event in self.chat_events(model=model, messages=messages, profile=profile):
            result.raw_events.append(event)
            if event.content:
                content_parts.append(event.content)
            if event.thinking:
                thinking_parts.append(event.thinking)
            if event.done:
                result.done_reason = event.done_reason
                result.prompt_eval_count = event.prompt_eval_count
                result.eval_count = event.eval_count
        result.content = "".join(content_parts).strip()
        result.thinking = "".join(thinking_parts).strip()
        return result

    def chat_stream(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        num_ctx: int = 16_384,
        num_predict: int = 1_600,
    ) -> Iterator[str]:
        profile = GenerationProfile(
            think=False,
            num_ctx=num_ctx,
            num_predict=num_predict,
            temperature=temperature,
            top_p=0.8,
            top_k=20,
        )
        for event in self.chat_events(model=model, messages=messages, profile=profile):
            if event.content:
                yield event.content
