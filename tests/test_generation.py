from types import SimpleNamespace

from app.generation import (
    PROFILES,
    filter_low_relevance,
    model_for_mode,
    should_use_retrieval,
    trim_messages_to_context,
    user_only_retrieval_query,
)


def test_code_builder_uses_long_thinking_profile():
    profile = PROFILES["code_builder"]
    assert profile.think is True
    assert profile.num_predict >= 6_144
    assert profile.num_ctx >= 16_384


def test_code_builder_uses_separate_model():
    settings = SimpleNamespace(chat_model="qwen3:8b", code_model="coder:14b")
    assert model_for_mode(settings, "code_builder") == "coder:14b"
    assert model_for_mode(settings, "tutor") == "qwen3:8b"


def test_code_builder_skips_rag_for_standalone_generation():
    assert not should_use_retrieval("Напиши автономный Python-скрипт", "code_builder")
    assert should_use_retrieval("Используй мои заметки из Obsidian", "code_builder")


def test_retrieval_query_uses_user_messages_only():
    history = [
        {"role": "user", "content": "Объясни PCA"},
        {"role": "assistant", "content": "Выдуманный ответ про CatBoost"},
    ]
    query = user_only_retrieval_query(history, "А теперь пример")
    assert "PCA" in query
    assert "CatBoost" not in query


def test_low_relevance_semantic_result_is_removed():
    weak = SimpleNamespace(lexical_score=0.0, semantic_score=0.1)
    strong = SimpleNamespace(lexical_score=0.5, semantic_score=None)
    assert filter_low_relevance([weak]) == []
    assert filter_low_relevance([strong]) == [strong]


def test_context_trimming_keeps_system_and_latest_user():
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "old " * 5_000},
        {"role": "assistant", "content": "answer " * 5_000},
        {"role": "user", "content": "latest"},
    ]
    trimmed = trim_messages_to_context(messages, num_ctx=2_048, reserved_output_tokens=512)
    assert trimmed[0]["role"] == "system"
    assert trimmed[-1]["content"] == "latest"
