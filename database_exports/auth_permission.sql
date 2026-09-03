-- SQL Export for table: auth_permission
-- Generated: 2025-11-03
-- Database: Interactive Drilling Rig Scheduler (iDRS)

-- Drop table if exists
DROP TABLE IF EXISTS auth_permission;

-- Create table structure
CREATE TABLE "auth_permission" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "content_type_id" integer NOT NULL REFERENCES "django_content_type" ("id") DEFERRABLE INITIALLY DEFERRED, "codename" varchar(100) NOT NULL, "name" varchar(255) NOT NULL);

-- Insert data (52 rows)
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (1, 1, 'add_logentry', 'Can add log entry');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (2, 1, 'change_logentry', 'Can change log entry');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (3, 1, 'delete_logentry', 'Can delete log entry');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (4, 1, 'view_logentry', 'Can view log entry');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (5, 2, 'add_permission', 'Can add permission');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (6, 2, 'change_permission', 'Can change permission');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (7, 2, 'delete_permission', 'Can delete permission');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (8, 2, 'view_permission', 'Can view permission');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (9, 3, 'add_group', 'Can add group');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (10, 3, 'change_group', 'Can change group');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (11, 3, 'delete_group', 'Can delete group');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (12, 3, 'view_group', 'Can view group');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (13, 4, 'add_user', 'Can add user');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (14, 4, 'change_user', 'Can change user');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (15, 4, 'delete_user', 'Can delete user');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (16, 4, 'view_user', 'Can view user');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (17, 5, 'add_contenttype', 'Can add content type');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (18, 5, 'change_contenttype', 'Can change content type');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (19, 5, 'delete_contenttype', 'Can delete content type');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (20, 5, 'view_contenttype', 'Can view content type');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (21, 6, 'add_session', 'Can add session');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (22, 6, 'change_session', 'Can change session');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (23, 6, 'delete_session', 'Can delete session');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (24, 6, 'view_session', 'Can view session');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (25, 7, 'add_rig', 'Can add Drilling Rig');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (26, 7, 'change_rig', 'Can change Drilling Rig');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (27, 7, 'delete_rig', 'Can delete Drilling Rig');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (28, 7, 'view_rig', 'Can view Drilling Rig');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (29, 8, 'add_schedule', 'Can add Schedule');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (30, 8, 'change_schedule', 'Can change Schedule');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (31, 8, 'delete_schedule', 'Can delete Schedule');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (32, 8, 'view_schedule', 'Can view Schedule');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (33, 9, 'add_well', 'Can add Well');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (34, 9, 'change_well', 'Can change Well');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (35, 9, 'delete_well', 'Can delete Well');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (36, 9, 'view_well', 'Can view Well');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (37, 10, 'add_unassignedwell', 'Can add Unassigned Well');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (38, 10, 'change_unassignedwell', 'Can change Unassigned Well');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (39, 10, 'delete_unassignedwell', 'Can delete Unassigned Well');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (40, 10, 'view_unassignedwell', 'Can view Unassigned Well');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (41, 11, 'add_assignment', 'Can add Assignment');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (42, 11, 'change_assignment', 'Can change Assignment');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (43, 11, 'delete_assignment', 'Can delete Assignment');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (44, 11, 'view_assignment', 'Can view Assignment');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (45, 12, 'add_schedulerig', 'Can add Schedule Rig');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (46, 12, 'change_schedulerig', 'Can change Schedule Rig');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (47, 12, 'delete_schedulerig', 'Can delete Schedule Rig');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (48, 12, 'view_schedulerig', 'Can view Schedule Rig');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (49, 13, 'add_schedulewell', 'Can add Schedule Well');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (50, 13, 'change_schedulewell', 'Can change Schedule Well');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (51, 13, 'delete_schedulewell', 'Can delete Schedule Well');
INSERT INTO auth_permission (id, content_type_id, codename, name) VALUES (52, 13, 'view_schedulewell', 'Can view Schedule Well');
