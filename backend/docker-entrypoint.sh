#!/bin/sh
# Повторяем миграции, пока Postgres не поднимется (depends_on + healthcheck не гарантируют готовность драйвера с хоста volume).
cd /app || exit 1

max_attempts=30
attempt=0
until alembic upgrade head; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge "$max_attempts" ]; then
    echo "alembic: база недоступна после $max_attempts попыток" >&2
    exit 1
  fi
  echo "alembic: ожидание БД ($attempt/$max_attempts)..."
  sleep 2
done

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
