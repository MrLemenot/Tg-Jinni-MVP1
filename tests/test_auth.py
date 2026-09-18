import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest
from fastapi import HTTPException

from src.auth import validate_telegram_init_data


def signed(bot_token: str, user: dict, auth_date: int | None = None) -> str:
    auth_date = auth_date or int(time.time())
    fields = {"auth_date": str(auth_date), "query_id": "demo", "user": json.dumps(user, separators=(",", ":"))}
    check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(key, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def test_valid_init_data():
    token = "123456:abc"
    user = {"id": 42, "first_name": "Test"}
    assert validate_telegram_init_data(signed(token, user), token)["id"] == 42


def test_bad_hash_rejected():
    token = "123456:abc"
    user = {"id": 42}
    data = signed(token, user).replace("hash=", "hash=bad")
    with pytest.raises(HTTPException):
        validate_telegram_init_data(data, token)


def test_documented_telegram_vector():
    token = "5768337691:AAH5YkoiEuPk8-FZa32hStHTqXiLPtAEhx8"
    init_data = (
        "query_id=AAHdF6IQAAAAAN0XohDhrOrc&"
        "user=%7B%22id%22%3A279058397%2C%22first_name%22%3A%22Vladislav%22%2C%22last_name%22%3A%22Kibenko%22%2C%22username%22%3A%22vdkfrost%22%2C%22language_code%22%3A%22ru%22%2C%22is_premium%22%3Atrue%7D&"
        "auth_date=1662771648&"
        "hash=c501b71e775f74ce10e377dea85a7ea24ecd640b223ea86dfe453e0eaed2e2b2"
    )
    user = validate_telegram_init_data(init_data, token, max_age=2_000_000_000)
    assert user["id"] == 279058397
