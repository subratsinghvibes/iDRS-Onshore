-- SQL Export for table: auth_user
-- Generated: 2025-11-03
-- Database: Interactive Drilling Rig Scheduler (iDRS)

-- Drop table if exists
DROP TABLE IF EXISTS auth_user;

-- Create table structure
CREATE TABLE "auth_user" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "password" varchar(128) NOT NULL, "last_login" datetime NULL, "is_superuser" bool NOT NULL, "username" varchar(150) NOT NULL UNIQUE, "last_name" varchar(150) NOT NULL, "email" varchar(254) NOT NULL, "is_staff" bool NOT NULL, "is_active" bool NOT NULL, "date_joined" datetime NOT NULL, "first_name" varchar(150) NOT NULL);

-- Insert data (2 rows)
INSERT INTO auth_user (id, password, last_login, is_superuser, username, last_name, email, is_staff, is_active, date_joined, first_name) VALUES (1, 'pbkdf2_sha256$870000$wNJjG5yPYPCYCMfOTlCRLK$ll3zOqwNDiv8XvHm7eB1Jv/6L0uBXgLiB28UE6C9gUU=', '2025-11-03 13:19:21.384997', 1, 'admin', '', 'admin@example.com', 1, 1, '2025-08-18 06:05:16.554400', '');
INSERT INTO auth_user (id, password, last_login, is_superuser, username, last_name, email, is_staff, is_active, date_joined, first_name) VALUES (2, 'pbkdf2_sha256$870000$ACdcY7pgLeHEQ1WuMnr5Qh$31GHHXsLnsbRIfuu1Fi/I8NKVwB1OevUdFzPZm31yGA=', NULL, 1, 'Subrat', 'Singh', 'singh_subrat@ongc.co.in', 1, 1, '2025-10-01 10:12:20', 'Subrat');
