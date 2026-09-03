#!/usr/bin/env bash
# =============================================================================
# IDRS v11 – Container Entrypoint Script
# Runs inside the container on every start.
# =============================================================================
set -e

echo "============================================================"
echo " IDRS v11 – Starting up"
echo "============================================================"

# --------------------------------------------------------------------------- #
# Point Django at the persisted SQLite database in the mounted data volume.
# The DATABASE_URL env var can be overridden in docker-compose.yml or at
# runtime to use PostgreSQL instead.
# --------------------------------------------------------------------------- #
export DATABASE_URL="${DATABASE_URL:-sqlite:////app/data/db.sqlite3}"

# --------------------------------------------------------------------------- #
# Wait for the database to be reachable (relevant only for PostgreSQL).
# For SQLite the file is always accessible once the volume is mounted.
# --------------------------------------------------------------------------- #
if [[ "$DATABASE_URL" == postgresql* ]] || [[ "$DATABASE_URL" == postgres* ]]; then
    echo "[entrypoint] Waiting for PostgreSQL to be ready..."
    # Extract host and port from the DATABASE_URL
    DB_HOST=$(echo "$DATABASE_URL" | sed -E 's|.*@([^:/]+).*|\1|')
    DB_PORT=$(echo "$DATABASE_URL" | sed -E 's|.*:([0-9]+)/.*|\1|')
    DB_PORT="${DB_PORT:-5432}"
    
    for i in $(seq 1 30); do
        if (echo > /dev/tcp/$DB_HOST/$DB_PORT) 2>/dev/null; then
            echo "[entrypoint] PostgreSQL is ready."
            break
        fi
        echo "[entrypoint] Attempt $i/30 – PostgreSQL not ready yet, waiting 2s..."
        sleep 2
    done
fi

# --------------------------------------------------------------------------- #
# Apply database migrations (idempotent – safe to run on every start)
# --------------------------------------------------------------------------- #
echo "[entrypoint] Running database migrations..."
python manage.py migrate --noinput

# --------------------------------------------------------------------------- #
# Load initial fixture data (only if the database is empty / first run).
# We check for the presence of at least one schedule to determine first-boot.
# --------------------------------------------------------------------------- #
FIXTURE_FLAG="/app/data/.fixtures_loaded"
if [ ! -f "$FIXTURE_FLAG" ]; then
    echo "[entrypoint] First run – loading fixture data..."
    fixtures=(
        "fixtures/01_companycode.json"
        "fixtures/02_externalappsetting.json"
        "fixtures/03_locationspecfactor.json"
        "fixtures/04_dailydrillingrate.json"
        "fixtures/05_drillingbenchmark.json"
        "fixtures/06_rigbuildingnorm.json"
        "fixtures/07_rigbuildingadjustment.json"
        "fixtures/08_completiontestingnorm.json"
        "fixtures/09_additionaltest.json"
        "fixtures/10_coringnorm.json"
        "fixtures/11_casingnorm.json"
        "fixtures/12_hermeticaltestingnorm.json"
        "fixtures/13_operationnorm.json"
        # 14_videotutorial.json is intentionally excluded from auto-loading.
        # It references production user IDs (uploaded_by_id) that do not exist
        # in a fresh database, causing an IntegrityError.  Load it manually
        # after creating users:  docker exec idrs_app python manage.py loaddata fixtures/14_videotutorial.json
    )
    for fixture in "${fixtures[@]}"; do
        if [ -f "$fixture" ]; then
            echo "[entrypoint]   Loading $fixture..."
            python manage.py loaddata "$fixture" || echo "[entrypoint]   WARNING: Failed to load $fixture (skipping)"
        fi
    done
    touch "$FIXTURE_FLAG"
    echo "[entrypoint] Fixture data loaded."
else
    echo "[entrypoint] Fixtures already loaded – skipping."
fi

# --------------------------------------------------------------------------- #
# Create a default Django superuser if one does not already exist.
# Credentials are taken from environment variables for security.
# --------------------------------------------------------------------------- #
DJANGO_SUPERUSER_USERNAME="${DJANGO_SUPERUSER_USERNAME:-admin}"
DJANGO_SUPERUSER_EMAIL="${DJANGO_SUPERUSER_EMAIL:-admin@idrs.local}"
DJANGO_SUPERUSER_PASSWORD="${DJANGO_SUPERUSER_PASSWORD:-ChangeMe@2024!}"

echo "[entrypoint] Ensuring superuser '$DJANGO_SUPERUSER_USERNAME' exists..."
python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='${DJANGO_SUPERUSER_USERNAME}').exists():
    User.objects.create_superuser(
        '${DJANGO_SUPERUSER_USERNAME}',
        '${DJANGO_SUPERUSER_EMAIL}',
        '${DJANGO_SUPERUSER_PASSWORD}'
    )
    print('[entrypoint] Superuser created.')
else:
    print('[entrypoint] Superuser already exists – skipping.')
"

echo "============================================================"
echo " IDRS v11 – Startup complete. Launching server..."
echo "============================================================"

# Hand off to the CMD (gunicorn) or any override passed to docker run / compose
exec "$@"
