# TG-Jinni — Cloudflare Workers Edition

TG-Jinni is migrated from a long-running FastAPI + aiogram polling process to a Cloudflare Python Worker.

## What changed

- **Telegram updates:** webhook instead of `getUpdates` polling.
- **Backend:** FastAPI through the Cloudflare Python Workers ASGI adapter.
- **PostgreSQL:** Cloudflare Hyperdrive + `asyncpg`; no SQLAlchemy async ORM.
- **Mini App:** Workers Static Assets from `public/`.
- **Background jobs:** Cloudflare Cron Trigger every hour for reward-hold finalization and channel ownership re-checks.
- **Secrets:** `BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, and `PAYMENT_PROVIDER_TOKEN` are required Worker Secrets for the full paid-promotion MVP.
- **Moderation:** admin endpoints for pending channels.
- **Payments:** Telegram invoice links in RUB; campaign activates only after `successful_payment`.
- **Ownership:** channel is accepted only when both the user and the bot are administrators.
- **Task reward:** subscription is checked through Telegram Bot API, then reward is held and rechecked before release.

Cloudflare documents Python Workers, FastAPI, Hyperdrive + Python and Cron Triggers here:
- https://developers.cloudflare.com/workers/languages/python/
- https://developers.cloudflare.com/workers/languages/python/packages/fastapi/
- https://developers.cloudflare.com/hyperdrive/examples/python-workers/
- https://developers.cloudflare.com/workers/configuration/cron-triggers/

## Project layout

```text
src/
  main.py            FastAPI routes + WorkerEntrypoint + Cron
  auth.py            Telegram Mini App initData validation
  bot.py             Telegram webhook update handling + payments
  config.py          Worker env/secrets parsing
  db.py              Hyperdrive/asyncpg connection helper
  game_engine.py     Bayesian game engine
  telegram_api.py    Telegram Bot API client via Workers fetch()
public/
  index.html
  app.js
schema.sql           PostgreSQL schema + starter questions/items
wrangler.jsonc       Cloudflare Worker configuration
scripts/
  set_webhook.sh     one-shot webhook setup
  schema_apply.sh    apply schema to PostgreSQL
