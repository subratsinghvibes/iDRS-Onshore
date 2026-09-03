# IDRS – Quick Setup Guide (Windows + SQLite)

This guide lets you run the Interactive Drilling Rig Scheduler on Windows using the pre-built SQLite database (`db_for_friend.sqlite3`) that already contains all 111 wells, 14 rigs, users, schedules, and other data.

No PostgreSQL installation is required.

---

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.11 – 3.13 | Download from https://www.python.org/downloads/ |
| Git | any | To clone/copy the repo |
| FFmpeg | optional | Only needed for video export features |

> During Python installation, **check "Add python.exe to PATH"**.

---

## Step-by-Step Setup

### 1. Open Command Prompt (or PowerShell)

```cmd
cd C:\path\to\IDRS v11 (Deterministic Version)
```

### 2. Create a virtual environment

```cmd
python -m venv .venv
.venv\Scripts\activate
```

### 3. Install dependencies

```cmd
pip install -r requirements.txt
```

> `psycopg2-binary` may warn or fail on Windows without PostgreSQL installed – that's fine, it's not needed for SQLite. If pip errors out on it, install everything else:
> ```cmd
> pip install -r requirements.txt --exclude psycopg2-binary
> ```
> Or simply ignore the error; Django will fall back to SQLite regardless.

### 4. Create your `.env` file

Create a file named `.env` in the project root with this content:

```env
SECRET_KEY=change-me-to-any-random-string-at-least-50-chars-long-123456789
DEBUG=True
USE_HTTPS=False
ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=sqlite:///db_for_friend.sqlite3
```

Key point: `DATABASE_URL=sqlite:///db_for_friend.sqlite3` tells Django to use the included SQLite file instead of PostgreSQL.

### 5. Verify the database works

```cmd
python manage.py check
python manage.py showmigrations | findstr "\[ \]"
```

The first command should print "System check identified no issues." The second should produce no output (meaning all migrations are applied).

### 6. Run the development server

```cmd
python manage.py runserver 0.0.0.0:8011
```

Open your browser at **http://127.0.0.1:8011/**

---

## Default Login

Use any of the existing accounts from the database. The superuser is:

| Username | Password |
|----------|----------|
| `admin`  | *(ask Subrat for the password, or reset below)* |

To reset the admin password:

```cmd
python manage.py changepassword admin
```

Or create a fresh superuser:

```cmd
python manage.py createsuperuser
```

---

## Troubleshooting

### "No module named psycopg2"
Not a problem – the app auto-detects `DATABASE_URL` and uses SQLite. This error only appears if something forces a PostgreSQL import. Double-check your `.env` has `DATABASE_URL=sqlite:///db_for_friend.sqlite3`.

### Migrations out of sync
If you ever see migration warnings:
```cmd
python manage.py migrate
```

### Static files not loading (CSS/JS missing)
```cmd
python manage.py collectstatic --noinput
```
Then restart the server.

### Port already in use
Use a different port:
```cmd
python manage.py runserver 0.0.0.0:8080
```

---

## Files to Share

Send your friend these items:

1. **The entire project folder** (excluding `.venv/` and `__pycache__/` directories)
2. **`db_for_friend.sqlite3`** (120 MB – already in the project root)

The `db_dump.json` file is an intermediate export and is *not* needed.

---

## Notes

- The SQLite database is a full replica of the PostgreSQL production data as of the export date.
- SQLite works perfectly for single-user / demo usage. For concurrent multi-user production use, PostgreSQL is recommended.
- All 111 wells, 14 rigs, schedules, baskets, distances, and user accounts are included.
