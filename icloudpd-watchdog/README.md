# iCloudPD Watchdog Bot

Telegram-бот для автоматической синхронизации iCloud фото через [icloudpd](https://github.com/icloudpd/icloudpd).

**Возможности:**
- Синхронизация нескольких аккаунтов iCloud по очереди
- Автоматическое обнаружение слетевшей сессии
- Интерактивная 2FA-авторизация прямо через Telegram
- Уведомления о новых скачанных файлах

---

## Структура файлов

Положи всё в `/mnt/user/appdata/compose/icloudpd-watchdog/`:

```
icloudpd-watchdog/
├── bot.py
├── Dockerfile
├── requirements.txt
├── docker-compose.yml
├── .env              ← создаёшь сам из .env.example (не коммить!)
├── .env.example
└── .gitignore
```

---

## Быстрый старт

### 1. Получи Telegram-токен

Напиши [@BotFather](https://t.me/BotFather) → `/newbot` → получи токен.

### 2. Узнай свой Chat ID

Напиши [@userinfobot](https://t.me/userinfobot) — он пришлёт твой `id`.

### 3. Создай `.env`

```bash
cp .env.example .env
nano .env   # заполни все значения
```

### 4. Запусти

```bash
cd /mnt/user/appdata/compose/icloudpd-watchdog
docker compose up -d --build
```

### 5. Проверь логи

```bash
docker logs -f icloudpd-watchdog
```

---

## Первый запуск и 2FA

При первом запуске (или после слёта сессии) бот автоматически:

1. Обнаруживает ошибку авторизации во время синхронизации
2. Запускает процесс `--auth-only`
3. Пишет тебе в Telegram с просьбой ввести код
4. Ты отвечаешь 6 цифрами прямо в чат боту
5. Код уходит в процесс, сессия сохраняется в `/config/<name>/`
6. Синхронизация возобновляется автоматически

---

## Команды бота

| Команда | Описание |
|---|---|
| `/status` | Текущий статус и список аккаунтов |
| `/reauth ilvits` | Принудительная переавторизация аккаунта |
| `/reauth kate` | Принудительная переавторизация аккаунта |
| `/sync` | Запустить синхронизацию всех аккаунтов сейчас |
| `/help` | Список команд |

---

## Volumes (docker-compose.yml)

| Хост | Контейнер | Назначение |
|---|---|---|
| `/mnt/user/appdata/icloudpd-ilvits` | `/config/ilvits` | Cookie/сессия ilvits |
| `/mnt/user/appdata/icloudpd-kate` | `/config/kate` | Cookie/сессия kate |
| `/mnt/user/photoLibraries/ilvits/icloud` | `/data/ilvits` | Фото ilvits |
| `/mnt/user/photoLibraries/kate/icloud` | `/data/kate` | Фото kate |

---

## Переменные окружения

| Переменная | Обязательная | Описание |
|---|---|---|
| `TELEGRAM_TOKEN` | ✅ | Токен от @BotFather |
| `CHAT_ID` | ✅ | Твой Telegram chat_id |
| `ILVITS_USERNAME` | ✅ | Apple ID (email) первого аккаунта |
| `ILVITS_PASSWORD` | ✅ | Пароль первого аккаунта |
| `KATE_USERNAME` | ✅ | Apple ID (email) второго аккаунта |
| `KATE_PASSWORD` | ✅ | Пароль второго аккаунта |
| `ILVITS_FOLDER_STRUCTURE` | ❌ | Структура папок (по умолч.: `{:%Y/%m}`) |
| `KATE_FOLDER_STRUCTURE` | ❌ | Структура папок (по умолч.: `{:%Y/%m}`) |
| `SYNC_INTERVAL` | ❌ | Интервал синхронизации в секундах (по умолч.: `3600`) |

---

## Заметки

**App-specific password** — если у тебя включена двухфакторная аутентификация Apple ID (а она должна быть включена), Apple может потребовать использовать app-specific password вместо основного. Создать: [appleid.apple.com](https://appleid.apple.com) → Безопасность → Пароли для приложений.

**Срок жизни сессии** — Apple инвалидирует cookie примерно раз в 30–90 дней, иногда раньше при смене IP. Это нормально — бот обработает автоматически.

**Advanced Data Protection** — если включена расширенная защита данных iCloud, некоторые типы данных icloudpd не сможет скачать (ограничение Apple).
