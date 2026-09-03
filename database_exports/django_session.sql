-- SQL Export for table: django_session
-- Generated: 2025-11-03
-- Database: Interactive Drilling Rig Scheduler (iDRS)

-- Drop table if exists
DROP TABLE IF EXISTS django_session;

-- Create table structure
CREATE TABLE "django_session" ("session_key" varchar(40) NOT NULL PRIMARY KEY, "session_data" text NOT NULL, "expire_date" datetime NOT NULL);

-- Insert data (4 rows)
INSERT INTO django_session (session_key, session_data, expire_date) VALUES ('r5vgpm0ig85190torhybrt2twilf87z2', '.eJxVjMsOwiAQRf-FtSFAKQ-X7v0GMsxMpWogKe3K-O_apAvd3nPOfYkE21rS1nlJM4mz0OL0u2XAB9cd0B3qrUlsdV3mLHdFHrTLayN-Xg7376BAL9_ak7FKazNk54PT0aCbOBObiBS0cqMbAxmKEGjgIWQfLSMjgTVoJ-XF-wPMazfe:1v3tnO:MGXcQbs0lXsQ65-LAsX2mykq2SUd5YYix6tMnPMfSn0', '2025-10-15 10:10:50.386138');
INSERT INTO django_session (session_key, session_data, expire_date) VALUES ('r7fy64qztakgqw0g8zp926ldcgijft25', '.eJxVjMsOwiAQRf-FtSHDW1y69xsIMINUDSSlXRn_3TbpQrf3nHPfLMR1qWEdNIcJ2YUJdvrdUsxPajvAR2z3znNvyzwlviv8oIPfOtLrerh_BzWOutUktY1WCCxRosEiAYxTQJBIOgNkvc6KNsM5l6wvxukzyFS01B69MuzzBdQyNxM:1vFsA3:cyBRtavGgtacXSzP0JspRRXmExSsUd_74W9XrXNV_Y8', '2025-11-03 11:51:43.546648');
INSERT INTO django_session (session_key, session_data, expire_date) VALUES ('ab16p61tzoc9dqv9j12ob1pvxe7u18rl', '.eJxVjMsOwiAQRf-FtSHy6BRcuvcbyAxMpWogKe3K-O_SpAvdnnPufYuA25rD1ngJcxIXocTplxHGJ5ddpAeWe5WxlnWZSe6JPGyTt5r4dT3av4OMLfc1GB3BqqQhgXE0TsijB8uUmPlMhgAH7SyxB8cQjbe9xIFBdegmEJ8v6ro4HQ:1vFt87:c0L1KzrFmJKlTPJCecSJ_JBKUFQIjsFa0-fClnnG7pk', '2025-11-03 12:53:47.811441');
INSERT INTO django_session (session_key, session_data, expire_date) VALUES ('irm3qo6y72ep02200oothplw4v6vjp0k', '.eJxVjMsOwiAURP-FtSECDVCX7v0GcrkPqRpISrsy_rtt0oVuZjHnzLxVgnUpae08p4nURRl1-u0y4JPrDugB9d40trrMU9a7og_a9a0Rv66H-3dQoJdtbdFlEwBljIGsRzAuWOfQ58gC1jPTKCbYsxDhMDAHcQJbklCOQdTnCwTHOZM:1vFuSv:CEY5DR2caw5HRdJRnUfSRM9C4WOE2jBL-tcgyk7yAhE', '2025-11-03 14:19:21.385811');
