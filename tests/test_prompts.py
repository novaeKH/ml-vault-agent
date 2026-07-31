from app.prompts import CALLOUT_GUIDE, MODE_PROMPTS, PRESENTATION_PROMPTS, system_prompt


def test_practice_prompt_uses_progressive_coaching():
    prompt = MODE_PROMPTS["practice"]
    assert "ровно одну" in prompt
    assert "**Сложность**" in prompt
    assert "Подсказки раскрывай постепенно" in prompt


def test_non_builder_modes_get_structured_presentation_rules():
    for mode in ("chat", "tutor", "interviewer", "code"):
        prompt = system_prompt(mode, "context")
        assert CALLOUT_GUIDE in prompt
        assert PRESENTATION_PROMPTS[mode] in prompt


def test_practice_keeps_task_contract_without_callouts():
    prompt = system_prompt("practice", "context")
    assert CALLOUT_GUIDE not in prompt
    assert "**Название**" in prompt


def test_code_builder_prioritizes_complete_code_without_callouts():
    prompt = system_prompt("code_builder", "context")
    assert CALLOUT_GUIDE not in prompt
    assert "Не используй" in prompt
    assert "TODO" in prompt
    assert "Не обрывай" in prompt
