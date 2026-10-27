# 📋 Бот инвентаризации

Telegram-бот для учёта ИТ-оборования в поликлиниках.

## ✨ Возможности

| Функция | Описание |
|---|---|
| 🖥️ **Учёт техники** | Добавление записей: системные блоки, мониторы, принтеры, ноутбуки и др. |
| ✏️ **Редактирование** | Полноценное редактирование существующих записей: поиск по ИНВ / ID / поликлинике / имени ПК, изменение отдельных полей, удаление записей |
| 📊 **Экспорт в Excel** | Выгрузка всей базы в `.xlsx` с группировкой по поликлиникам (структура листа совпадает со шаблоном «Инвентаризация.xlsx») |
| 🔍 **Умный поиск** | Поиск по инв. номеру, ID, имени ПК, поликлинике |
| 👥 **RBAC** | Разграничение прав между обычными пользователями и администраторами |
| 💾 **Локальное хранение** | Данные хранятся в SQLite — без облаков |

## 📦 Поля инвентаризации

Поля приведены в соответствие со столбцами шаблона `Инвентаризация.xlsx`:

| XLSX колонка | Поле в боте (БД) | Обязательно |
|---|---|---|
| № кабинета | `cabinet` | ✅ |
| Тип (сист блок/монитор/принтер) | `tech_type` | ✅ (выбор из меню) |
| Марка, модель | `tech` | ✅ |
| Инв № | `inv_number` (`inv`) | ✅ |
| Сер № | `serial` | ✅ |
| ОС | `os` | — |
| Dr Web | `drweb` | — |
| IP-адрес | `ip` | — |
| **Имя ПК** | `pc_name` | — |
| **Физический MAC** | `mac_phys` | — |
| **Реальный MAC** | `mac_real` | — |
| **Характеристики** | `specs` | — |
| Дополнительно | `note` | — |

> ⚠️ Поля **Имя ПК**, **Физический MAC**, **Реальный MAC**, **Характеристики** и **Тип** добавлены в этой версии. При первом запуске бота на существующей базе выполняется автоматическая миграция (`ALTER TABLE … ADD COLUMN`) — старые записи сохраняются.

## 🚀 Быстрый старт

```bash
# 1. Установить зависимости
pip install -r requirements.txt

# 2. Настроить переменные окружения
cp .env.example .env
#    BOT_TOKEN=...
#    ALLOWED_CHAT_IDS=123456789,987654321
#    ADMIN_CHAT_IDS=123456789

# 3. Запустить бота
python bot.py
```

## 📱 Использование

### Добавление записи
1. `/start` → «📋 Начать инвентаризацию»
2. Выбрать поликлинику
3. Ввести номер кабинета
4. Выбрать тип техники (Системный блок / Монитор / Принтер / Ноутбук / Другое)
5. Заполнить поля (с проверкой данных перед сохранением)
6. ✅ Сохранить

### Редактирование записи
1. «✏️ Редактировать»
2. Выбрать способ поиска:
   - 🏷️ По инвентарному номеру
   - 🔢 По ID
   - 🏥 По поликлинике (список с пагинацией)
   - 💻 По имени компьютера (частичный поиск)
   - 🔍 **Глобальный поиск** — один запрос ищет сразу по инвентарному / серийному / имени ПК / марке / кабинету / характеристикам / ОС / примечанию
3. В карточке записи выбрать поле → ввести новое значение → сохраняется сразу в БД
4. Можно удалить запись (с подтверждением)

### Аудиторский фильтр (только админ)
В админ-меню кнопка **«🔍 Проблемные записи»** — показывает записи с конкретной проблемой:
- 💻 Без имени компьютера (только ПК / ноутбук / принтер)
- 🌐 Без IP-адреса
- 📡 Без MAC-адресов
- 🛡️ Dr.Web: «Нет лицензии» или «Нет соединения»
- ⚠️ Физический MAC ≠ Реальный MAC
- ⚙️ Без характеристик (только ПК / ноутбук)

Клик по записи открывает её карточку для правки.

