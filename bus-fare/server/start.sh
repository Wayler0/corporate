#!/bin/sh
# Railway start command (see bus-fare/DEPLOY.md)
set -e
python manage.py migrate --noinput
if [ "$SEED_DEMO" = "1" ]; then
  python manage.py seed_demo          # demo data; only adds what is missing
fi
if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
  # Platform login for /admin/ (created once; errors if it already exists)
  python manage.py createsuperuser --noinput --email "${DJANGO_SUPERUSER_EMAIL:-admin@example.com}" 2>/dev/null || true
fi
exec gunicorn config.wsgi --bind "0.0.0.0:${PORT:-8000}" --workers 2 --timeout 30 --access-logfile -
