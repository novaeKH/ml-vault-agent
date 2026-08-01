from app.prompts import (
    CALLOUT_GUIDE,
    ML_REASONING_GUIDE,
    MODE_PROMPTS,
    PRESENTATION_PROMPTS,
    system_prompt,
)


def test_practice_prompt_uses_progressive_coaching():
    prompt = MODE_PROMPTS["practice"]
    assert "ровно одну" in prompt
    assert "**Сложность**" in prompt
    assert "**Дано**" in prompt
    assert "**Нужно вернуть**" in prompt
    assert "Easy или Medium" in prompt
    assert "Подсказки раскрывай постепенно" in prompt
    assert "только по прямой просьбе" in prompt


def test_non_practice_modes_get_structured_presentation_rules():
    for mode in ("chat", "tutor", "interviewer", "code"):
        prompt = system_prompt(mode, "context")
        assert CALLOUT_GUIDE in prompt
        assert PRESENTATION_PROMPTS[mode] in prompt
        assert "[!SUMMARY]" in prompt or "[!QUESTION]" in prompt


def test_practice_keeps_its_existing_task_card_contract():
    prompt = system_prompt("practice", "context")

    assert PRESENTATION_PROMPTS["practice"] == ""
    assert CALLOUT_GUIDE not in prompt
    assert "**Название**" in prompt


def test_all_modes_reason_about_ml_problem_definition_and_leakage():
    for mode in MODE_PROMPTS:
        prompt = system_prompt(mode, "context")
        assert ML_REASONING_GUIDE in prompt
        assert "target" in prompt
        assert "leakage" in prompt


def test_code_mode_is_a_theory_template_not_an_autonomous_builder():
    prompt = MODE_PROMPTS["code"]

    assert "Код здесь — иллюстрация теории" in prompt
    assert "не генерируй лишнюю инфраструктуру" in prompt
