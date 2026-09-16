# TG Jinni MVP

Production-oriented MVP for the Telegram Mini App / bot.

## Secrets and configuration

**No real credentials belong in Git.** The application reads secrets from environment variables. For local development:

```bash
cp .env.example .env
# edit .env and set BOT_TOKEN and other secrets
```

`.env` is ignored by Git. Only `.env.example` is committed.

### Render

`render.yaml` contains only variable names and non-sensitive defaults. Secret variables use `sync: false` and must be entered in the Render Dashboard during the initial Blueprint setup. Never replace those placeholders with real tokens.

Required production secrets:

- `BOT_TOKEN`
- `DATABASE_URL`
- `WEBAPP_URL`
- `ADMIN_IDS`
- `PAYMENT_PROVIDER_TOKEN` (when payments are enabled)
- `PAYMENT_WEBHOOK_SECRET` (when payment webhooks are enabled)

### GitHub secret protection

The repository includes a GitHub Actions Gitleaks scan on every push and pull request. Also enable GitHub Secret Protection / Push Protection for the repository so supported secrets are blocked before they reach the repository.

## Local run

```bash
cp .env.example .env
# edit .env

docker compose up --build
```

API: `http://localhost:8000/docs`
Health: `http://localhost:8000/healthcheck`

## Security rule

If a real bot token has ever been committed to GitHub, deleting it from the latest file is not enough: rotate/revoke that token in BotFather and remove the secret from Git history before treating the repository as clean.

## Render deployment notes

The service is a Docker Web Service. PostgreSQL should be a separate Render database in the same region.
Set `BOT_TOKEN`, `ADMIN_IDS`, and `DATABASE_URL` in the service Environment settings. `WEBAPP_URL` may be left empty on Render because the app falls back to Render's `RENDER_EXTERNAL_URL`.

`DATABASE_URL` is normalized at runtime: `postgres://`, `postgresql://`, and `postgresql+psycopg2://` are converted to `postgresql+asyncpg://`, so Render's native Postgres URL works with SQLAlchemy async without installing psycopg2.

The Web Service runs FastAPI, the aiogram polling bot, and the subscription hold worker in the same process for the MVP. Run only one instance while using polling to avoid Telegram update conflicts.

The Mini App authenticates API calls with Telegram `initData`; the old insecure `X-Telegram-Id` header is no longer accepted.


## Render deployment

Create one Docker Web Service from the repository root. Set these Environment Variables in Render (never commit real values):

- `BOT_TOKEN` — Telegram bot token.
- `ADMIN_IDS` — comma-separated Telegram user IDs for administrators.
- `DATABASE_URL` — Render PostgreSQL **Internal Database URL**.
- `WEBAPP_URL` — optional; leave empty to use Render's `RENDER_EXTERNAL_URL`.
- `ENVIRONMENT=production`.

The application normalizes Render's `postgresql://` URL to SQLAlchemy's `postgresql+asyncpg://` automatically. No `psycopg2` package is required.

Do not deploy with multiple Uvicorn workers: Telegram long polling must have a single consumer.
