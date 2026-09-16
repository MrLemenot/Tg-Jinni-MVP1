import os

os.environ.setdefault("BOT_TOKEN", "123456789:TESTTOKEN")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost/db")
os.environ.setdefault("ADMIN_IDS", "1")
os.environ.setdefault("WEBAPP_URL", "https://example.com")

def test_app_imports():
    import app.main  # noqa: F401

def test_database_url_normalization():
    from app.database.database import normalize_database_url
    assert normalize_database_url("postgresql://u:p@h/db").startswith("postgresql+asyncpg://")
    assert normalize_database_url("postgres://u:p@h/db").startswith("postgresql+asyncpg://")
    assert normalize_database_url("postgresql+psycopg2://u:p@h/db").startswith("postgresql+asyncpg://")
