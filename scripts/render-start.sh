#!/usr/bin/env bash
set -euo pipefail
# Works without Render's paid pre-deploy feature. A PostgreSQL advisory lock
# serializes overlapping instance startups before Gunicorn starts.
python manage.py release_migrate
exec gunicorn KPN.wsgi:application --bind "0.0.0.0:${PORT:-8000}" --workers "${WEB_CONCURRENCY:-3}" --timeout 60 --access-logfile - --error-logfile -
