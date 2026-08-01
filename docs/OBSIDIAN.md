# Подключение Obsidian vault

## Что нужно переносить между Mac и Windows

Код агента переносится через GitHub. Obsidian vault переносится отдельно:

- через Obsidian Sync;
- через OneDrive, iCloud Drive или другой синхронизируемый каталог;
- копированием папки vault на внешний диск или по локальной сети.

Не кладите vault внутрь репозитория агента: так личные заметки не попадут в GitHub,
а индекс на каждом компьютере построится заново.

## Выбор папки в интерфейсе

1. Запустите агент и откройте `http://127.0.0.1:8787`.
2. Откройте **Настройки**.
3. В поле **Vault path** вставьте абсолютный путь к корневой папке vault.
4. Сохраните настройки.
5. Дождитесь завершения Reindex; при необходимости нажмите полный Reindex.

Корневая папка должна содержать скрытый каталог `.obsidian` и хотя бы один
Markdown-файл. Примеры:

```text
C:\Users\Ilya\OneDrive\Documents\My_brain_v2
/Users/ilya/Documents/My_brain_v2
```

Альтернатива перед запуском — переменная окружения:

```powershell
# Windows PowerShell, только для текущего окна
$env:OBSIDIAN_VAULT_PATH = "C:\Users\Ilya\Documents\My_brain_v2"
.\run.ps1
```

```bash
# macOS, только для текущего Terminal
export OBSIDIAN_VAULT_PATH="$HOME/Documents/My_brain_v2"
./run.sh
```

## Какие заметки индексируются

Добавьте YAML frontmatter к заметке, которую нужно использовать:

```yaml
---
title: Linear Regression
type: concept
area: ml
status: active
aliases:
  - Линейная регрессия
  - OLS
---
```

Поддерживаемые правила:

- `type: concept` и `type: deep-dive` → база знаний;
- `type: interview` → база для режима интервью;
- `type: practice` + `rag: include` → задачи и подсказки для Practice;
- `type: solution` + `rag: include` → решения и шаблоны для Templates;
- другой `type` + `rag: include` → обычная база знаний;
- `rag: exclude` или `status: archived` → не индексировать.

Папки `.obsidian`, `.trash` и любые скрытые папки игнорируются.

После добавления или переноса большого набора заметок откройте настройки агента и
нажмите **Полная переиндексация**. Для алгоритмических материалов рекомендуется
разделять условия (`type: practice`) и эталонные ответы (`type: solution`): так
Practice сможет давать задачи без преждевременного показа решения.

## Приватность и read-only режим

Агент открывает Markdown-файлы только для чтения. В папку vault он не записывает:
настройки и индекс хранятся в `data/` рядом с приложением. Web-сервер доступен
только через loopback-адрес `127.0.0.1`.
