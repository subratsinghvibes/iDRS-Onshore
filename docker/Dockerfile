# =============================================================================
# IDRS v11 - Dockerfile
# Target: Linux x86_64 (AMD64) — for offline VM deployment
# Build this image on an internet-connected machine, then export and transfer.
# =============================================================================

# Force linux/amd64 so the image runs correctly on a Linux x86_64 server VM,
# even when building from macOS ARM (Apple Silicon).
FROM --platform=linux/amd64 python:3.13-slim

# --------------------------------------------------------------------------- #
# System-level metadata
# --------------------------------------------------------------------------- #
LABEL maintainer="IDRS Team" \
      version="11" \
      description="Interactive Drilling Rig Scheduler – Deterministic Version"

# Prevent Python from writing .pyc files and from buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# --------------------------------------------------------------------------- #
# System dependencies
# --------------------------------------------------------------------------- #
# ffmpeg  – video processing / HLS streaming
# gcc / build-essential / libffi-dev / libssl-dev – needed to compile some
#   Python wheels (e.g. cryptography used by ldap3)
# libldap2-dev / libsasl2-dev – optional LDAP dev headers (ldap3 is pure-Python,
#   but keeps things flexible if a native LDAP C extension is ever added)
# curl – useful for health-checks
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        gcc \
        build-essential \
        libffi-dev \
        libssl-dev \
        libldap2-dev \
        libsasl2-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

# --------------------------------------------------------------------------- #
# Application working directory
# --------------------------------------------------------------------------- #
WORKDIR /app

# --------------------------------------------------------------------------- #
# Python dependencies
# Install before copying the full source so Docker layer-cache is reused when
# only application code changes (and requirements.txt is unchanged).
# --------------------------------------------------------------------------- #
COPY requirements.txt requirements-prod.txt ./

RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -r requirements-prod.txt

# --------------------------------------------------------------------------- #
# Application source code
# --------------------------------------------------------------------------- #
COPY . .

# --------------------------------------------------------------------------- #
# Runtime directories & permissions
# --------------------------------------------------------------------------- #
# /app/data  – persisted via a Docker volume; holds the SQLite database file
# /app/media – persisted via a Docker volume; holds uploaded media (videos etc.)
# /app/logs  – persisted via a Docker volume; holds application log files
RUN mkdir -p /app/data /app/media /app/logs \
    && chmod 755 /app/data /app/media /app/logs

# Make the entrypoint script executable
RUN chmod +x /app/docker/entrypoint.sh

# --------------------------------------------------------------------------- #
# Static files
# Collected into STATIC_ROOT (/app/staticfiles) at build time so WhiteNoise
# can serve them without needing a separate Nginx container.
# --------------------------------------------------------------------------- #
RUN SECRET_KEY="build-time-placeholder-key-not-used-in-production-123456789" \
    DEBUG=False \
    ALLOWED_HOSTS="*" \
    DATABASE_URL="sqlite:////app/data/db.sqlite3" \
    python manage.py collectstatic --noinput

# --------------------------------------------------------------------------- #
# Remove settings.py from the image.
# It contains company-specific defaults and must be provided at runtime via
# a bind-mount (see docker-compose.yml).  The file was only needed above for
# the collectstatic build step.
# --------------------------------------------------------------------------- #
RUN rm /app/drilling_scheduler/settings.py

# --------------------------------------------------------------------------- #
# Networking
# --------------------------------------------------------------------------- #
EXPOSE 8011

# --------------------------------------------------------------------------- #
# Health-check – Django's /health/ endpoint (defined in urls.py) or admin page
# --------------------------------------------------------------------------- #
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8011/admin/login/ || exit 1

# --------------------------------------------------------------------------- #
# Entrypoint & default command
# --------------------------------------------------------------------------- #
ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["gunicorn", \
     "--bind", "0.0.0.0:8011", \
     "--workers", "2", \
     "--threads", "4", \
     "--worker-class", "gthread", \
     "--timeout", "300", \
     "--keep-alive", "5", \
     "--max-requests", "1000", \
     "--max-requests-jitter", "100", \
     "--access-logfile", "/app/logs/gunicorn-access.log", \
     "--error-logfile", "/app/logs/gunicorn-error.log", \
     "--log-level", "info", \
     "drilling_scheduler.wsgi:application"]
