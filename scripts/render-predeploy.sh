#!/usr/bin/env bash
set -euo pipefail
# Validate existing data BEFORE the new seat indexes are applied.
# NOTE: render.yaml does not use this script (pre-deploy is a paid Render
# feature); the live flow is scripts/render-start.sh -> release_migrate,
# which runs the same sequence under a PostgreSQL advisory lock. The two
# are kept in step: any change to the release sequence must land in both.
python manage.py check_release --database
python manage.py migrate --noinput
python manage.py check_release --database
# KPN Media (v2.9.1): automatic Story ID backfill + coverage report,
# mirroring release_migrate. The backfill is idempotent and exits
# non-zero on error, which fails this script (set -e) and the release;
# the coverage report is advisory and always exits 0.
python manage.py backfill_story_ids
python manage.py check_story_id_coverage
