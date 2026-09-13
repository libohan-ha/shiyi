#!/bin/sh
set -eu
cd /app/backend
/app/backend/.venv/bin/alembic upgrade head
exec "$@"
