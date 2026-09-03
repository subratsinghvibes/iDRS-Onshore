-- SQL Export for table: django_admin_log
-- Generated: 2025-11-03
-- Database: Interactive Drilling Rig Scheduler (iDRS)

-- Drop table if exists
DROP TABLE IF EXISTS django_admin_log;

-- Create table structure
CREATE TABLE "django_admin_log" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "object_id" text NULL, "object_repr" varchar(200) NOT NULL, "action_flag" smallint unsigned NOT NULL CHECK ("action_flag" >= 0), "change_message" text NOT NULL, "content_type_id" integer NULL REFERENCES "django_content_type" ("id") DEFERRABLE INITIALLY DEFERRED, "user_id" integer NOT NULL REFERENCES "auth_user" ("id") DEFERRABLE INITIALLY DEFERRED, "action_time" datetime NOT NULL);

-- Insert data (3 rows)
INSERT INTO django_admin_log (id, object_id, object_repr, action_flag, change_message, content_type_id, user_id, action_time) VALUES (1, '2', 'Subrat', 1, '[{"added": {}}]', 4, 1, '2025-10-01 10:12:20.526918');
INSERT INTO django_admin_log (id, object_id, object_repr, action_flag, change_message, content_type_id, user_id, action_time) VALUES (2, '2', 'Subrat', 2, '[{"changed": {"fields": ["First name", "Last name", "Email address", "Superuser status", "User permissions"]}}]', 4, 1, '2025-10-01 10:12:46.108131');
INSERT INTO django_admin_log (id, object_id, object_repr, action_flag, change_message, content_type_id, user_id, action_time) VALUES (3, '2', 'Subrat', 2, '[{"changed": {"fields": ["Staff status"]}}]', 4, 1, '2025-10-01 10:12:55.598272');