### Подтверждение при выходе
Если в середине ввода записи нажать «В меню» или «Отменить» — бот спросит:
«⚠️ У вас есть несохранённые данные. Точно выйти?»
с кнопками «🗑️ Да, выйти» / «✏️ Продолжить ввод».

## 🌐 Веб-панель (`web_app.py`)

Полностью переработана на современном стеке: **FastAPI + Tailwind CSS + HTMX + Chart.js**.

Дополнительно к боту — отдельное FastAPI-приложение для просмотра статистики
и записей в браузере. Запускается отдельной командой:

```bash
# Способ 1 (проще всего): python web_app.py — запускает uvicorn внутри себя
python web_app.py

# Способ 2: через uvicorn как модуль (если команды uvicorn нет в PATH — это норма на Windows)
python -m uvicorn web_app:app --host 127.0.0.1 --port 5000

# Способ 3: если uvicorn установлен и доступен как команда
uvicorn web_app:app --host 127.0.0.1 --port 5000
```

> ⚠️ **Если на Windows** `uvicorn` не распознаётся как команда — это нормально,
> `pip install` кладёт `uvicorn.exe` в `Scripts/` папку Python, которой часто
> нет в `PATH`. Используйте `python web_app.py` (Способ 1) — это надёжнее.

Откройте в браузере `http://127.0.0.1:5000/`. Бот (`bot.py`) и веб-панель
(`web_app.py`) запускаются **отдельно** — оба читают одну и ту же SQLite-БД,
не мешая друг другу.

### Возможности
- **Дашборд** (`/`) — 8 KPI (всего устройств / с IP / с именем ПК / с MAC / с характеристиками / с ОС / поликлиники),
  4 графика (по поликлиникам / типам техники / ОС / статусу Dr.Web), блок аудита, таблица последних 10 записей.
- **База** (`/inventory`) — таблица с фильтрами:
  - **HTMX-поиск без перезагрузки** — набираете текст, таблица обновляется мгновенно
  - Фильтр по поликлинике и типу техники
  - Удаление записи через HTMX (строка исчезает без перезагрузки)
- **Аудит** (`/audit`) — список 6 категорий проблемных записей с количеством.
  Клик по категории → список записей (с пагинацией по 25).
- **Карточка записи** (`/item/{id}`) — полная информация по одной записи,
  с предупреждением, если физ. MAC ≠ реал. MAC.
- **Экспорт в Excel** (`/export`) — выгрузка всей базы.
- **REST API** (Swagger UI на `/api/docs`):
  - `GET /api/stats` — общая статистика
  - `GET /api/items?search=...&clinic=...&tech_type=...&limit=...` — список записей с фильтрами
  - `GET /api/items/{id}` — одна запись
  - `GET /api/audit/{category}` — записи категории аудита

### Авторизация по паролю (cookie-сессии)
Если в `.env` задана переменная `WEB_PANEL_PASSWORD` — все страницы защищены
формой входа с cookie-сессией (7 дней). Если не задана — панель открыта.
**Не используйте открытую панель на публичном сервере!**

- `/login` — форма входа (POST с полем `password`)
- `/logout` — выход (POST, очищает сессию)
- HTMX-запросы без авторизации возвращают 401 (для JS-обработки)

### Конфигурация (`.env`)
```
# Опционально — пароль для веб-панели (если не задан, панель открыта)
WEB_PANEL_PASSWORD=secret_password

# Хост и порт:
#   127.0.0.1 (по умолчанию) — доступ только с этой машины
#   0.0.0.0                  — доступ из сети (используйте с паролем!)
WEB_PANEL_HOST=127.0.0.1
WEB_PANEL_PORT=5000
```

### Запуск в продакшене
Для продакшена — несколько воркеров uvicorn:

```bash
uvicorn web_app:app --host 127.0.0.1 --port 5000 --workers 4
```

