-- SQL Export for table: auth_user_user_permissions
-- Generated: 2025-11-03
-- Database: Interactive Drilling Rig Scheduler (iDRS)

-- Drop table if exists
DROP TABLE IF EXISTS auth_user_user_permissions;

-- Create table structure
CREATE TABLE "auth_user_user_permissions" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "user_id" integer NOT NULL REFERENCES "auth_user" ("id") DEFERRABLE INITIALLY DEFERRED, "permission_id" integer NOT NULL REFERENCES "auth_permission" ("id") DEFERRABLE INITIALLY DEFERRED);

-- Insert data (44 rows)
INSERT INTO auth_user_user_permissions (id, user_id, permission_id) VALUES (1, 2, 1);
INSERT INTO auth_user_user_permissions (id, user_id, permission_id) VALUES (2, 2, 2);
INSERT INTO auth_user_user_permissions (id, user_id, permission_id) VALUES (3, 2, 3);
INSERT INTO auth_user_user_permissions (id, user_id, permission_id) VALUES (4, 2, 4);
INSERT INTO auth_user_user_permissions (id, user_id, permission_id) VALUES (5, 2, 5);
INSERT INTO auth_user_user_permissions (id, user_id, permission_id) VALUES (6, 2, 6);
INSERT INTO auth_user_user_permissions (id, user_id, permission_id) VALUES (7, 2, 7);
INSERT INTO auth_user_user_permissions (id, user_id, permission_id) VALUES (8, 2, 8);
INSERT INTO auth_user_user_permissions (id, user_id, permission_id) VALUES (9, 2, 9);
INSERT INTO auth_user_user_permissions (id, user_id, permission_id) VALUES (10, 2, 10);
INSERT INTO auth_user_user_permissions (id, user_id, permission_id) VALUES (11, 2, 11);
INSERT INTO auth_user_user_permissions (id, user_id, permission_id) VALUES (12, 2, 12);
INSERT INTO auth_user_user_permissions (id, user_id, permission_id) VALUES (13, 2, 13);
INSERT INTO auth_user_user_permissions (id, user_id, permission_id) VALUES (14, 2, 14);
INSERT INTO auth_user_user_permissions (id, user_id, permission_id) VALUES (15, 2, 15);
INSERT INTO auth_user_user_permissions (id, user_id, permission_id) VALUES (16, 2, 16);
INSERT INTO auth_user_user_permissions (id, user_id, permission_id) VALUES (17, 2, 17);
INSERT INTO auth_user_user_permissions (id, user_id, permission_id) VALUES (18, 2, 18);
INSERT INTO auth_user_user_permissions (id, user_id, permission_id) VALUES (19, 2, 19);
INSERT INTO auth_user_user_permissions (id, user_id, permission_id) VALUES (20, 2, 20);
INSERT INTO auth_user_user_permissions (id, user_id, permission_id) VALUES (21, 2, 21);
INSERT INTO auth_user_user_permissions (id, user_id, permission_id) VALUES (22, 2, 22);
INSERT INTO auth_user_user_permissions (id, user_id, permission_id) VALUES (23, 2, 23);
INSERT INTO auth_user_user_permissions (id, user_id, permission_id) VALUES (24, 2, 24);
INSERT INTO auth_user_user_permissions (id, user_id, permission_id) VALUES (25, 2, 25);
INSERT INTO auth_user_user_permissions (id, user_id, permission_id) VALUES (26, 2, 26);
INSERT INTO auth_user_user_permissions (id, user_id, permission_id) VALUES (27, 2, 27);
INSERT INTO auth_user_user_permissions (id, user_id, permission_id) VALUES (28, 2, 28);
INSERT INTO auth_user_user_permissions (id, user_id, permission_id) VALUES (29, 2, 29);
INSERT INTO auth_user_user_permissions (id, user_id, permission_id) VALUES (30, 2, 30);
INSERT INTO auth_user_user_permissions (id, user_id, permission_id) VALUES (31, 2, 31);
INSERT INTO auth_user_user_permissions (id, user_id, permission_id) VALUES (32, 2, 32);
INSERT INTO auth_user_user_permissions (id, user_id, permission_id) VALUES (33, 2, 33);
INSERT INTO auth_user_user_permissions (id, user_id, permission_id) VALUES (34, 2, 34);
INSERT INTO auth_user_user_permissions (id, user_id, permission_id) VALUES (35, 2, 35);
INSERT INTO auth_user_user_permissions (id, user_id, permission_id) VALUES (36, 2, 36);
INSERT INTO auth_user_user_permissions (id, user_id, permission_id) VALUES (37, 2, 37);
INSERT INTO auth_user_user_permissions (id, user_id, permission_id) VALUES (38, 2, 38);
INSERT INTO auth_user_user_permissions (id, user_id, permission_id) VALUES (39, 2, 39);
INSERT INTO auth_user_user_permissions (id, user_id, permission_id) VALUES (40, 2, 40);
INSERT INTO auth_user_user_permissions (id, user_id, permission_id) VALUES (41, 2, 41);
INSERT INTO auth_user_user_permissions (id, user_id, permission_id) VALUES (42, 2, 42);
INSERT INTO auth_user_user_permissions (id, user_id, permission_id) VALUES (43, 2, 43);
INSERT INTO auth_user_user_permissions (id, user_id, permission_id) VALUES (44, 2, 44);
