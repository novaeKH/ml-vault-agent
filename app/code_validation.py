from __future__ import annotations

import ast
import re
from dataclasses import dataclass


FENCED_CODE_RE = re.compile(
    r"```(?P<language>[A-Za-z0-9_+.-]*)\s*\n(?P<code>[\s\S]*?)```",
    re.MULTILINE,
)


@dataclass(frozen=True, slots=True)
class CodeValidation:
    found_python: bool
    valid: bool
    code: str
    error: str = ""


def extract_python_blocks(answer: str) -> list[str]:
    blocks: list[str] = []
    for match in FENCED_CODE_RE.finditer(answer):
        language = match.group("language").casefold()
        if language in {"python", "py", "python3", ""}:
            blocks.append(match.group("code").strip())
    return blocks


def validate_python_answer(answer: str) -> CodeValidation:
    blocks = extract_python_blocks(answer)
    if not blocks:
        return CodeValidation(found_python=False, valid=True, code="")
    code = max(blocks, key=len)
    try:
        ast.parse(code)
    except SyntaxError as error:
        location = ""
        if error.lineno is not None:
            location = f" at line {error.lineno}"
            if error.offset is not None:
                location += f", column {error.offset}"
        return CodeValidation(
            found_python=True,
            valid=False,
            code=code,
            error=f"{error.msg}{location}",
        )
    return CodeValidation(found_python=True, valid=True, code=code)


def build_repair_instruction(original_request: str, answer: str, error: str) -> str:
    return f"""
Исправь предыдущий ответ как senior Python/ML engineer.

Исходная задача пользователя:
{original_request}

Проверка Python-кода завершилась ошибкой:
{error}

Предыдущий ответ:
{answer}

Верни полностью исправленный финальный ответ. Не показывай diff и не объясняй процесс
исправления. Сохрани все выполненные требования, но замени оборванный или ошибочный
код одним цельным запускаемым блоком. Перед завершением внутренне проверь синтаксис,
импорты, отступы и закрытие всех функций и скобок.
""".strip()
