from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class GenerationProfile:
    num_ctx: int
    num_predict: int
    temperature: float
    top_p: float
    top_k: int
    min_p: float = 0.0
    repeat_penalty: float = 1.05


# Theory-first defaults favor repeatable, grounded explanations over creativity.
PROFILES: dict[str, GenerationProfile] = {
    "chat": GenerationProfile(16_384, 1_800, 0.25, 0.90, 30),
    "tutor": GenerationProfile(20_480, 2_600, 0.30, 0.90, 30),
    "interviewer": GenerationProfile(16_384, 1_200, 0.25, 0.88, 30),
    "practice": GenerationProfile(16_384, 1_800, 0.25, 0.88, 30),
    "code": GenerationProfile(16_384, 2_200, 0.18, 0.88, 30),
}


FOLLOW_UP_MARKERS = (
    "а почему",
    "а как",
    "почему",
    "как это",
    "что это",
    "что насчет",
    "что насчёт",
    "можешь подробнее",
    "объясни подробнее",
    "приведи пример",
    "и что",
)


def profile_for_mode(
    mode: str,
    configured_temperature: float | None = None,
) -> GenerationProfile:
    profile = PROFILES.get(mode, PROFILES["chat"])
    if configured_temperature is None:
        return profile
    temperature = min(max(float(configured_temperature), 0.0), profile.temperature)
    return GenerationProfile(
        num_ctx=profile.num_ctx,
        num_predict=profile.num_predict,
        temperature=temperature,
        top_p=profile.top_p,
        top_k=profile.top_k,
        min_p=profile.min_p,
        repeat_penalty=profile.repeat_penalty,
    )


def retrieval_query(
    previous_history: list[dict[str, str]],
    current_message: str,
) -> str:
    current = current_message.strip()
    normalized = current.casefold()
    is_follow_up = any(
        normalized.startswith(marker) for marker in FOLLOW_UP_MARKERS
    )
    if not is_follow_up:
        return current

    previous_user_messages = [
        item.get("content", "").strip()
        for item in previous_history
        if item.get("role") == "user" and item.get("content", "").strip()
    ]
    if not previous_user_messages:
        return current
    return f"{previous_user_messages[-1]}\n{current}"


def filter_low_relevance(results: list[Any]) -> list[Any]:
    if not results:
        return []
    top = results[0]
    lexical = float(getattr(top, "lexical_score", 0.0) or 0.0)
    semantic_value = getattr(top, "semantic_score", None)
    semantic = float(semantic_value) if semantic_value is not None else None
    if lexical <= 0 and (semantic is None or semantic < 0.18):
        return []
    return results


def estimate_tokens(text: str) -> int:
    # Russian text and Markdown are usually closer to 3 chars/token than the
    # common English-only approximation of 4 chars/token.
    return max(1, (len(text) + 2) // 3)


def trim_messages_to_context(
    messages: list[dict[str, str]],
    *,
    num_ctx: int,
    reserved_output_tokens: int,
) -> list[dict[str, str]]:
    budget = max(1_024, num_ctx - reserved_output_tokens)
    if sum(estimate_tokens(item.get("content", "")) for item in messages) <= budget:
        return messages
    if len(messages) <= 2:
        return messages

    system = messages[0]
    newest = messages[-1]
    middle = messages[1:-1]
    selected: list[dict[str, str]] = []
    used = estimate_tokens(system.get("content", "")) + estimate_tokens(
        newest.get("content", "")
    )
    for item in reversed(middle):
        cost = estimate_tokens(item.get("content", ""))
        if used + cost > budget:
            continue
        selected.append(item)
        used += cost
    selected.reverse()
    return [system, *selected, newest]
