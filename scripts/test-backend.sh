#!/usr/bin/env bash
set -euo pipefail
export KPN_ENV=test
export SESSION_SECRET="${SESSION_SECRET:-$(python -c 'import secrets;print(secrets.token_urlsafe(48))')}"
python manage.py check --settings=KPN.test_settings
python manage.py makemigrations --check --dry-run --settings=KPN.test_settings
python manage.py test core.tests staff.tests rest_api.tests --settings=KPN.test_settings --noinput
