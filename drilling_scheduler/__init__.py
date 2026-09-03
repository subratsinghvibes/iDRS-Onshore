"""
Enable SQLite WAL (Write-Ahead Logging) mode and foreign keys on every connection.
WAL mode allows concurrent reads while writes are happening, preventing most
'database is locked' errors.
"""
from django.db.backends.signals import connection_created


def configure_sqlite(sender, connection, **kwargs):
    if connection.vendor == 'sqlite':
        cursor = connection.cursor()
        cursor.execute('PRAGMA journal_mode=WAL;')
        cursor.execute('PRAGMA foreign_keys=ON;')
        cursor.execute('PRAGMA busy_timeout=30000;')  # 30 seconds


connection_created.connect(configure_sqlite)
