"""
iDRS - Admin Password Reset Utility
Called by reset_admin_password.bat
Must be run from the project root (same directory as manage.py).
"""

import os
import sys
import re
import socket


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SEP = "=" * 62


def banner(msg=""):
    print()
    print(SEP)
    if msg:
        print(f"  {msg}")
        print(SEP)


def check_postgres(env_path=".env"):
    """Parse DATABASE_URL from .env and do a TCP probe on the host:port."""
    db_host = None
    db_port = 5432

    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("DATABASE_URL="):
                    url = line.split("=", 1)[1]
                    m = re.search(r"@([^:/]+):?(\d+)?/", url)
                    if m:
                        db_host = m.group(1)
                        db_port = int(m.group(2) or 5432)
                    break

    if not db_host:
        print("  [WARN] Could not parse DATABASE_URL from .env — skipping connectivity check.")
        return True

    print(f"  Connecting to PostgreSQL at {db_host}:{db_port} ...", end=" ", flush=True)
    try:
        s = socket.create_connection((db_host, db_port), timeout=5)
        s.close()
        print("[OK] Server is reachable.")
        return True
    except (socket.timeout, ConnectionRefusedError, OSError) as exc:
        print(f"[FAIL]\n\n  ERROR: {exc}")
        print(f"\n  PostgreSQL is NOT reachable at {db_host}:{db_port}.")
        print("  Make sure the PostgreSQL service is running and the")
        print("  .env DATABASE_URL is correct, then try again.")
        return False


def setup_django():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "drilling_scheduler.settings")
    try:
        import django
        django.setup()
    except Exception as exc:
        print(f"\n  ERROR: Django setup failed: {exc}")
        sys.exit(1)


def list_superusers():
    from django.contrib.auth import get_user_model
    User = get_user_model()
    rows = list(
        User.objects.filter(is_superuser=True)
        .values_list("username", "email", "is_active")
    )
    return rows, User


def prompt_username(rows, User):
    print(f"\n  {'USERNAME':<25} {'EMAIL':<35} ACTIVE")
    print("  " + "-" * 65)
    for username, email, active in rows:
        print(f"  {username:<25} {email or '(none)':<35} {'Yes' if active else 'No'}")

    print()
    while True:
        target = input("  Enter username to reset (from list above): ").strip()
        if not target:
            print("  Username cannot be empty. Try again.")
            continue
        if not User.objects.filter(username=target).exists():
            print(f"  '{target}' not found. Please enter a username from the list.")
            continue
        return target


def prompt_password():
    import getpass
    print()
    while True:
        pw1 = getpass.getpass("  Enter new password  : ")
        if not pw1:
            print("  Password cannot be empty. Try again.")
            continue
        pw2 = getpass.getpass("  Confirm new password: ")
        if pw1 != pw2:
            print("  Passwords do not match. Try again.")
            continue
        return pw1


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    banner("iDRS - Interactive Drilling Rig Scheduler")
    print("  Admin Password Reset Utility")
    print(SEP)

    # Step 1 — PostgreSQL check
    print("\n  [1/4] Checking PostgreSQL connectivity...")
    if not check_postgres():
        sys.exit(1)

    # Step 2 — Django setup
    print("\n  [2/4] Initialising Django / database connection...")
    setup_django()
    print("        Django ready.")

    # Step 3 — List superusers
    print("\n  [3/4] Fetching superuser accounts...")
    rows, User = list_superusers()

    if not rows:
        print("\n  No superuser accounts found.")
        print("  Create one with:  .venv\\Scripts\\python manage.py createsuperuser")
        sys.exit(1)

    # Step 4 — Interactive reset
    print("\n  [4/4] Select account and set new password")
    print()
    target = prompt_username(rows, User)
    new_password = prompt_password()

    user = User.objects.get(username=target)
    user.set_password(new_password)
    user.save()

    print()
    print(SEP)
    print(f"  [OK] Password for '{target}' has been reset successfully.")
    print(f"       Log in at: http://localhost:8022/admin")
    print(SEP)
    print()


if __name__ == "__main__":
    main()
