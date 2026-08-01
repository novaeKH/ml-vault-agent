from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Iterator
from typing import Any


class OllamaError(RuntimeError):
    pass


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

    def chat_stream(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        num_ctx: int = 16_384,
        num_predict: int = 1_600,
        top_p: float = 0.9,
        top_k: int = 30,
        min_p: float = 0.0,
        repeat_penalty: float = 1.05,
    ) -> Iterator[str]:
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "think": False,
            "keep_alive": "10m",
            "options": {
                "temperature": temperature,
                "num_ctx": num_ctx,
                "num_predict": num_predict,
                "top_p": top_p,
                "top_k": top_k,
                "min_p": min_p,
                "repeat_penalty": repeat_penalty,
            },
        }
        with self._request("/api/chat", payload) as response:
            for raw_line in response:
                if not raw_line.strip():
                    continue
                try:
                    event = json.loads(raw_line)
                except json.JSONDecodeError as error:
                    raise OllamaError("Ollama вернула повреждённый stream.") from error
                if "error" in event:
                    raise OllamaError(str(event["error"]))
                content = event.get("message", {}).get("content", "")
                if content:
                    yield content
                if event.get("done"):
                    break
