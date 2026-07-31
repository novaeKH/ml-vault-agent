from app.prompts import MODE_PROMPTS


def test_practice_prompt_uses_progressive_coaching():
    prompt = MODE_PROMPTS["practice"]
    assert "ровно одну" in prompt
    assert "**Сложность**" in prompt
    assert "**Дано**" in prompt
    assert "**Нужно вернуть**" in prompt
    assert "Easy или Medium" in prompt
    assert "Подсказки раскрывай постепенно" in prompt
    assert "только по прямой просьбе" in prompt
