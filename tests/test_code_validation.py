from app.code_validation import extract_python_blocks, validate_python_answer


def test_valid_python_block_passes():
    answer = """Готово.\n```python\ndef add(a: int, b: int) -> int:\n    return a + b\n```"""
    result = validate_python_answer(answer)
    assert result.found_python
    assert result.valid


def test_broken_python_block_reports_syntax_error():
    answer = """```python\ndef broken(:\n    pass\n```"""
    result = validate_python_answer(answer)
    assert result.found_python
    assert not result.valid
    assert result.error


def test_largest_python_block_is_checked():
    answer = """```python\nx = 1\n```\n```python\ndef f() -> int:\n    return 2\n```"""
    result = validate_python_answer(answer)
    assert "def f" in result.code


def test_non_python_answer_does_not_fail_validation():
    result = validate_python_answer("Обычное объяснение без кода")
    assert not result.found_python
    assert result.valid


def test_extracts_unlabelled_fence_for_compatibility():
    blocks = extract_python_blocks("```\nx = 1\n```")
    assert blocks == ["x = 1"]
