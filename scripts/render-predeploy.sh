#!/usr/bin/env bash
set -euo pipefail
# Validate existing data BEFORE the new seat indexes are applied.
python manage.py check_release --database
python manage.py migrate --noinput
python manage.py check_release --database
