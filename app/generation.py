from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class GenerationProfile:
    think: bool
    num_ctx: int
    num_predict: int
    temperature: float
    top_p: float
    top_k: int
    min_p: float = 0.0
    repeat_penalty: float = 1.05


PROFILES: dict[str, GenerationProfile] = {
    "chat": GenerationProfile(False, 16_384, 1_600, 0.7, 0.8, 20),
    "tutor": GenerationProfile(True, 16_384, 3_000, 0.6, 0.95, 20),
    "interviewer": GenerationProfile(False, 16_384, 1_000, 0.7, 0.8, 20),
    "practice": GenerationProfile(False, 16_384, 1_600, 0.7, 0.8, 20),
    "code": GenerationProfile(True, 16_384, 3_200, 0.6, 0.95, 20),
    "code_builder": GenerationProfile(True, 24_576, 8_192, 0.6, 0.95, 20),
}


def profile_for_mode(mode: str, fallback_temperature: float | None = None) -> GenerationProfile:
    profile = PROFILES.get(mode, PROFILES["chat"])
    if fallback_temperature is None:
        return profile
    return GenerationProfile(
        think=profile.think,
        num_ctx=profile.num_ctx,
        num_predict=profile.num_predict,
        temperature=float(fallback_temperature),
        top_p=profile.top_p,
        top_k=profile.top_k,
        min_p=profile.min_p,
        repeat_penalty=profile.repeat_penalty,
    )


def model_for_mode(settings: Any, mode: str) -> str:
    if mode == "code_builder":
        return str(getattr(settings, "code_model", "")).strip() or settings.chat_model
    return settings.chat_model


def should_use_retrieval(message: str, mode: str) -> bool:
    if mode != "code_builder":
        return True
    normalized = message.casefold()
    markers = (
        "vault",
        "obsidian",
        "заметк",
        "моей базе",
        "моих материалах",
        "как у меня",
        "из хранилища",
        "из базы знаний",
    )
    return any(marker in normalized for marker in markers)


def user_only_retrieval_query(
    previous_history: list[dict[str, str]],
    current_message: str,
) -> str:
    user_messages = [
        item["content"].strip()
        for item in previous_history
        if item.get("role") == "user" and item.get("content", "").strip()
    ]
    recent = user_messages[-1:]
    recent.append(current_message.strip())
    return "\n".join(recent)


def filter_low_relevance(results: list[Any]) -> list[Any]:
    if not results:
        return []
    top = results[0]
    lexical = float(getattr(top, "lexical_score", 0.0) or 0.0)
    semantic_value = getattr(top, "semantic_score", None)
    semantic = float(semantic_value) if semantic_value is not None else None
    if lexical <= 0 and (semantic is None or semantic < 0.20):
        return []
    return results


def estimate_tokens(text: str) -> int:
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
