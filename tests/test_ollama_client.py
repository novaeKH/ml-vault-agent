import io
import json
from contextlib import contextmanager

from app.generation import PROFILES
from app.ollama_client import OllamaClient


class FakeClient(OllamaClient):
    @contextmanager
    def _request(self, path, payload=None, *, timeout=None):
        assert path == "/api/chat"
        assert payload["think"] is True
        lines = [
            {"message": {"thinking": "plan"}, "done": False},
            {"message": {"content": "hello"}, "done": False},
            {
                "message": {"content": " world"},
                "done": True,
                "done_reason": "length",
                "prompt_eval_count": 10,
                "eval_count": 20,
            },
        ]
        raw = b"".join(json.dumps(item).encode() + b"\n" for item in lines)
        yield io.BytesIO(raw)


def test_complete_preserves_done_reason_and_thinking():
    client = FakeClient("http://localhost")
    result = client.complete(
        model="model",
        messages=[{"role": "user", "content": "test"}],
        profile=PROFILES["code_builder"],
    )
    assert result.content == "hello world"
    assert result.thinking == "plan"
    assert result.done_reason == "length"
    assert result.truncated
    assert result.eval_count == 20
