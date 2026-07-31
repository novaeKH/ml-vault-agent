# Установка на macOS

## Требования

- macOS 14 Sonoma или новее для актуальной Ollama;
- Python 3.11–3.14;
- Git (есть в Xcode Command Line Tools или Homebrew);
- примерно 6 GB для моделей плюс место для Ollama и локального индекса.

## 1. Установите Python, Git и Ollama

Вариант с официальными установщиками:

- [Python for macOS](https://www.python.org/downloads/macos/);
- [Ollama for macOS](https://ollama.com/download/mac).

Или через Homebrew:

```bash
brew install python@3.13 git
brew install --cask ollama
```

Откройте приложение Ollama один раз, затем проверьте Terminal:

```bash
python3 --version
git --version
ollama --version
```

## 2. Скачайте и установите агент

```bash
cd ~/Documents
git clone https://github.com/novaeKH/ml-vault-agent.git
cd ml-vault-agent
./setup.sh
```

Скрипт создаёт `.venv`, ставит Python-зависимости и при необходимости загружает
`qwen3:8b` и `qwen3-embedding:0.6b`.

Ручная установка моделей:

```bash
ollama pull qwen3:8b
ollama pull qwen3-embedding:0.6b
ollama list
```

Чтобы установить backend без загрузки моделей:

```bash
./setup.sh --skip-models
```

## 3. Запустите

```bash
./run.sh
```

Откройте [http://127.0.0.1:8787](http://127.0.0.1:8787). В дальнейшем можно
дважды нажимать `Start ML Vault Agent.command`.

Если Finder впервые блокирует `.command`, нажмите файл правой кнопкой → **Open**.
Также можно восстановить права:

```bash
chmod +x setup.sh run.sh "Setup ML Vault Agent.command" "Start ML Vault Agent.command"
```

## 4. Подключите Obsidian

В настройках агента укажите корневую папку vault, например:

```text
/Users/ilya/Documents/My_brain_v2
/Users/ilya/Library/Mobile Documents/iCloud~md~obsidian/Documents/My_brain_v2
```

Нажмите сохранение и дождитесь Reindex. Агент читает Markdown, но не записывает в
vault.

## Диагностика

- **Ollama недоступна:** откройте приложение Ollama или выполните `ollama serve`.
- **Vault не найден:** вставьте полный путь вручную; папка должна содержать
  `.obsidian` и хотя бы один `.md`.
- **Мало памяти:** установите `ollama pull qwen3:4b` и выберите `qwen3:4b` в
  настройке Chat model.
- **Порт 8787 занят:** закройте предыдущий Terminal с агентом.
