#!/usr/bin/env bash
# =============================================================================
# IDRS v11 – Build & Export Script (run on the INTERNET-CONNECTED Mac/machine)
# =============================================================================
# This script:
#   1. Builds the Docker image for linux/amd64 (works on Apple Silicon too)
#   2. Saves it as a compressed .tar.gz archive
#   3. Packages it with docker-compose.yml and deployment files
#   4. Produces a single bundle ready to copy to the offline VM
#
# Usage:
#   chmod +x docker/build-offline.sh
#   ./docker/build-offline.sh
#
# Output:
#   idrs-v11-docker-bundle.tar.gz   (in the project root)
# =============================================================================

set -euo pipefail

# Guard: Docker daemon must be running
if ! docker info > /dev/null 2>&1; then
    echo "ERROR: Cannot reach the Docker daemon."
    echo ""
    echo "  On macOS: open Docker Desktop first, wait for the whale icon in the"
    echo "            menu bar to stop animating, then re-run this script."
    echo "  On Linux: sudo systemctl start docker"
    echo ""
    exit 1
fi

IMAGE_NAME="idrs"
IMAGE_TAG="v11"
FULL_IMAGE="${IMAGE_NAME}:${IMAGE_TAG}"
BUNDLE_DIR="idrs-docker-bundle"
BUNDLE_ARCHIVE="idrs-v11-docker-bundle.tar.gz"

echo "============================================================"
echo "  IDRS v11 – Docker Offline Build & Export"
echo "============================================================"
echo ""
echo "  Image   : ${FULL_IMAGE}"
echo "  Platform: linux/amd64"
echo "  Output  : ${BUNDLE_ARCHIVE}"
echo ""

# --------------------------------------------------------------------------- #
# Step 1 – Build the image
# Using --platform linux/amd64 ensures it runs on x86_64 Linux VMs even if
# you are building on Apple Silicon (M1/M2/M3).
# --------------------------------------------------------------------------- #
echo "[1/4] Building Docker image (this may take 5–15 minutes)..."
docker build \
    --no-cache \
    --platform linux/amd64 \
    --tag "${FULL_IMAGE}" \
    --file Dockerfile \
    .

echo ""
echo "      Image built successfully."
echo ""

# --------------------------------------------------------------------------- #
# Step 2 – Export the image to a compressed tar archive
# --------------------------------------------------------------------------- #
echo "[2/4] Exporting image to archive (this may take a few minutes)..."
docker save "${FULL_IMAGE}" | gzip > "${BUNDLE_ARCHIVE}.image.tar.gz"

IMAGE_SIZE=$(du -sh "${BUNDLE_ARCHIVE}.image.tar.gz" | cut -f1)
echo "      Image archive: ${BUNDLE_ARCHIVE}.image.tar.gz  (${IMAGE_SIZE})"
echo ""

# --------------------------------------------------------------------------- #
# Step 3 – Assemble the deployment bundle
# --------------------------------------------------------------------------- #
echo "[3/4] Assembling deployment bundle..."
rm -rf "${BUNDLE_DIR}"
mkdir -p "${BUNDLE_DIR}"

# Container image archive
mv "${BUNDLE_ARCHIVE}.image.tar.gz" "${BUNDLE_DIR}/idrs-v11.image.tar.gz"

# Compose and environment files
cp docker-compose.yml           "${BUNDLE_DIR}/"
cp docker/.env.template         "${BUNDLE_DIR}/.env.template"

# settings.py is bind-mounted at runtime — include it in the bundle so the
# deployment team can place it next to docker-compose.yml on the VM.
cp drilling_scheduler/settings.py "${BUNDLE_DIR}/settings.py"

# Deployment instructions
cp docker/DEPLOY_LINUX.md       "${BUNDLE_DIR}/DEPLOY_LINUX.md" 2>/dev/null || true

# Convenience helper scripts for the VM
cat > "${BUNDLE_DIR}/load-image.sh" << 'LOAD_SCRIPT'
#!/usr/bin/env bash
# Run this on the offline Linux VM to load the Docker image.
set -e
echo "Loading IDRS Docker image..."
docker load < idrs-v11.image.tar.gz
echo "Image loaded successfully: idrs:v11"
docker images | grep idrs
LOAD_SCRIPT
chmod +x "${BUNDLE_DIR}/load-image.sh"

cat > "${BUNDLE_DIR}/start.sh" << 'START_SCRIPT'
#!/usr/bin/env bash
# Run this on the offline Linux VM to start IDRS.
set -e
if [ ! -f ".env" ]; then
    echo "ERROR: .env file not found."
    echo "Copy .env.template to .env and configure it first."
    exit 1
fi
docker compose up -d
echo ""
echo "IDRS is starting. Check status with: docker compose logs -f"
echo "Access the application at: http://$(hostname -I | awk '{print $1}'):8011"
START_SCRIPT
chmod +x "${BUNDLE_DIR}/start.sh"

cat > "${BUNDLE_DIR}/stop.sh" << 'STOP_SCRIPT'
#!/usr/bin/env bash
# Run this on the offline Linux VM to stop IDRS.
docker compose down
echo "IDRS stopped."
STOP_SCRIPT
chmod +x "${BUNDLE_DIR}/stop.sh"

# --------------------------------------------------------------------------- #
# Step 4 – Compress the bundle
# COPYFILE_DISABLE=1 prevents macOS BSD tar from embedding ._resource-fork
# files and LIBARCHIVE.xattr.* extended attributes into the archive.
# Without it, Linux recipients see spurious ._* files and xattr warnings.
# --------------------------------------------------------------------------- #
echo "[4/4] Compressing bundle..."
COPYFILE_DISABLE=1 tar -czf "${BUNDLE_ARCHIVE}" "${BUNDLE_DIR}/"
rm -rf "${BUNDLE_DIR}"

BUNDLE_SIZE=$(du -sh "${BUNDLE_ARCHIVE}" | cut -f1)

echo ""
echo "============================================================"
echo "  BUILD COMPLETE"
echo "============================================================"
echo ""
echo "  Bundle : ${BUNDLE_ARCHIVE}  (${BUNDLE_SIZE})"
echo ""
echo "  Next steps:"
echo "  1. Copy ${BUNDLE_ARCHIVE} to the offline Linux VM"
echo "     (USB drive, internal network share, SCP, etc.)"
echo ""
echo "  2. On the VM, extract and follow DEPLOY_LINUX.md:"
echo "     tar -xzf ${BUNDLE_ARCHIVE}"
echo "     cd idrs-docker-bundle"
echo "     cat DEPLOY_LINUX.md"
echo ""
echo "============================================================"