Или за Nginx (для HTTPS и.pub-доступа):
```nginx
location / {
    proxy_pass http://127.0.0.1:5000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

### Технологии
- **FastAPI** — асинхронные эндпоинты, OpenAPI/Swagger UI из коробки
- **Jinja2** — HTML-шаблоны
- **Tailwind CSS** (через CDN) — современная стилизация, тёмная тема
- **HTMX** — интерактивность (живой поиск, удаление без перезагрузки) без JS-фронтенда
- **Chart.js** — графики на дашборде
- **Cookie-сессии** (itsdangerous) — авторизация по паролю

## 🔐 Безопасность

### Что реализовано

1. **Пароль через bcrypt-хэш** — `WEB_PANEL_PASSWORD` можно хранить как `$2b$12$...` (хэш), а не как plain text. При утечке `.env` пароль остаётся безопасным.
2. **Cookie с флагами безопасности** — `HttpOnly=True` (не доступна из JS), `SameSite=Strict` (не отправляется на сторонние сайты), `Secure=True` при `WEB_PANEL_FORCE_HTTPS=true`.
3. **Сессия 8 часов** — истекает через рабочий день, не через 7 дней как раньше.
4. **Rate limiting на `/login`** — 5 попыток за 60 секунд с одного IP, потом блок на 5 минут. Защита от брутфорса.
5. **CSRF-токены на POST/DELETE** — в форме входа, удаления записи. HTMX автоматически добавляет `X-CSRF-Token` из meta-тега.
6. **Security headers на все ответы**:
   - `X-Frame-Options: DENY` — защита от clickjacking
   - `X-Content-Type-Options: nosniff` — браузер не угадывает MIME
   - `Referrer-Policy: strict-origin-when-cross-origin`
   - `Permissions-Policy: geolocation=(), microphone=(), camera=()`
   - `Content-Security-Policy` — белый список источников (Tailwind, HTMX, Chart.js, Bootstrap Icons)
   - `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload` (только при HTTPS)
7. **Swagger UI `/api/docs` и `/api/openapi.json` закрыты** под авторизацию (если пароль задан).
8. **Файл БД с правами `0o600`** — только владелец читает/пишет (на Linux/macOS).
9. **Constant-time сравнение паролей** — защита от timing-атак (через `secrets.compare_digest`).

### Как сгенерировать bcrypt-хэш пароля

```bash
python web_app.py --hash-password
```

Запустит интерактивную утилиту:
```
🔐 Генерация bcrypt-хэша пароля для .env
   (пароль не отображается при вводе)

Введите пароль: ********
Повторите пароль: ********

✅ Готово. Скопируйте эту строку в .env:

WEB_PANEL_PASSWORD=$2b$12$N5XkJrU9kZ4wL2eEa1iJRODe...

💡 Также рекомендуем (если панель за HTTPS):
   WEB_PANEL_FORCE_HTTPS=true
