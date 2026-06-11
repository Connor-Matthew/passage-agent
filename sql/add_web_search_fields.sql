-- 第 11 期：增加 Web 搜索字段
-- 为 article 表添加联网搜索相关字段

ALTER TABLE article
ADD COLUMN enableWebSearch TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否启用联网搜索' AFTER isDelete,
ADD COLUMN webSearchContext TEXT COMMENT '联网搜索上下文（JSON格式）' AFTER enableWebSearch;