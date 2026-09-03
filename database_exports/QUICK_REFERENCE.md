# Quick Reference - Database Operations

## Export Database (Create Backup)
```bash
# Full database export
sqlite3 db.sqlite3 .dump > "database_exports/sample sql file for deployment.sql"

# With timestamp
sqlite3 db.sqlite3 .dump > "database_exports/backup_$(date +%Y%m%d_%H%M%S).sql"
```

## Import Database (Restore)
```bash
# ⚠️ STOP SERVER FIRST!
pkill -f 'python.*manage.py runserver'

# Remove old database (CAREFUL!)
rm db.sqlite3

# Import SQL file
sqlite3 db.sqlite3 < "database_exports/sample sql file for deployment.sql"

# Run migrations to update schema
python manage.py migrate

# Restart server
python manage.py runserver 8011
```

## Verify Database
```bash
# Check tables exist
sqlite3 db.sqlite3 ".tables"

# Count rigs
sqlite3 db.sqlite3 "SELECT COUNT(*) FROM scheduler_rig;"

# Count wells
sqlite3 db.sqlite3 "SELECT COUNT(*) FROM scheduler_well;"

# Count schedules
sqlite3 db.sqlite3 "SELECT COUNT(*) FROM scheduler_schedule;"

# List users
sqlite3 db.sqlite3 "SELECT id, username, email, is_active FROM auth_user;"
```

## Common Tasks

### Create New Export
```bash
cd "/Users/subratsingh/Desktop/4. WebApp Developments/11. Interactive Drilling Rig Scheduler/IDRS v8."
sqlite3 db.sqlite3 .dump > "database_exports/backup_$(date +%Y%m%d_%H%M%S).sql"
```

### Deploy to New Environment
```bash
# 1. Copy SQL file to new environment
# 2. Create virtual environment and install requirements
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Import database
sqlite3 db.sqlite3 < "database_exports/sample sql file for deployment.sql"

# 4. Run migrations
python manage.py migrate

# 5. Collect static files
python manage.py collectstatic --noinput

# 6. Start server
python manage.py runserver 8011
```

### Merge with Existing Data
```bash
# Export specific table
sqlite3 db.sqlite3 "SELECT * FROM scheduler_rig;" > rigs.csv

# Import to another database
sqlite3 other_db.sqlite3 ".import rigs.csv scheduler_rig"
```

## Database Size
```bash
ls -lh db.sqlite3
du -sh db.sqlite3
```

## Backup Strategy
```bash
# Daily backups (add to crontab)
0 2 * * * cd /path/to/IDRS && sqlite3 db.sqlite3 .dump > "database_exports/daily_$(date +\%Y\%m\%d).sql"

# Weekly backups (keep longer)
0 3 * * 0 cd /path/to/IDRS && sqlite3 db.sqlite3 .dump > "database_exports/weekly_$(date +\%Y_week\%U).sql"

# Cleanup old backups (keep last 30 days)
find database_exports/ -name "daily_*.sql" -mtime +30 -delete
```

## Emergency Recovery
```bash
# If database is corrupted
sqlite3 db.sqlite3 ".recover" | sqlite3 recovered.db
mv db.sqlite3 db_corrupted.sqlite3.bak
mv recovered.db db.sqlite3
python manage.py migrate
```

---

**Last Updated**: November 3, 2025
