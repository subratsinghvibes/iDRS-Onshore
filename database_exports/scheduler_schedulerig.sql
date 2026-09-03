-- SQL Export for table: scheduler_schedulerig
-- Generated: 2025-11-03
-- Database: Interactive Drilling Rig Scheduler (iDRS)

-- Drop table if exists
DROP TABLE IF EXISTS scheduler_schedulerig;

-- Create table structure
CREATE TABLE "scheduler_schedulerig" ("id" char(32) NOT NULL PRIMARY KEY, "created_at" datetime NOT NULL, "rig_id" char(32) NOT NULL REFERENCES "scheduler_rig" ("id") DEFERRABLE INITIALLY DEFERRED, "schedule_id" char(32) NOT NULL REFERENCES "scheduler_schedule" ("id") DEFERRABLE INITIALLY DEFERRED);

-- Insert data (54 rows)
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('d962606866b441229c160033469bfa50', '2025-10-15 11:31:31.084740', 'b3cfa36b977a49cf988378e7cb58b793', 'f78b1466122349fa9fdd282fae13bc12');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('1d57d5ed10e34fc3a5744bf8bd35ec1a', '2025-10-15 11:31:31.084752', 'ef65180efec04c8da15fe541d311d983', 'f78b1466122349fa9fdd282fae13bc12');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('0702ed6ac63448ef9ed46795519f2746', '2025-10-15 11:31:31.084760', '524c9e5126c14ec894af671a0dbdf174', 'f78b1466122349fa9fdd282fae13bc12');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('9e785e8328a34de9a3b4eb636219663e', '2025-10-15 11:31:31.084767', '375a8fdb61a74700a3cb7a78a9950ac7', 'f78b1466122349fa9fdd282fae13bc12');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('e9684af9d6e947b494ba36e70d483a25', '2025-10-15 11:31:31.084773', '483305c1e0f841099c47134288a94369', 'f78b1466122349fa9fdd282fae13bc12');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('41cfe79d052344bbb9be2be7468b5ee5', '2025-10-15 11:31:31.084780', '134fd43cf6e54bbb8a4b2f872bcc2ff7', 'f78b1466122349fa9fdd282fae13bc12');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('c4262691f3784f8a8503f3dc1a90ae93', '2025-10-15 14:44:41.566296', 'b3cfa36b977a49cf988378e7cb58b793', '9240e4b2779c45c48aa70391b1d1ba07');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('3b2ac08595e2496cbc5b4089557724cf', '2025-10-15 14:44:41.566309', 'ef65180efec04c8da15fe541d311d983', '9240e4b2779c45c48aa70391b1d1ba07');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('3206aac46bfc4a94a0ccbb96b4cc4eec', '2025-10-15 14:44:41.566318', '524c9e5126c14ec894af671a0dbdf174', '9240e4b2779c45c48aa70391b1d1ba07');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('26143bf099d341d2a6b5cc572377d1b1', '2025-10-15 14:44:41.566326', '375a8fdb61a74700a3cb7a78a9950ac7', '9240e4b2779c45c48aa70391b1d1ba07');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('49e2e4d022d0497182c9b70158cc5fb3', '2025-10-15 14:44:41.566334', '483305c1e0f841099c47134288a94369', '9240e4b2779c45c48aa70391b1d1ba07');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('59f8f029b2cd425c8f09359926a741e1', '2025-10-15 14:44:41.566340', '134fd43cf6e54bbb8a4b2f872bcc2ff7', '9240e4b2779c45c48aa70391b1d1ba07');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('73dc2cb107494442a3cada2da3122c96', '2025-10-15 14:51:12.371769', 'b3cfa36b977a49cf988378e7cb58b793', '1b5d3e00dd984f5388b8897966f91aae');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('1bbff7ceae1948c7bee068614b4888c4', '2025-10-15 14:51:12.371779', 'ef65180efec04c8da15fe541d311d983', '1b5d3e00dd984f5388b8897966f91aae');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('56bce9d382a24c47acb006bc646e3a0b', '2025-10-15 14:51:12.371787', '524c9e5126c14ec894af671a0dbdf174', '1b5d3e00dd984f5388b8897966f91aae');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('4d99e1b0e2a44c538663459803af4597', '2025-10-15 14:51:12.371793', '375a8fdb61a74700a3cb7a78a9950ac7', '1b5d3e00dd984f5388b8897966f91aae');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('84f53c18332f4172ba20314d44bdf169', '2025-10-15 14:51:12.371800', '483305c1e0f841099c47134288a94369', '1b5d3e00dd984f5388b8897966f91aae');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('d8724b0c42b6477ea44ea1573a6315fe', '2025-10-15 14:51:12.371807', '134fd43cf6e54bbb8a4b2f872bcc2ff7', '1b5d3e00dd984f5388b8897966f91aae');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('de2adc284bdb44f790d68b5c5a3f4733', '2025-10-16 03:51:22.497061', 'b3cfa36b977a49cf988378e7cb58b793', '04c10a6ecbe74bcab4f671f89c9df2f7');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('810210bf37b7407b936a41d2cb707440', '2025-10-16 03:51:22.497075', 'ef65180efec04c8da15fe541d311d983', '04c10a6ecbe74bcab4f671f89c9df2f7');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('2f373e58975f49ea9bc3997066312d9b', '2025-10-16 03:51:22.497084', '524c9e5126c14ec894af671a0dbdf174', '04c10a6ecbe74bcab4f671f89c9df2f7');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('fe8efa56a914463fa3de2bace92a4eed', '2025-10-16 03:51:22.497109', '375a8fdb61a74700a3cb7a78a9950ac7', '04c10a6ecbe74bcab4f671f89c9df2f7');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('7864929ac9e349afa952bb977cdb8a1f', '2025-10-16 03:51:22.497119', '483305c1e0f841099c47134288a94369', '04c10a6ecbe74bcab4f671f89c9df2f7');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('41f22d77624545a0b26c52891bca827e', '2025-10-16 03:51:22.497129', '134fd43cf6e54bbb8a4b2f872bcc2ff7', '04c10a6ecbe74bcab4f671f89c9df2f7');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('69d133e76c3d4f7d8562973ab5ed3fa9', '2025-10-16 09:37:17.561070', 'b3cfa36b977a49cf988378e7cb58b793', 'c4da21bc9e524b42ace26b27e932208f');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('a3f584596d334b21994f1e6dd730fcde', '2025-10-16 09:37:17.561080', 'ef65180efec04c8da15fe541d311d983', 'c4da21bc9e524b42ace26b27e932208f');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('bd2a060cfd4c406e9e18a9943303e89c', '2025-10-16 09:37:17.561087', '524c9e5126c14ec894af671a0dbdf174', 'c4da21bc9e524b42ace26b27e932208f');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('8e2a20215dcf491cb94aab8fd8e672d5', '2025-10-16 09:37:17.561094', '375a8fdb61a74700a3cb7a78a9950ac7', 'c4da21bc9e524b42ace26b27e932208f');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('8395d35a0f6448ac8155f00123433f12', '2025-10-16 09:37:17.561100', '483305c1e0f841099c47134288a94369', 'c4da21bc9e524b42ace26b27e932208f');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('044ebe8fa84f4e96b7ca427ef1c3a501', '2025-10-16 09:37:17.561107', '134fd43cf6e54bbb8a4b2f872bcc2ff7', 'c4da21bc9e524b42ace26b27e932208f');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('87c8260b4c9844b6a339593ecfb9960b', '2025-10-17 04:20:39.159479', 'b3cfa36b977a49cf988378e7cb58b793', '148c13f6642440fb9d32227547654f9a');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('09338cd77f394ab0bd5f13fdbb41a2f7', '2025-10-17 04:20:39.159490', 'ef65180efec04c8da15fe541d311d983', '148c13f6642440fb9d32227547654f9a');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('129a5a7cc817453cae1d3168a1d62781', '2025-10-17 04:20:39.159497', '524c9e5126c14ec894af671a0dbdf174', '148c13f6642440fb9d32227547654f9a');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('fc3ae8b1823f4b98af47e3130d02bbce', '2025-10-17 04:20:39.159504', '375a8fdb61a74700a3cb7a78a9950ac7', '148c13f6642440fb9d32227547654f9a');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('cc897b4b83c8476396b03faf9b70f869', '2025-10-17 04:20:39.159511', '483305c1e0f841099c47134288a94369', '148c13f6642440fb9d32227547654f9a');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('a85780519ffa4907a398452a6aa1eb45', '2025-10-17 04:20:39.159517', '134fd43cf6e54bbb8a4b2f872bcc2ff7', '148c13f6642440fb9d32227547654f9a');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('a810dcb2ef424672b24e61686aaa465d', '2025-10-24 11:14:42.170367', 'b3cfa36b977a49cf988378e7cb58b793', 'd37698abad7d47ed8a7eae17a5fa9ab6');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('09714d1037494c9886d648e95eb80e56', '2025-10-24 11:14:42.170378', 'ef65180efec04c8da15fe541d311d983', 'd37698abad7d47ed8a7eae17a5fa9ab6');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('6290109292cf49608121b95a5bf190fa', '2025-10-24 11:14:42.170386', '524c9e5126c14ec894af671a0dbdf174', 'd37698abad7d47ed8a7eae17a5fa9ab6');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('7f003a22ba1f492f87adda8fe541f4ab', '2025-10-24 11:14:42.170392', '375a8fdb61a74700a3cb7a78a9950ac7', 'd37698abad7d47ed8a7eae17a5fa9ab6');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('d0c3bbbb3fd847179bab3825fafcd01c', '2025-10-24 11:14:42.170399', '483305c1e0f841099c47134288a94369', 'd37698abad7d47ed8a7eae17a5fa9ab6');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('da8b3707a79d4bd29c6d2c7b385ac80f', '2025-10-24 11:14:42.170405', '134fd43cf6e54bbb8a4b2f872bcc2ff7', 'd37698abad7d47ed8a7eae17a5fa9ab6');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('75bd17ae74d24657867cae68eecba68d', '2025-10-24 11:27:06.124741', 'b3cfa36b977a49cf988378e7cb58b793', '54622907bb95420f85350e2b057cf6e7');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('410c502717524d318be0964ef7727d20', '2025-10-24 11:27:06.124754', 'ef65180efec04c8da15fe541d311d983', '54622907bb95420f85350e2b057cf6e7');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('1c80b6655bc94eb6bc53ad25a7c9ac47', '2025-10-24 11:27:06.124762', '524c9e5126c14ec894af671a0dbdf174', '54622907bb95420f85350e2b057cf6e7');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('6fcc05a9080940388160aa3cfac2a7d4', '2025-10-24 11:27:06.124768', '375a8fdb61a74700a3cb7a78a9950ac7', '54622907bb95420f85350e2b057cf6e7');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('16ff6b3b9b7046b2aeb2969835222bcb', '2025-10-24 11:27:06.124775', '483305c1e0f841099c47134288a94369', '54622907bb95420f85350e2b057cf6e7');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('fbfddeebe699413fbc190c8259e28fe5', '2025-10-24 11:27:06.124782', '134fd43cf6e54bbb8a4b2f872bcc2ff7', '54622907bb95420f85350e2b057cf6e7');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('2144a3d03ddc48f182e699bbf745b4b7', '2025-10-25 14:25:36.249237', 'b3cfa36b977a49cf988378e7cb58b793', '9eb992daf70946c28e1564690eda5511');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('44e84bdcede94fcba1c5b3c3d608e515', '2025-10-25 14:25:36.251074', 'ef65180efec04c8da15fe541d311d983', '9eb992daf70946c28e1564690eda5511');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('77849b7b0c034a179607682449ddc2c6', '2025-10-25 14:25:36.252392', '524c9e5126c14ec894af671a0dbdf174', '9eb992daf70946c28e1564690eda5511');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('256068ea0bc94ea9bcde7de445a863e3', '2025-10-25 14:25:36.253665', '375a8fdb61a74700a3cb7a78a9950ac7', '9eb992daf70946c28e1564690eda5511');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('c8d5b2acf41e4192b24cc6a34ed63833', '2025-10-25 14:25:36.254978', '483305c1e0f841099c47134288a94369', '9eb992daf70946c28e1564690eda5511');
INSERT INTO scheduler_schedulerig (id, created_at, rig_id, schedule_id) VALUES ('a8ad5c9c251d4efabf9dc76405543689', '2025-10-25 14:25:36.256265', '134fd43cf6e54bbb8a4b2f872bcc2ff7', '9eb992daf70946c28e1564690eda5511');
