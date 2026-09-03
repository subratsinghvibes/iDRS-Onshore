# IDRS v11 – Linux VM Offline Deployment Guide

## Overview

This guide explains how to deploy the IDRS application on an air-gapped (offline) Linux VM using Docker.  
All required software is pre-packaged inside the Docker image, so no internet access is needed on the VM.

---

## Prerequisites on the Linux VM

| Requirement | Minimum Version | How to install (online, before VM is air-gapped) |
|---|---|---|
| Linux OS | Ubuntu 22.04 LTS or RHEL 9 recommended | — |
| Docker Engine | 24.x or later | `curl -fsSL https://get.docker.com \| sh` |
| Docker Compose v2 | 2.x (ships with Docker Desktop / `docker-compose-plugin`) | `apt install docker-compose-plugin` |
| Disk space | ≥ 10 GB free | — |
| RAM | ≥ 4 GB (8 GB recommended for large optimisation runs) | — |

> **Important:** Install Docker **before** the VM is disconnected from the internet.  
> Once air-gapped, no further internet access is required.

---

## Step 1 – Transfer the Bundle to the VM

Copy `idrs-v11-docker-bundle.tar.gz` to the VM using any available method:

```bash
# Option A – SCP (if VM is reachable on the internal network)
scp idrs-v11-docker-bundle.tar.gz user@<VM_IP>:/opt/idrs/

# Option B – USB drive
# Mount USB on VM, then copy the file to /opt/idrs/
sudo mkdir -p /opt/idrs
sudo cp /media/usb/idrs-v11-docker-bundle.tar.gz /opt/idrs/
```

---

## Step 2 – Extract the Bundle

```bash
cd /opt/idrs
tar -xzf idrs-v11-docker-bundle.tar.gz
cd idrs-docker-bundle
ls -la
```

You should see:
```
idrs-v11.image.tar.gz    ← the Docker image (large file, ~2–4 GB)
docker-compose.yml
.env.template
load-image.sh
start.sh
stop.sh
DEPLOY_LINUX.md          ← this file
```

---

## Step 3 – Load the Docker Image

```bash
chmod +x load-image.sh
./load-image.sh
```

Verify the image loaded:
```bash
docker images | grep idrs
# Expected output:
# idrs   v11   <image_id>   <date>   <size>
```

---

## Step 4 – Configure the Environment

```bash
cp .env.template .env
nano .env         # or use vi / vim
```

**Minimum settings to change:**

| Variable | What to set |
|---|---|
| `SECRET_KEY` | A long random string (50+ chars). Generate with: `python3 -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `ALLOWED_HOSTS` | The VM's IP address and/or hostname, e.g. `192.168.1.100,idrs.mycompany.local` |
| `DJANGO_SUPERUSER_PASSWORD` | A strong password for the Django admin account |
| `LDAP_SERVER` | Your Active Directory server IP (or leave default to disable LDAP) |

---

## Step 5 – Start the Application

```bash
chmod +x start.sh
./start.sh
```

The first startup will:
1. Run database migrations automatically
2. Load initial reference data (drilling norms, benchmarks, etc.)
3. Create the admin superuser account
4. Start the Gunicorn web server on port **8011**

To follow the startup logs:
```bash
docker compose logs -f
```

---

## Step 6 – Access the Application

Open a browser on any machine that can reach the VM:

```
http://<VM_IP_ADDRESS>:8011/
```

- **Admin panel:** `http://<VM_IP_ADDRESS>:8011/admin/`
  - Username: `admin` (or whatever you set in `.env`)
  - Password: value of `DJANGO_SUPERUSER_PASSWORD` in `.env`

---

## Day-to-Day Operations

### Start / Stop

```bash
# Start (background)
docker compose up -d

# Stop (keeps data)
docker compose down

# Restart
docker compose restart
```

### View Logs

```bash
# Live app logs
docker compose logs -f

# Last 100 lines
docker compose logs --tail=100

# Gunicorn access log (inside container)
docker exec idrs_app tail -f /app/logs/gunicorn-access.log
```

### Open a Shell Inside the Container

```bash
docker exec -it idrs_app bash
```

### Run Django management commands

```bash
# Example: create another superuser
docker exec -it idrs_app python manage.py createsuperuser

# Example: Django shell
docker exec -it idrs_app python manage.py shell
```

---

## Data Persistence

Data is stored in named Docker volumes, **not** inside the container.  
The container can be deleted and re-created without losing data.

| Volume | Contents |
|---|---|
| `idrs_data` | SQLite database (`db.sqlite3`) |
| `idrs_media` | Uploaded media files (video tutorials, etc.) |
| `idrs_logs` | Application and Gunicorn log files |

### Backup the Database

```bash
# Copy SQLite database to current directory
docker cp idrs_app:/app/data/db.sqlite3 ./idrs-backup-$(date +%Y%m%d).sqlite3
```

### Restore a Backup

```bash
# Stop the app first, then restore
docker compose down
docker cp ./idrs-backup-20240101.sqlite3 idrs_app:/app/data/db.sqlite3
docker compose up -d
```

---

## Upgrading to a New Version

1. Build a new image on the internet-connected machine:
   ```bash
   ./docker/build-offline.sh
   ```
2. Transfer the new bundle to the VM
3. Load the new image and restart:
   ```bash
   ./load-image.sh       # loads idrs:v12 (or new tag)
   # Edit docker-compose.yml to update image tag if needed
   docker compose down
   docker compose up -d
   ```
   > The database and media volumes are preserved automatically.

---

## Firewall Configuration

If the VM has a firewall enabled, allow port 8011:

```bash
# Ubuntu / Debian (ufw)
sudo ufw allow 8011/tcp
sudo ufw reload

# RHEL / CentOS (firewalld)
sudo firewall-cmd --permanent --add-port=8011/tcp
sudo firewall-cmd --reload
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Container keeps restarting | Run `docker compose logs` to read the error |
| "ALLOWED_HOSTS" error in browser | Add the VM IP to `ALLOWED_HOSTS` in `.env` and restart |
| Port 8011 already in use | Change host port in `docker-compose.yml` → `"8012:8011"` |
| "no such image: idrs:v11" | Re-run `./load-image.sh` |
| Database locked errors | Normal under heavy load — Gunicorn is already limited to 2 workers for SQLite safety |
| LDAP login fails | Set `LDAP_SERVER` to correct IP in `.env`, or use Django admin login (`/admin/`) |
| Video tutorials not playing | Check media volume is mounted; large videos may need FFmpeg re-processing |

---

## Security Hardening (Recommended)

1. **Change all default passwords** in `.env` before first use.
2. **Restrict access** by binding to a specific interface: change `"8011:8011"` to `"192.168.1.100:8011:8011"` in `docker-compose.yml`.
3. **Use a reverse proxy** (Nginx) in front of Gunicorn if exposing to a wider network.
4. Set `DEBUG=False` (already the default) — never set `True` in production.
5. Keep Docker Engine updated even when the VM is air-gapped (apply OS patches periodically).
