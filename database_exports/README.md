# Database Exports

This folder contains individual SQL files for each database table in the Interactive Drilling Rig Scheduler (iDRS).

## Structure

Each SQL file contains:
1. **DROP TABLE** statement - Safely removes existing table
2. **CREATE TABLE** statement - Defines table structure
3. **INSERT INTO** statements - Populates table with current data

## Files Overview

### Django Authentication & Admin Tables
- `auth_user.sql` - User accounts (2 users)
- `auth_group.sql` - User groups (empty)
- `auth_permission.sql` - System permissions (52 permissions)
- `auth_user_groups.sql` - User-group relationships (empty)
- `auth_user_user_permissions.sql` - User permissions (44 assignments)
- `django_admin_log.sql` - Admin action log (3 entries)
- `django_content_type.sql` - Content type registry (13 types)
- `django_migrations.sql` - Migration history (25 migrations)
- `django_session.sql` - Active sessions (4 sessions)

### Application Tables (Scheduler)
- `scheduler_rig.sql` - **8 rigs** (drilling rig information)
- `scheduler_well.sql` - **56 wells** (well information)
- `scheduler_schedule.sql` - **9 schedules** (schedule configurations)
- `scheduler_assignment.sql` - **399 assignments** (rig-well assignments)
- `scheduler_schedulerig.sql` - **54 schedule rigs** (schedule-specific rig data)
- `scheduler_schedulewell.sql` - **496 schedule wells** (schedule-specific well data)
- `scheduler_unassignedwell.sql` - **86 unassigned wells** (wells not scheduled)

### System Tables
- `sqlite_sequence.sql` - Auto-increment sequence tracking (7 sequences)

---

## Total Data Summary

- **Total Tables**: 18
- **Total Data Rows**: 1,249
- **Export Date**: November 3, 2025
- **Database Size**: ~307 KB

---

## How to Use

### Import Individual Tables

```bash
# Import a specific table
sqlite3 db.sqlite3 < "database_exports/scheduler_rig.sql"

# Import multiple tables
cat database_exports/scheduler_*.sql | sqlite3 db.sqlite3

# Import all tables
cat database_exports/*.sql | sqlite3 db.sqlite3
```

### Import in Specific Order (Recommended)

For a fresh database, import in this order to respect foreign key constraints:

```bash
# 1. Django core tables first
sqlite3 db.sqlite3 < "database_exports/django_content_type.sql"
sqlite3 db.sqlite3 < "database_exports/django_migrations.sql"

# 2. Authentication tables
sqlite3 db.sqlite3 < "database_exports/auth_permission.sql"
sqlite3 db.sqlite3 < "database_exports/auth_group.sql"
sqlite3 db.sqlite3 < "database_exports/auth_user.sql"
sqlite3 db.sqlite3 < "database_exports/auth_group_permissions.sql"
sqlite3 db.sqlite3 < "database_exports/auth_user_groups.sql"
sqlite3 db.sqlite3 < "database_exports/auth_user_user_permissions.sql"

# 3. Application base tables
sqlite3 db.sqlite3 < "database_exports/scheduler_rig.sql"
sqlite3 db.sqlite3 < "database_exports/scheduler_well.sql"
sqlite3 db.sqlite3 < "database_exports/scheduler_schedule.sql"

# 4. Application relationship tables
sqlite3 db.sqlite3 < "database_exports/scheduler_assignment.sql"
sqlite3 db.sqlite3 < "database_exports/scheduler_schedulerig.sql"
sqlite3 db.sqlite3 < "database_exports/scheduler_schedulewell.sql"
sqlite3 db.sqlite3 < "database_exports/scheduler_unassignedwell.sql"

# 5. Session and admin tables
sqlite3 db.sqlite3 < "database_exports/django_session.sql"
sqlite3 db.sqlite3 < "database_exports/django_admin_log.sql"

# 6. System tables
sqlite3 db.sqlite3 < "database_exports/sqlite_sequence.sql"
```

### Complete Fresh Deployment

```bash
# Stop the server
pkill -f 'python.*manage.py runserver'

# Backup existing database (if any)
mv db.sqlite3 db.sqlite3.backup

# Import all tables in order
cd "/path/to/IDRS v8./database_exports"
for file in django_content_type.sql django_migrations.sql \
            auth_permission.sql auth_group.sql auth_user.sql \
            auth_group_permissions.sql auth_user_groups.sql auth_user_user_permissions.sql \
            scheduler_rig.sql scheduler_well.sql scheduler_schedule.sql \
            scheduler_assignment.sql scheduler_schedulerig.sql scheduler_schedulewell.sql \
            scheduler_unassignedwell.sql \
            django_session.sql django_admin_log.sql sqlite_sequence.sql; do
    echo "Importing $file..."
    sqlite3 ../db.sqlite3 < "$file"
done

# Run migrations to ensure schema is current
cd ..
python manage.py migrate

# Restart server
python manage.py runserver 8011
```

### Selective Import (Update Specific Data)

```bash
# Only update rigs
sqlite3 db.sqlite3 < "database_exports/scheduler_rig.sql"

# Only update wells
sqlite3 db.sqlite3 < "database_exports/scheduler_well.sql"

# Update both rigs and wells
sqlite3 db.sqlite3 < "database_exports/scheduler_rig.sql"
sqlite3 db.sqlite3 < "database_exports/scheduler_well.sql"
```

---

## Re-export Updated Data

To create new exports after making changes:

```bash
cd "/Users/subratsingh/Desktop/4. WebApp Developments/11. Interactive Drilling Rig Scheduler/IDRS v8."

# Run the export script
python export_tables_to_sql.py
```

