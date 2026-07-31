# Установка на Windows

## Требования

- Windows 10 22H2 или новее;
- Python 3.11–3.14;
- Git for Windows;
- Ollama for Windows;
- примерно 6 GB для двух моделей плюс место для Ollama и локального индекса.

## 1. Установите программы

1. Скачайте [Python](https://www.python.org/downloads/windows/). В установщике
   включите **Add python.exe to PATH**.
2. Установите [Git for Windows](https://git-scm.com/download/win).
3. Установите [Ollama](https://ollama.com/download/windows). После установки она
   работает в фоне и предоставляет локальный API на `http://localhost:11434`.
4. Закройте и заново откройте PowerShell, чтобы обновился `PATH`.

Проверка:

```powershell
python --version
git --version
ollama --version
```

## 2. Скачайте агент

```powershell
cd $HOME\Documents
git clone https://github.com/novaeKH/ml-vault-agent.git
cd ml-vault-agent
```

Для private-репозитория Git запросит вход в GitHub. Также можно скачать ZIP через
кнопку **Code → Download ZIP** и распаковать его.

## 3. Установите зависимости и модели

```powershell
.\setup.ps1
```

Скрипт создаёт только локальную `.venv`, устанавливает Python-зависимости и
загружает:

- `qwen3:8b` — около 5.2 GB;
- `qwen3-embedding:0.6b` — около 639 MB.

Ручная установка моделей:

```powershell
ollama pull qwen3:8b
ollama pull qwen3-embedding:0.6b
ollama list
```

Если модели уже установлены, повторно они не скачиваются. Чтобы временно пропустить
их загрузку:

```powershell
.\setup.ps1 -SkipModels
```

## 4. Запустите

```powershell
.\run.ps1
```

Откройте [http://127.0.0.1:8787](http://127.0.0.1:8787). В дальнейшем можно
запускать `Start ML Vault Agent.bat` двойным кликом.

## 5. Подключите Obsidian

В настройках агента вставьте полный путь к папке vault, например:

```text
C:\Users\Ilya\Documents\My_brain_v2
C:\Users\Ilya\OneDrive\Documents\My_brain_v2
```

Нужна сама корневая папка vault, внутри которой находятся `.obsidian` и файлы
`.md`. Нажмите сохранение и дождитесь Reindex.

## Диагностика

- **`python` не найден:** переустановите Python с опцией PATH или попробуйте
  `py -3.12 --version`.
- **`ollama` не найден:** откройте Ollama через Start, затем новый PowerShell.
- **Модель не найдена:** выполните `ollama list` и повторите `ollama pull ...`.
- **Порт 8787 занят:** закройте предыдущий экземпляр агента.
- **Vault не принимается:** проверьте наличие `.obsidian` и хотя бы одного `.md`.
- **Мало памяти:** установите `ollama pull qwen3:4b` и выберите `qwen3:4b` в
  настройке Chat model.
