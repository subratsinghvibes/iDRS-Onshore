-- SQL Export for table: django_content_type
-- Generated: 2025-11-03
-- Database: Interactive Drilling Rig Scheduler (iDRS)

-- Drop table if exists
DROP TABLE IF EXISTS django_content_type;

-- Create table structure
CREATE TABLE "django_content_type" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "app_label" varchar(100) NOT NULL, "model" varchar(100) NOT NULL);

-- Insert data (13 rows)
INSERT INTO django_content_type (id, app_label, model) VALUES (1, 'admin', 'logentry');
INSERT INTO django_content_type (id, app_label, model) VALUES (2, 'auth', 'permission');
INSERT INTO django_content_type (id, app_label, model) VALUES (3, 'auth', 'group');
INSERT INTO django_content_type (id, app_label, model) VALUES (4, 'auth', 'user');
INSERT INTO django_content_type (id, app_label, model) VALUES (5, 'contenttypes', 'contenttype');
INSERT INTO django_content_type (id, app_label, model) VALUES (6, 'sessions', 'session');
INSERT INTO django_content_type (id, app_label, model) VALUES (7, 'scheduler', 'rig');
INSERT INTO django_content_type (id, app_label, model) VALUES (8, 'scheduler', 'schedule');
INSERT INTO django_content_type (id, app_label, model) VALUES (9, 'scheduler', 'well');
INSERT INTO django_content_type (id, app_label, model) VALUES (10, 'scheduler', 'unassignedwell');
INSERT INTO django_content_type (id, app_label, model) VALUES (11, 'scheduler', 'assignment');
INSERT INTO django_content_type (id, app_label, model) VALUES (12, 'scheduler', 'schedulerig');
INSERT INTO django_content_type (id, app_label, model) VALUES (13, 'scheduler', 'schedulewell');
