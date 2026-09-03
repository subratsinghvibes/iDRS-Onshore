-- SQL Export for table: django_migrations
-- Generated: 2025-11-03
-- Database: Interactive Drilling Rig Scheduler (iDRS)

-- Drop table if exists
DROP TABLE IF EXISTS django_migrations;

-- Create table structure
CREATE TABLE "django_migrations" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "app" varchar(255) NOT NULL, "name" varchar(255) NOT NULL, "applied" datetime NOT NULL);

-- Insert data (25 rows)
INSERT INTO django_migrations (id, app, name, applied) VALUES (1, 'contenttypes', '0001_initial', '2025-08-18 06:05:09.305090');
INSERT INTO django_migrations (id, app, name, applied) VALUES (2, 'auth', '0001_initial', '2025-08-18 06:05:09.310346');
INSERT INTO django_migrations (id, app, name, applied) VALUES (3, 'admin', '0001_initial', '2025-08-18 06:05:09.314408');
INSERT INTO django_migrations (id, app, name, applied) VALUES (4, 'admin', '0002_logentry_remove_auto_add', '2025-08-18 06:05:09.320174');
INSERT INTO django_migrations (id, app, name, applied) VALUES (5, 'admin', '0003_logentry_add_action_flag_choices', '2025-08-18 06:05:09.322550');
INSERT INTO django_migrations (id, app, name, applied) VALUES (6, 'contenttypes', '0002_remove_content_type_name', '2025-08-18 06:05:09.328421');
INSERT INTO django_migrations (id, app, name, applied) VALUES (7, 'auth', '0002_alter_permission_name_max_length', '2025-08-18 06:05:09.332109');
INSERT INTO django_migrations (id, app, name, applied) VALUES (8, 'auth', '0003_alter_user_email_max_length', '2025-08-18 06:05:09.335233');
INSERT INTO django_migrations (id, app, name, applied) VALUES (9, 'auth', '0004_alter_user_username_opts', '2025-08-18 06:05:09.337650');
INSERT INTO django_migrations (id, app, name, applied) VALUES (10, 'auth', '0005_alter_user_last_login_null', '2025-08-18 06:05:09.341069');
INSERT INTO django_migrations (id, app, name, applied) VALUES (11, 'auth', '0006_require_contenttypes_0002', '2025-08-18 06:05:09.342156');
INSERT INTO django_migrations (id, app, name, applied) VALUES (12, 'auth', '0007_alter_validators_add_error_messages', '2025-08-18 06:05:09.344273');
INSERT INTO django_migrations (id, app, name, applied) VALUES (13, 'auth', '0008_alter_user_username_max_length', '2025-08-18 06:05:09.347777');
INSERT INTO django_migrations (id, app, name, applied) VALUES (14, 'auth', '0009_alter_user_last_name_max_length', '2025-08-18 06:05:09.350826');
INSERT INTO django_migrations (id, app, name, applied) VALUES (15, 'auth', '0010_alter_group_name_max_length', '2025-08-18 06:05:09.354196');
INSERT INTO django_migrations (id, app, name, applied) VALUES (16, 'auth', '0011_update_proxy_permissions', '2025-08-18 06:05:09.356243');
INSERT INTO django_migrations (id, app, name, applied) VALUES (17, 'auth', '0012_alter_user_first_name_max_length', '2025-08-18 06:05:09.359394');
INSERT INTO django_migrations (id, app, name, applied) VALUES (18, 'scheduler', '0001_initial', '2025-08-18 06:05:09.366626');
INSERT INTO django_migrations (id, app, name, applied) VALUES (19, 'sessions', '0001_initial', '2025-08-18 06:05:09.367946');
INSERT INTO django_migrations (id, app, name, applied) VALUES (20, 'scheduler', '0002_rig_asset_id', '2025-09-24 04:24:54.181754');
INSERT INTO django_migrations (id, app, name, applied) VALUES (21, 'scheduler', '0003_schedule_financial_year', '2025-09-30 04:09:33.472149');
INSERT INTO django_migrations (id, app, name, applied) VALUES (22, 'scheduler', '0004_add_actual_dates_to_assignment', '2025-10-10 15:31:52.607112');
INSERT INTO django_migrations (id, app, name, applied) VALUES (23, 'scheduler', '0005_schedulerig_schedulewell', '2025-10-15 05:25:01.746567');
INSERT INTO django_migrations (id, app, name, applied) VALUES (24, 'scheduler', '0006_schedule_branch_type_schedule_parent_schedule_and_more', '2025-10-15 09:48:56.938385');
INSERT INTO django_migrations (id, app, name, applied) VALUES (25, 'scheduler', '0007_add_original_planned_dates', '2025-10-24 11:16:23.590842');