This will regenerate all SQL files with the latest data.

---

## Database Schema Overview

### Key Relationships

```
Schedule (1) ----< (N) Assignment (N) >---- (1) Rig
                            |
                            V
                          Well
                            
Schedule (1) ----< (N) Schedule (Parent-Child for versions)
```

### Sample File Structure

Each SQL file follows this pattern:

```sql
-- SQL Export for table: scheduler_rig
-- Generated: 2025-11-03
-- Database: Interactive Drilling Rig Scheduler (iDRS)

-- Drop table if exists
DROP TABLE IF EXISTS scheduler_rig;

-- Create table structure
CREATE TABLE "scheduler_rig" (...column definitions...);

-- Insert data (8 rows)
INSERT INTO scheduler_rig (...) VALUES (...);
INSERT INTO scheduler_rig (...) VALUES (...);
...
```

### Important Fields

**Rigs**:
- `asset_id`: Unique rig identifier
- `available_from`, `available_to`: Availability window
- `capacity`: Max wells per rig
- `min_solve_time`: Minimum time between wells

**Wells**:
- `well_name`: Unique well identifier
- `well_type`: DEV (Development), EXP (Exploration), APP (Appraisal)
- `priority`: Optimization priority (1-5)
- `spud_date`, `planned_rig_release_date`: Date constraints
- `drilling_days`, `pt_days`: Time requirements
- `well_cost`: Financial impact

**Schedules**:
- `name`: Schedule identifier
- `financial_year`: FY designation
- `version_number`: Version tracking
- `parent_schedule`: For schedule branching
- `status`: RUNNING, COMPLETED, FAILED

**Assignments**:
- Links rigs to wells within a schedule
- Tracks `assigned_start_date`, `assigned_end_date`
- Includes `actual_*` dates for tracking execution

---

## Important Notes

### Before Import
- ⚠️ **Backup existing database** before importing
- 🔒 **Stop Django server** to prevent conflicts
- 📝 **Review user accounts** - passwords are hashed
- ⚡ **Foreign keys** - Import in correct order to avoid constraint errors

### After Import
1. Run migrations to ensure schema is current:
   ```bash
   python manage.py migrate
   ```

2. Verify data integrity:
   ```bash
   sqlite3 db.sqlite3 "SELECT COUNT(*) FROM scheduler_rig;"
   sqlite3 db.sqlite3 "SELECT COUNT(*) FROM scheduler_well;"
   ```

3. Create a superuser if needed:
   ```bash
   python manage.py createsuperuser
   ```

4. Collect static files:
   ```bash
   python manage.py collectstatic --noinput
   ```

### Security Considerations
- The SQL files contain hashed passwords
- Session data may need to be cleared in production
- Update `SECRET_KEY` in production environment
- Review and update `ALLOWED_HOSTS` setting

---

## File Sizes

```
auth_permission.sql         - 52 rows
auth_user.sql              - 2 rows
auth_user_user_permissions - 44 rows
django_admin_log.sql       - 3 rows
django_content_type.sql    - 13 rows
django_migrations.sql      - 25 rows
django_session.sql         - 4 rows
scheduler_assignment.sql   - 399 rows ⭐
scheduler_rig.sql          - 8 rows
scheduler_schedule.sql     - 9 rows
scheduler_schedulerig.sql  - 54 rows
scheduler_schedulewell.sql - 496 rows ⭐
scheduler_unassignedwell   - 86 rows
scheduler_well.sql         - 56 rows
sqlite_sequence.sql        - 7 rows
```

*⭐ = Large data files*

---

## Maintenance

### Re-export All Tables
```bash
# Navigate to project root
cd "/Users/subratsingh/Desktop/4. WebApp Developments/11. Interactive Drilling Rig Scheduler/IDRS v8."

# Run export script
python export_tables_to_sql.py
```

### Export Single Table Manually
```bash
# Example: Export scheduler_rig table
python -c "
import sqlite3
conn = sqlite3.connect('db.sqlite3')
cursor = conn.cursor()
cursor.execute('SELECT sql FROM sqlite_master WHERE type=\"table\" AND name=\"scheduler_rig\"')
print(cursor.fetchone()[0])
conn.close()
" > database_exports/scheduler_rig_schema.sql
```

### Automated Backups
Create scheduled exports using cron:
```bash
# Add to crontab (daily at 2 AM)
0 2 * * * cd /path/to/IDRS && python export_tables_to_sql.py
```

---

## Troubleshooting

### Import Errors
If you encounter errors during import:
```bash
# Check SQLite version
sqlite3 --version

# Verify SQL file integrity
head -n 20 "sample sql file for deployment.sql"

# Import with verbose output
sqlite3 db.sqlite3 < "sample sql file for deployment.sql" 2>&1 | tee import.log
```

### Database Locked
If database is locked:
```bash
# Stop all Django processes
pkill -f 'python.*manage.py runserver'

# Remove lock file if exists
rm db.sqlite3-journal
```

---

## Export Date & Stats

**Export Generated**: November 3, 2025  
**Database Size**: 307 KB  
**Format**: SQLite SQL dump  
**Django Version**: 5.2.5  
**Python Version**: 3.13.2  

---

## Support

For issues or questions:
- Check Django documentation: https://docs.djangoproject.com/
- Review SQLite documentation: https://www.sqlite.org/docs.html
- Contact system administrator

---

**Product of Project DOT**  
Interactive Drilling Rig Scheduler (iDRS) v8.0