```

## 1. Create the Hyperdrive configuration

Your PostgreSQL database must be reachable from Hyperdrive. Hyperdrive can connect to an existing PostgreSQL database. In Cloudflare Dashboard open **Workers & Pages → Hyperdrive → Create configuration** and point it at the database.

Or use Wrangler:

```bash
npx wrangler hyperdrive create tg-jinni-db --connection-string="postgres://USER:PASSWORD@HOST:5432/DATABASE"
```

Copy the resulting Hyperdrive configuration ID into `wrangler.jsonc` in place of `REPLACE_WITH_HYPERDRIVE_ID`.

Do not put the database password into Git.

## 2. Initialize the database

For a fresh database, use `schema.sql`. For an existing TG-Jinni PostgreSQL database created by the old SQLAlchemy version, apply `migrations/002_cloudflare_upgrade.sql` after a backup, then compare the remaining schema with `schema.sql`.

Use a PostgreSQL client against the same database that Hyperdrive will use:

```bash
export PGURL='postgres://USER:PASSWORD@HOST:5432/DATABASE'
./scripts/schema_apply.sh
```

Do this against a fresh database first. For an existing TG-Jinni database, compare the current schema with `schema.sql` before running it.

## 3. Authenticate Wrangler

```bash
npx wrangler login
```

The Python Worker toolchain uses `pywrangler`, which is provided through `workers-py` and is run through `uv`.

## 4. Install Python Worker tooling

Install `uv` and Node.js on your computer if you do not already have them.

Then from the project root:

```bash
uv sync
uv run pywrangler --help
```

## 5. Configure Worker secrets

Never store these values in Git or `wrangler.jsonc`:

```bash
uv run pywrangler secret put BOT_TOKEN
uv run pywrangler secret put TELEGRAM_WEBHOOK_SECRET
uv run pywrangler secret put PAYMENT_PROVIDER_TOKEN
```

`PAYMENT_PROVIDER_TOKEN` is required because paid promotion is part of the production MVP. Obtain it from the payment provider configured in BotFather.

`TELEGRAM_WEBHOOK_SECRET` may be any random 1–256 character string using only `A-Z`, `a-z`, `0-9`, `_`, `-`.

## 6. Set your admin Telegram IDs

Edit `wrangler.jsonc`:

```jsonc
"vars": {
  "ADMIN_IDS": "123456789,987654321",
  ...
}
```

Or add the variable in the Cloudflare Worker dashboard.

## 7. Local development

For local development, create `.dev.vars` from `.dev.vars.example` and fill in local-only secrets. Keep `.dev.vars` out of Git.

Run:

```bash
uv run pywrangler dev --test-scheduled
```

Then test:

```bash
curl http://localhost:8787/healthcheck
curl 'http://localhost:8787/cdn-cgi/local/scheduled?format=json&cron=*+*+*+*+*'
```

## 8. Deploy

```bash
uv run pywrangler deploy
```

Cloudflare will print the Worker URL, for example:

```text
https://tg-jinni.<your-subdomain>.workers.dev
```

## 9. Set Telegram webhook

In your shell:

```bash
export BOT_TOKEN='DO_NOT_COMMIT_THIS'
export WORKER_URL='https://tg-jinni.<your-subdomain>.workers.dev'
export TELEGRAM_WEBHOOK_SECRET='YOUR_WEBHOOK_SECRET'
./scripts/set_webhook.sh
```

Check Telegram:

```bash
curl -fsS "https://api.telegram.org/bot${BOT_TOKEN}/getWebhookInfo"
```

The webhook URL must be HTTPS. Telegram sends updates to it using POST requests and can include `X-Telegram-Bot-Api-Secret-Token` when `secret_token` is configured.

## 10. Admin moderation

After `ADMIN_IDS` is configured, an admin user sees an **Админка** button in the Mini App. The moderation screen lists pending channels and lets the admin approve or reject them. The backend still enforces the admin ID server-side.

## 11. Mini App

The Worker serves `public/index.html` at `/`. The bot's `/start` command sends a Web App button pointing to the same Worker URL.

Before using a custom domain, you can run the MVP entirely on the `workers.dev` URL.

For production, configure the bot's Mini App/Main Mini App URL in BotFather to the same HTTPS Worker URL.

## 12. Payments

The promotion flow is:

1. Owner adds a public channel.
2. Backend verifies user is a channel administrator.
3. Backend verifies the bot is a channel administrator.
4. Admin approves the channel.
5. Owner creates a promotion campaign.
6. Backend creates a Telegram invoice link for **180 RUB / 4500 impressions**.
7. Mini App opens that invoice.
8. Telegram sends `pre_checkout_query`; backend validates the pending payment.
9. Telegram sends `successful_payment`; backend marks payment paid, activates the campaign, and creates the subscription task.

A campaign must never be activated by a client-side "demo" endpoint.

## 13. Important security notes

- Telegram Mini App requests are authenticated with signed `initData`; the raw `initDataUnsafe` object is never trusted.
- Do not use a custom `X-Telegram-Id` header for authentication.
- Keep `BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET` and `PAYMENT_PROVIDER_TOKEN` as Worker Secrets when payments are enabled.
- If a bot token was ever committed to GitHub, revoke/rotate it in BotFather.
- Keep exactly one webhook endpoint for the production bot. Do not run polling at the same time.

## 14. Current production caveats

- Hyperdrive + Python is currently documented by Cloudflare as **beta**.
- The game engine uses default question weights of `0.5` until channel-specific weights are populated. The schema already contains `entity_question_weights` for later tuning.
- The payment provider token depends on the payment provider configured for the bot in BotFather; this project intentionally refuses to fake a successful payment.
- The current shop contains one demonstration item; inventory/purchase routes can be extended without changing the Worker/Hyperdrive architecture.