```

Скопируйте строку в `.env`. Если пароль всё-таки хранится как plain text — бот выведет предупреждение в лог при запуске.

### HTTPS через обратный прокси (Caddy — самый простой)

Caddy — это автоматически Let's Encrypt-сертификаты, минимальная конфигурация.

**`Caddyfile`:**
```
inventory.example.com {
    reverse_proxy 127.0.0.1:5000
}
```

Запуск:
```bash
# Установить Caddy: https://caddyserver.com/docs/install
caddy run
```

В `.env`:
```
WEB_PANEL_HOST=127.0.0.1
WEB_PANEL_PORT=5000
WEB_PANEL_PASSWORD=$2b$12$...   # bcrypt-хэш
WEB_PANEL_FORCE_HTTPS=true        # включает Secure cookie + HSTS
```

Caddy сам получит сертификат и продлит. Бот запускается на 127.0.0.1 (без внешнего доступа), Caddy проксирует и терминирует TLS.

### HTTPS через Nginx

Получить сертификат через `certbot`:
```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d inventory.example.com
```

Конфигурация Nginx:
```nginx
server {
    listen 443 ssl http2;
    server_name inventory.example.com;

    ssl_certificate /etc/letsencrypt/live/inventory.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/inventory.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

server {
    listen 80;
    server_name inventory.example.com;
    return 301 https://$host$request_uri;
}
```

Запуск FastAPI за Nginx:
```bash
WEB_PANEL_FORCE_HTTPS=true WEB_PANEL_HOST=127.0.0.1 WEB_PANEL_PORT=5000 \
    uvicorn web_app:app --host 127.0.0.1 --port 5000 --workers 4
```

`X-Forwarded-For` нужен для rate limiting — иначе все запросы приходят с IP 127.0.0.1.

### Конфигурация безопасности (`.env`)

```bash
# Пароль для веб-панели:
#   1) bcrypt-хэш (рекомендуется) — начинается с $2a$, $2b$, $2y$
#      Сгенерировать: python web_app.py --hash-password
#      Пример: WEB_PANEL_PASSWORD=$2b$12$N5XkJrU9kZ4wL2eEa1iJRODe...
#   2) plain text (для совместимости, выводит warning при запуске)
WEB_PANEL_PASSWORD=$2b$12$...

# Хост и порт:
#   127.0.0.1 (по умолчанию) — доступ только с этой машины (рекомендуется для localhost)
#   0.0.0.0                  — доступ из сети (используйте ТОЛЬКО с паролем + HTTPS!)
WEB_PANEL_HOST=127.0.0.1
WEB_PANEL_PORT=5000

# Включить secure cookie + HSTS (использовать при доступе через HTTPS)
WEB_PANEL_FORCE_HTTPS=true
```

## 🚀 Деплой на VPS через Docker

Всё уже обёрнуто в Docker. Один образ, `docker-compose.yml` поднимает 4 сервиса.

### Файлы

| Файл | Назначение |
|---|---|
| `Dockerfile` | Один образ для бота и веб-панели |
| `docker-compose.yml` | Оркестрация: bot + web + redis (опц.) + caddy (опц.) |
| `.dockerignore` | Исключает `__pycache__`, `.env`, `data/`, `logs/` из образа |
| `.env.example` | Шаблон конфигурации — скопируйте в `.env` |
| `Caddyfile` | Конфигурация HTTPS reverse proxy для Caddy |

### Шаги для деплоя на VPS

**1. Подготовка VPS** (один раз):
```bash
# На VPS с Ubuntu/Debian:
ssh root@your-vps
apt update && apt upgrade -y
# Установить Docker и Docker Compose:
curl -fsSL https://get.docker.com | sh
systemctl enable --now docker
```

**2. Залить код на VPS** — на машине разработчика:

```bash
# Способ 1: через git clone (если у вас есть репозиторий на GitHub)
ssh root@your-vps
cd /opt
git clone https://github.com/ваш-логин/inventory_bot.git inventory_bot

# Способ 2: если репозиторий приватный — использовать Personal Access Token
# Вставьте ваш токен в URL:
git clone https://TOKEN@github.com/ваш-логин/inventory_bot.git inventory_bot

# Способ 3: через scp (если git не используете)
scp -r inventory_bot-master/ root@your-vps:/opt/inventory_bot
```

**3. Настроить `.env` на VPS**:
```bash
ssh root@your-vps
cd /opt/inventory_bot
cp .env.example .env

# Отредактируйте .env:
nano .env
#   BOT_TOKEN=...           (от @BotFather)
#   ALLOWED_CHAT_IDS=...    (ваш chat_id)
#   ADMIN_CHAT_IDS=...      (ваш chat_id)
#   WEB_PANEL_PASSWORD=$2b$12$...   (сгенерировать см. ниже)

# Сгенерировать bcrypt-хэш пароля (на машине с Python):
# python web_app.py --hash-password
# Скопировать вывод в WEB_PANEL_PASSWORD
```

**4. Сгенерировать bcrypt-хэш пароля для веб-панели**:
```bash
# Если на машине разработчика установлен Python:
python web_app.py --hash-password
# Или на VPS через Docker:
docker compose run --rm web python web_app.py --hash-password
```

**5. Настроить домен и DNS** (для HTTPS через Caddy):
- Настроить A-запись в DNS: `inventory.example.com → IP_вашего_VPS`
- Отредактировать `Caddyfile`:
  ```
  inventory.example.com {
      reverse_proxy web:5000
      ...
  }
  ```
- В `.env`:
  ```
  WEB_PANEL_FORCE_HTTPS=true
  ```

**6. Запустить**:
```bash
# Сборка образов + запуск всех сервисов:
docker compose up -d --build

# Проверить статус:
docker compose ps
# NAME                STATUS              PORTS
# inventory_bot       Up (healthy)        -
# inventory_web        Up (healthy)        127.0.0.1:5000->5000/tcp
# inventory_redis     Up (healthy)        6379/tcp
# inventory_caddy     Up (healthy)        0.0.0.0:80->80, 0.0.0.0:443->443/tcp

# Логи:
docker compose logs -f bot
docker compose logs -f web
docker compose logs -f caddy

# Остановка:
docker compose down

# Обновление кода (после git pull):
docker compose up -d --build

# Полный сброс (с удалением Redis и Caddy volumes — осторожно!):
docker compose down -v
```

### Конфигурация без Caddy (только бот + панель на localhost)

Если не нужен HTTPS — закомментируйте сервис `caddy` в `docker-compose.yml`. Веб-панель будет доступна только по `127.0.0.1:5000` на самом VPS. Чтобы зайти снаружи — SSH-туннель:
```bash
ssh -L 5000:127.0.0.1:5000 root@your-vps
# Локально открыть http://127.0.0.1:5000
```

### Конфигурация без Redis

Если не используете `REDIS_URL` — закомментируйте сервис `redis` в `docker-compose.yml`. Бот будет работать на `MemoryStorage` (состояния теряются при перезапуске). Это нормально для небольших инсталляций.

### Бэкапы

```bash
# Бэкап БД:
docker compose exec bot cp /app/data/inventory.db /app/data/inventory_$(date +%Y%m%d).db
# Скачать с VPS:
scp root@your-vps:/opt/inventory_bot/data/inventory_20260101.db .

# Авто-бэкап через cron на VPS:
echo "0 3 * * * cd /opt/inventory_bot && docker compose exec -T bot cp /app/data/inventory.db /app/data/inventory_\$(date +\%Y\%m\%d).db" | crontab -
```

### Обновление

Если проект на GitHub — обновление одной строкой:
```bash
cd /opt/inventory_bot
git pull
docker compose up -d --build
docker image prune -f  # очистить старые образы (опционально)
```

`docker compose up -d --build` автоматически пересоберёт образ, если изменился код. Контейнеры `bot` и `web` перезапустятся с новой версией, `redis` и `caddy` продолжат работать без изменений. Данные в `data/` сохранятся.

Если нет git — обновление через scp:
```bash
# На локальной машине:
scp -r inventory_bot-master/ root@your-vps:/opt/inventory_bot
# На VPS:
cd /opt/inventory_bot
docker compose up -d --build
```

### Восстановление при сбое

```bash
# Проверить, что запущено:
docker compose ps

# Перезапустить конкретный сервис:
docker compose restart bot
docker compose restart web

# Полный перезапуск с пересборкой:
docker compose down
docker compose up -d --build
```

## 📁 Структура проекта

```
inventory_bot/
├── 📄 bot.py                # Точка входа
├── 📄 config.py             # Переменные окружения + список поликлиник
├── 📄 database.py           # CRUD + миграция схемы БД
├── 📄 excel_export.py       # Экспорт в .xlsx (один лист = одна поликлиника)
├── 📄 excel_import.py       # Импорт из .xlsx (маппинг листов/заголовков)
├── 📄 web_app.py            # FastAPI веб-панель + безопасность
├── 📄 requirements.txt      # Список зависимостей
│
├── 📂 bot_core/             # Ядро бота
│   ├── 📄 constants.py      # TECH_TYPES, DRWEB_CHOICES, EDITABLE_FIELDS
│   ├── 📄 states.py         # FSM-состояния
│   ├── 📄 flow.py           # Промпты полей, карточка подтверждения
│   ├── 📄 keyboards.py      # Inline-клавиатуры
│   └── 📄 access.py         # Проверка доступа по chat_id
│
├── 📂 handlers/             # Обработчики команд
│   ├── 📄 common.py         # /start, /menu, /cancel, skip, back + подтверждение выхода
│   ├── 📄 inventory.py      # Ввод полей новой записи + дубликаты + MAC
│   ├── 📄 editing.py        # Редактирование СУЩЕСТВУЮЩИХ записей
│   ├── 📄 audit.py          # Аудиторский фильтр (проблемные записи)
│   ├── 📄 import_xlsx.py    # Импорт из Excel через Telegram
│   ├── 📄 admin.py          # Статистика, удаление, экспорт, пользователи
│   └── 📄 errors.py         # Глобальный обработчик ошибок + ротация логов
│
├── 📂 templates/            # HTML-шаблоны веб-панели (Jinja2)
│   ├── 📄 base.html         # Layout (Tailwind + HTMX)
│   ├── 📄 dashboard.html    # Дашборд с графиками
│   ├── 📄 inventory.html    # Список записей + HTMX-поиск
│   ├── 📄 inventory_table.html  # Partial таблицы (HTMX)
│   ├── 📄 audit.html        # Аудит
│   ├── 📄 item_detail.html  # Карточка записи
│   └── 📄 login.html        # Форма входа
│
├── 📂 static/               # CSS веб-панели
│   └── 📄 app.css
│
├── 📂 data/                 # SQLite БД (создаётся автоматически, в .gitignore)
│   └── 📄 .gitkeep
├── 📂 logs/                 # Логи ошибок (в .gitignore)
│   └── 📄 .gitkeep
├── 📂 labels/               # Бывшие штрих-коды (пустая, в .gitignore)
│   └── 📄 .gitkeep
│
├── 📄 Dockerfile            # Один образ для bot.py + web_app.py
├── 📄 docker-compose.yml    # 4 сервиса: bot + web + redis (опц.) + caddy (опц.)
├── 📄 .dockerignore         # Что исключить из Docker-образа
├── 📄 .gitignore            # Что исключить из git
├── 📄 .env.example          # Шаблон .env — КОМИТИТЬ, изменённый .env НЕ коммитить!
├── 📄 Caddyfile             # Конфиг HTTPS reverse proxy
└── 📄 README.md            # Эта документация
```

## 🔒 Безопасность репозитория

Что **коммитить** в GitHub (можно публичный):
- ✅ Весь код: `bot.py`, `web_app.py`, `handlers/`, `bot_core/`, `templates/`, `static/`
- ✅ `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.gitignore`
- ✅ `.env.example` (только шаблон, без реальных значений)
- ✅ `Caddyfile` (только структура, без домена — или замените на плейсхолдер)
- ✅ `README.md`
- ✅ `requirements.txt`

Что **НЕ коммитить** (в `.gitignore`):
- ❌ `.env` (содержит `BOT_TOKEN`, пароль веб-панели, chat_id!)
- ❌ `data/*.db` (БД с инвентарём)
- ❌ `logs/*.jsonl` (логи с chat_id пользователей)
- ❌ `__pycache__/`
- ❌ `.venv/` / `venv/`

Проверить, что `.env` не закоммичен:
```bash
git status .env
# Если не виден — значит в .gitignore и не закоммичен. ✅

# Если случайно закоммитили .env ранее — удалить из истории:
git rm --cached .env
git commit -m "remove .env from tracking"
# ⚠️ ВНИМАНИЕ: BOT_TOKEN всё ещё в истории git! Нужно перегенерировать токен
# у @BotFather, если репозиторий публичный.
```

Если репозиторий **приватный** — на VPS для `git clone` нужен доступ:

```bash
# Вариант 1: Personal Access Token (проще)
# Создать на https://github.com/settings/tokens (классический, scope: repo)
git clone https://TOKEN@github.com/ваш-логин/inventory_bot.git

# Вариант 2: SSH-ключ
# На VPS сгенерировать ключ:
ssh-keygen -t ed25519 -C "vps@inventory"
# Вывести публичный:
cat ~/.ssh/id_ed25519.pub
# Скопировать на https://github.com/settings/keys
# Клонировать через SSH:
git clone git@github.com:ваш-логин/inventory_bot.git
```

