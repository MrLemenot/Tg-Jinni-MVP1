# TG-Jinni — быстрый деплой в Cloudflare

Это последовательность для первого запуска. Все секреты вводятся в Cloudflare/Wrangler и не попадают в Git.

## 0. Что понадобится

Нужно иметь:

- Telegram-бот и его `BOT_TOKEN`.
- Telegram ID администратора для `ADMIN_IDS`.
- PostgreSQL база данных.
- `PAYMENT_PROVIDER_TOKEN` от платёжного провайдера, настроенного через BotFather.
- Cloudflare аккаунт.
- `uv` и Node.js с `npx wrangler` на компьютере.

## 1. Распаковать проект

Распакуй архив так, чтобы `wrangler.jsonc` лежал прямо в корне проекта. Не загружай ZIP-файл внутрь GitHub-репозитория и не создавай дополнительную папку с тем же проектом внутри проекта.

Корень должен выглядеть примерно так:

```text
DEPLOY.md
README.md
wrangler.jsonc
pyproject.toml
schema.sql
migrations/
src/
public/
scripts/
tests/
```

## 2. Создать Hyperdrive

Hyperdrive подключает Worker к уже существующему PostgreSQL.

Вариант через CLI:

```bash
npx wrangler login
npx wrangler hyperdrive create tg-jinni-db --connection-string="postgres://USER:PASSWORD@HOST:5432/DATABASE"
```

Сохрани выданный ID и замени в `wrangler.jsonc`:

```jsonc
"id": "REPLACE_WITH_HYPERDRIVE_ID"
```

на настоящий ID.

Важно: пароль базы не записывай в `wrangler.jsonc` или Git.

## 3. Подготовить PostgreSQL

Для новой пустой базы:

```bash
export PGURL='postgres://USER:PASSWORD@HOST:5432/DATABASE'
./scripts/schema_apply.sh
```

Для существующей базы TG-Jinni сначала сделай резервную копию, затем:

```bash
export PGURL='postgres://USER:PASSWORD@HOST:5432/DATABASE'
psql "$PGURL" -v ON_ERROR_STOP=1 -f migrations/002_cloudflare_upgrade.sql
```

Не прогоняй `schema.sql` вслепую по рабочей базе: он рассчитан на создание отсутствующих таблиц/индексов, а существующую структуру нужно проверить отдельно.

## 4. Проверить `wrangler.jsonc`

Обязательно проверь:

- `name` — имя Worker.
- `compatibility_date` — дата не старше требуемой для Python Workers/Hyperdrive.
- Hyperdrive `id` — настоящий ID.
- `ADMIN_IDS` — Telegram ID администратора/администраторов.
- `TASK_HOLD_HOURS` — по умолчанию 48.
- `OWNERSHIP_RECHECK_HOURS` — по умолчанию 24.
- `PROMOTION_PACKAGE_PRICE_RUB` — по умолчанию 180.
- `PROMOTION_PACKAGE_IMPRESSIONS` — по умолчанию 4500.

## 5. Секреты

Для полного MVP нужны три секрета:

```bash
uv run pywrangler secret put BOT_TOKEN
uv run pywrangler secret put TELEGRAM_WEBHOOK_SECRET
uv run pywrangler secret put PAYMENT_PROVIDER_TOKEN
```

Введи значения в интерактивных запросах CLI. Не вставляй их в исходники.

Для локальной разработки создай `.dev.vars` из `.dev.vars.example`; файл `.dev.vars` уже находится в `.gitignore`.

## 6. Первый локальный запуск

```bash
uv sync
uv run pywrangler dev
```

После запуска проверь:

```bash
curl http://localhost:8787/
curl http://localhost:8787/healthcheck
```

Для Cron в локальной среде:

```bash
curl "http://localhost:8787/cdn-cgi/local/scheduled?format=json"
```

## 7. Тесты

Перед публикацией:

```bash
python -m compileall -q src tests
PYTHONPATH=. pytest -q
```

В репозитории уже есть CI, который выполняет эти проверки при push и pull request.

## 8. Деплой Worker

```bash
uv run pywrangler deploy
```

Запиши URL, который напечатает Wrangler, например:

```text
https://tg-jinni.<your-subdomain>.workers.dev
```

## 9. Настроить Telegram webhook

Экспортируй три переменные в локальный shell:

```bash
export BOT_TOKEN='...'
export WORKER_URL='https://tg-jinni.<your-subdomain>.workers.dev'
export TELEGRAM_WEBHOOK_SECRET='...'
./scripts/set_webhook.sh
```

Скрипт одновременно:

- ставит `/telegram/webhook`;
- задаёт `secret_token`;
- ограничивает входящие update до `message` и `pre_checkout_query`;
- регистрирует `/start` и `/tasks`;
- ставит кнопку меню `TG-Jinni`, открывающую Mini App.

Проверка:

```bash
curl -fsS "https://api.telegram.org/bot${BOT_TOKEN}/getWebhookInfo"
```

В ответе URL должен заканчиваться на `/telegram/webhook`.

## 10. Mini App

Worker раздаёт Mini App из `public/`.

Пользователь может открыть его через `/start`, кнопку меню или через настроенный Main Mini App в BotFather.

В BotFather укажи тот же HTTPS URL Worker как URL Mini App.

## 11. Telegram-канал рекламодателя

Для проверки собственности пользователь должен быть администратором канала, и бот тоже должен быть администратором канала.

В Mini App:

1. «Мои каналы».
2. «Добавить канал».
3. Указать название и публичный `@username`/`https://t.me/username`.
4. После успешной проверки заявка попадает в модерацию.
5. Админ одобряет канал.

Приватные invite-ссылки вида `t.me/+...` для этого MVP не принимаются, потому что серверу нужен надёжный публичный идентификатор канала для Bot API-проверок.

## 12. Платежи

Сценарий:

```text
создание кампании
      ↓
Telegram invoice
      ↓
pre_checkout_query
      ↓
successful_payment
      ↓
кампания ACTIVE
      ↓
создание задания подписки
```

Клиентский JavaScript никогда не активирует кампанию сам. Единственный источник подтверждения оплаты — серверный Telegram update `successful_payment`.

## 13. Если переносится старая база

Перед миграцией:

1. Сделай backup PostgreSQL.
2. Останови старый polling-бот, чтобы он не конкурировал с webhook.
3. Выполни `migrations/002_cloudflare_upgrade.sql`.
4. Проверь несколько строк в `users`, `entities`, `promotion_campaigns`, `payments`, `user_tasks`.
5. Только после этого переключай Telegram webhook.

## 14. Что считать успешным запуском

Проверка по цепочке:

```text
Worker URL открывается
→ /healthcheck возвращает database=ok
→ /start показывает Mini App-кнопку
→ Mini App проходит initData-аутентификацию
→ админ добавляет тестовый канал и одобряет заявку
→ пользователь видит канал/игру/задание
→ проверка подписки работает
→ hold создаётся
→ Cron позже освобождает или отменяет награду
→ создание promotion выдаёт Telegram invoice
→ после successful_payment кампания становится active
```
