#!/usr/bin/env bash
set -euo pipefail
: "${BOT_TOKEN:?Set BOT_TOKEN in your shell}"
: "${WORKER_URL:?Set WORKER_URL, e.g. https://tg-jinni.<subdomain>.workers.dev}"
: "${TELEGRAM_WEBHOOK_SECRET:?Set TELEGRAM_WEBHOOK_SECRET in your shell}"
curl -fsS -X POST \
  "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook" \
  -H 'Content-Type: application/json' \
  --data "$(python3 - <<'PY'
import json, os
print(json.dumps({
  'url': os.environ['WORKER_URL'].rstrip('/') + '/telegram/webhook',
  'secret_token': os.environ['TELEGRAM_WEBHOOK_SECRET'],
  'allowed_updates': ['message', 'pre_checkout_query'],
  'drop_pending_updates': False,
  'max_connections': 40,
}))
PY
)"
echo

# Register the two MVP bot commands.
python3 - <<'PY'
import json, os, urllib.request

def post(method, payload):
    url = f"https://api.telegram.org/bot{os.environ['BOT_TOKEN']}/{method}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req) as resp:
        print(resp.read().decode())

base = os.environ['WORKER_URL'].rstrip('/')
post("setMyCommands", {"commands": [
    {"command": "start", "description": "Открыть TG-Jinni"},
    {"command": "tasks", "description": "Задания"},
]})
post("setChatMenuButton", {"menu_button": {
    "type": "web_app",
    "text": "TG-Jinni",
    "web_app": {"url": base + "/"},
}})
PY

echo "Webhook, bot commands, and menu button configured. Verify with getWebhookInfo if needed."
