-- SQL Export for table: auth_group
-- Generated: 2025-11-03
-- Database: Interactive Drilling Rig Scheduler (iDRS)

-- Drop table if exists
DROP TABLE IF EXISTS auth_group;

-- Create table structure
CREATE TABLE "auth_group" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "name" varchar(150) NOT NULL UNIQUE);

-- No data to insert (table is empty)
