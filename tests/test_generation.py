from dataclasses import dataclass

from app.generation import (
    filter_low_relevance,
    profile_for_mode,
    retrieval_query,
    trim_messages_to_context,
)


@dataclass
class Result:
    lexical_score: float
    semantic_score: float | None


def test_standalone_retrieval_query_uses_only_current_user_message():
    history = [
        {"role": "user", "content": "Расскажи про линейную регрессию"},
        {"role": "assistant", "content": "Длинный ответ модели про OLS"},
    ]

    query = retrieval_query(history, "Как устроен градиентный бустинг для регрессии?")

    assert query == "Как устроен градиентный бустинг для регрессии?"
    assert "ответ модели" not in query


def test_short_follow_up_keeps_previous_user_topic_but_not_assistant_answer():
    history = [
        {"role": "user", "content": "Объясни bias-variance trade-off"},
        {"role": "assistant", "content": "Служебный текст ответа"},
    ]

    query = retrieval_query(history, "А почему?")

    assert "bias-variance" in query
    assert "А почему?" in query
    assert "Служебный текст" not in query


def test_generation_profiles_cap_temperature_for_accuracy():
    assert profile_for_mode("chat", 0.9).temperature == 0.25
    assert profile_for_mode("code", 0.9).temperature == 0.18
    assert profile_for_mode("tutor", 0.1).temperature == 0.1


def test_low_relevance_context_is_dropped():
    assert filter_low_relevance([Result(0.0, 0.1)]) == []
    assert filter_low_relevance([Result(0.2, None)])
    assert filter_low_relevance([Result(0.0, 0.5)])


def test_old_history_is_trimmed_before_the_current_question():
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "x" * 1_800},
        {"role": "assistant", "content": "y" * 1_800},
        {"role": "user", "content": "current question"},
    ]

    trimmed = trim_messages_to_context(
        messages,
        num_ctx=1_200,
        reserved_output_tokens=100,
    )

    assert trimmed[0]["role"] == "system"
    assert trimmed[-1]["content"] == "current question"
    assert len(trimmed) < len(messages)
