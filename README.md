# ML Vault Agent

Локальный read-only RAG-агент для Obsidian-хранилища с заметками по Data Science,
Machine Learning, Python и алгоритмам. Агент индексирует Markdown-разделы,
объединяет BM25 и embeddings и формирует ответы через локальную модель Ollama.

Все данные остаются на компьютере: web-интерфейс слушает только
`http://127.0.0.1:8787`, а vault никогда не записывается и не загружается в GitHub.

## Возможности

- режимы Chat, Tutor, Interviewer, Algorithm Practice и Code Tutor;
- алгоритмическая практика с одной задачей за ход, поэтапными подсказками,
  проверкой сложности и разбором кода;
- отдельные retrieval-слои для теории, практики и эталонных решений, чтобы режим
  Practice не раскрывал ответ раньше времени;
- локальная генерация через `qwen3:8b`;
- мультиязычный семантический поиск через `qwen3-embedding:0.6b`;
- инкрементальный SQLite-индекс;
- работа без embeddings в режиме lexical-only, если Ollama временно выключена;
- Windows 10/11 и macOS 14+;
- интерфейс и модели работают локально, без облачного API.

## Что хранится в GitHub

В репозиторий входит только код приложения. Не публикуются:

- Obsidian vault и его заметки;
- модели Ollama;
- `data/settings.json` с локальным путём к vault;
- SQLite-индекс, логи, `.venv` и кэш Python.

После клонирования на новом компьютере модели скачиваются через Ollama, а путь к
локальной копии vault выбирается в настройках агента.

## Быстрый старт

Нужны Python 3.11–3.14, Git и Ollama. Модели занимают примерно 6 GB; для Ollama и
рабочих файлов потребуется дополнительное место.

### Windows

1. Установите [Python](https://www.python.org/downloads/windows/) и Git. При
   установке Python включите `Add python.exe to PATH`.
2. Установите [Ollama for Windows](https://ollama.com/download/windows).
3. Откройте PowerShell и выполните:

```powershell
git clone https://github.com/novaeKH/ml-vault-agent.git
cd ml-vault-agent
.\setup.ps1
.\run.ps1
```

Вместо последних двух команд можно дважды нажать сначала
`Setup ML Vault Agent.bat`, затем `Start ML Vault Agent.bat`.

Подробная инструкция: [docs/WINDOWS.md](docs/WINDOWS.md).

### macOS

1. Установите [Python](https://www.python.org/downloads/macos/) и
   [Ollama for macOS](https://ollama.com/download/mac).
2. Откройте Terminal и выполните:

```bash
git clone https://github.com/novaeKH/ml-vault-agent.git
cd ml-vault-agent
./setup.sh
./run.sh
```

Для последующих запусков можно дважды нажимать `Start ML Vault Agent.command`.

Подробная инструкция: [docs/MACOS.md](docs/MACOS.md).

После запуска откройте [http://127.0.0.1:8787](http://127.0.0.1:8787).

## Режим Algorithm Practice

Выберите **Practice** в боковом меню и укажите тему или уровень, например:

```text
Дай easy-задачу на two pointers без решения.
Хочу потренировать sliding window, уровень medium.
Проверь мою идею и дай только первую подсказку.
Объясни, как распознавать задачи на prefix sum.
```

Агент даёт одну задачу, просит сначала сформулировать идею и раскрывает подсказки
по уровням. Эталонный код показывается только по прямой просьбе. Для свободного
разбора готового решения используйте **Code Tutor**.

## Подключение Obsidian vault

Vault должен быть обычной локальной папкой, внутри которой есть каталог
`.obsidian` и Markdown-файлы. Откройте настройки агента, вставьте полный путь к
папке vault, сохраните настройки и дождитесь Reindex.

Примеры путей:

```text
Windows: C:\Users\Ilya\Documents\My_brain_v2
macOS:   /Users/ilya/Documents/My_brain_v2
```

Можно использовать папку, синхронизированную Obsidian Sync, OneDrive, iCloud или
другим сервисом, если она доступна локально. Сам vault в репозиторий копировать не
нужно. Подробности и правила отбора заметок: [docs/OBSIDIAN.md](docs/OBSIDIAN.md).

## Установка моделей вручную

`setup.sh` и `setup.ps1` делают это автоматически. Эквивалентные команды:

```bash
ollama pull qwen3:8b
ollama pull qwen3-embedding:0.6b
```

Для компьютера с меньшим объёмом памяти можно установить `qwen3:4b`, затем указать
это имя в настройке **Chat model**:

```bash
ollama pull qwen3:4b
```

Embedding-модель `qwen3-embedding:0.6b` менять не требуется.

## Команды разработчика

macOS:

```bash
.venv/bin/python -m pytest
.venv/bin/python -m app.cli smoke
.venv/bin/python -m app.cli smoke --live
```

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m app.cli smoke
.\.venv\Scripts\python.exe -m app.cli smoke --live
```

## Как устроен индекс

1. `type: concept` и `type: deep-dive` образуют базу знаний.
2. `type: practice` + `rag: include` образуют коллекцию задач и подсказок.
3. `type: solution` + `rag: include` образуют отдельную коллекцию решений,
   доступную Code Tutor, но не режиму Practice.
4. `type: interview` образует коллекцию режима Interviewer.
5. `rag: exclude`, `status: archived`, `.trash`, `.obsidian` и скрытые папки
   всегда пропускаются.
6. Markdown делится по H2/H3; chunks получают title, breadcrumb, aliases, type,
   area, heading и относительный путь.
7. Reindex пересчитывает только новые, изменённые и удалённые файлы.
8. Поиск объединяет BM25 и cosine similarity через reciprocal-rank fusion.

## Структура проекта

```text
app/                    backend и локальный web-интерфейс
tests/                  автономные тесты без Ollama
docs/                   инструкции Windows, macOS и Obsidian
setup.sh / run.sh       установка и запуск на macOS
setup.ps1 / run.ps1     установка и запуск на Windows
data/                   локальные настройки и индекс (не публикуются)
```
