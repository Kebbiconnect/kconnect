#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python manage.py check
python manage.py migrate --check
python manage.py run_editorial --max-jobs "${KPN_EDITORIAL_MAX_JOBS:-15}" --max-seconds 600
