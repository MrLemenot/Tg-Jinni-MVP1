#!/usr/bin/env bash
set -euo pipefail
: "${PGURL:?Set PGURL to the PostgreSQL URL}"
psql "$PGURL" -v ON_ERROR_STOP=1 -f schema.sql
