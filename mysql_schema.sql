-- MySQL schema for "胸部X光片影像智能分割与报告生成系统"
-- Source: MySQL_agent.md
-- Charset: utf8mb4

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- Table: role
CREATE TABLE IF NOT EXISTS `role` (
  `role_id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '角色ID（主键，自增）',
  `role_name` VARCHAR(50) NOT NULL COMMENT '角色名称：影像科医生/主治医生/管理员',
  `role_desc` VARCHAR(200) NULL COMMENT '角色权限描述',
  `create_time` DATETIME NOT NULL COMMENT '角色创建时间',
  `system_id` BIGINT NULL COMMENT '系统编号',
  PRIMARY KEY (`role_id`),
  UNIQUE KEY `uk_role_name` (`role_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='角色表';

-- Table: user
CREATE TABLE IF NOT EXISTS `user` (
  `user_id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '医生ID（主键，自增）',
  `login_name` VARCHAR(50) NOT NULL COMMENT '登录用户名（唯一，如医生工号）',
  `login_flag` SMALLINT NOT NULL COMMENT '登录方式：1为工号，2为手机号',
  `pwd` VARCHAR(100) NOT NULL COMMENT '密码',
  `real_name` VARCHAR(50) NOT NULL COMMENT '医生真实姓名',
  PRIMARY KEY (`user_id`),
  UNIQUE KEY `uk_user_login_name` (`login_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户表';

-- Table: operation_log
CREATE TABLE IF NOT EXISTS `operation_log` (
  `log_id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '日志ID（主键，自增）',
  `user_id` BIGINT NOT NULL COMMENT '操作用户ID（关联 user.user_id）',
  `user_name` VARCHAR(50) NOT NULL COMMENT '操作医生姓名（冗余存储便于查询）',
  `operation_type` VARCHAR(50) NOT NULL COMMENT '操作类型：X光片上传/报告审核/模型更新等',
  `operation_content` VARCHAR(500) NOT NULL COMMENT '操作详情描述',
  `operation_time` DATETIME NOT NULL COMMENT '操作发生时间',
  `ip_address` VARCHAR(50) NULL COMMENT '操作医生IP地址',
  `operation_status` SMALLINT NOT NULL COMMENT '操作状态：1成功，0失败',
  `system_id` BIGINT NULL COMMENT '系统编号',
  PRIMARY KEY (`log_id`),
  KEY `idx_operation_log_user_id` (`user_id`),
  KEY `idx_operation_log_time` (`operation_time`),
  CONSTRAINT `fk_operation_log_user`
    FOREIGN KEY (`user_id`) REFERENCES `user` (`user_id`)
    ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='系统操作日志表';

-- Table: xray_info
CREATE TABLE IF NOT EXISTS `xray_info` (
  `xray_id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'X光片记录ID（主键，自增）',
  `patient_id` VARCHAR(30) NOT NULL COMMENT '患者病历号（唯一）',
  `patient_name` VARCHAR(50) NOT NULL COMMENT '患者姓名',
  `patient_gender` SMALLINT NULL COMMENT '患者性别：1男，2女',
  `patient_age` SMALLINT NULL COMMENT '患者年龄',
  `xray_original_path` VARCHAR(255) NOT NULL COMMENT '原始X光片存储路径',
  `xray_format` VARCHAR(10) NOT NULL COMMENT '图片格式：JPG/PNG/DICOM',
  `upload_user_id` BIGINT NOT NULL COMMENT '上传医生ID（关联 user.user_id）',
  `upload_time` DATETIME NOT NULL COMMENT '上传时间',
  `segment_status` SMALLINT NOT NULL COMMENT '分割状态：0未分割，1分割中，2已完成，3失败',
  `update_time` DATETIME NULL COMMENT '状态更新时间',
  `system_id` BIGINT NULL COMMENT '系统编号',
  PRIMARY KEY (`xray_id`),
  UNIQUE KEY `uk_xray_patient_id` (`patient_id`),
  KEY `idx_xray_upload_user_id` (`upload_user_id`),
  KEY `idx_xray_upload_time` (`upload_time`),
  CONSTRAINT `fk_xray_info_user`
    FOREIGN KEY (`upload_user_id`) REFERENCES `user` (`user_id`)
    ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='患者X光片信息表';

-- Table: segment_result
CREATE TABLE IF NOT EXISTS `segment_result` (
  `segment_id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '分割结果ID（主键，自增）',
  `xray_id` BIGINT NOT NULL COMMENT '关联X光片ID（xray_info.xray_id）',
  `mask_path` VARCHAR(255) NOT NULL COMMENT '分割掩码图存储路径（心脏/双肺彩色叠加图）',
  `left_lung_view_path` VARCHAR(255) NOT NULL COMMENT '左肺局部视图存储路径',
  `right_lung_view_path` VARCHAR(255) NOT NULL COMMENT '右肺局部视图存储路径',
  `heart_view_path` VARCHAR(255) NOT NULL COMMENT '心脏局部视图存储路径',
  `heart_area` DECIMAL(10,2) NULL COMMENT '心脏分割区域面积（像素）',
  `left_lung_area` DECIMAL(10,2) NULL COMMENT '左肺分割区域面积（像素）',
  `right_lung_area` DECIMAL(10,2) NULL COMMENT '右肺分割区域面积（像素）',
  `model_version` VARCHAR(50) NOT NULL COMMENT '分割模型版本号',
  `segment_time` DATETIME NOT NULL COMMENT '分割完成时间',
  `system_id` BIGINT NULL COMMENT '系统编号',
  PRIMARY KEY (`segment_id`),
  KEY `idx_segment_result_xray_id` (`xray_id`),
  CONSTRAINT `fk_segment_result_xray`
    FOREIGN KEY (`xray_id`) REFERENCES `xray_info` (`xray_id`)
    ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='分割结果表';

-- Table: translate_record
CREATE TABLE IF NOT EXISTS `translate_record` (
  `translate_id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '翻译记录ID（主键，自增）',
  `segment_id` BIGINT NOT NULL COMMENT '关联分割结果ID（segment_result.segment_id）',
  `english_original` TEXT NOT NULL COMMENT '模型输出的英文诊断原文',
  `chinese_translate` TEXT NOT NULL COMMENT '翻译后的中文诊断文本',
  `translate_time` DATETIME NOT NULL COMMENT '翻译完成时间',
  `translate_status` SMALLINT NOT NULL COMMENT '翻译状态：1成功，0失败',
  `system_id` BIGINT NULL COMMENT '系统编号',
  PRIMARY KEY (`translate_id`),
  KEY `idx_translate_record_segment_id` (`segment_id`),
  CONSTRAINT `fk_translate_record_segment`
    FOREIGN KEY (`segment_id`) REFERENCES `segment_result` (`segment_id`)
    ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='翻译记录表';

-- Table: report_info
CREATE TABLE IF NOT EXISTS `report_info` (
  `report_id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '报告ID（主键，自增）',
  `xray_id` BIGINT NOT NULL COMMENT '关联X光片ID（xray_info.xray_id）',
  `segment_id` BIGINT NOT NULL COMMENT '关联分割结果ID（segment_result.segment_id）',
  `report_content` TEXT NOT NULL COMMENT '中文结构化诊断报告内容（含阳性/阴性发现）',
  `report_pdf_path` VARCHAR(255) NULL COMMENT '报告PDF文件存储路径',
  `generate_time` DATETIME NOT NULL COMMENT '报告生成时间',
  `audit_status` SMALLINT NOT NULL COMMENT '审核状态：0未审核，1通过，2驳回',
  `audit_user_id` BIGINT NULL COMMENT '审核医生ID（关联 user.user_id，影像科医生）',
  `audit_time` DATETIME NULL COMMENT '审核时间',
  `revise_content` TEXT NULL COMMENT '医生修订内容（为空则未修订）',
  `system_id` BIGINT NULL COMMENT '系统编号',
  PRIMARY KEY (`report_id`),
  KEY `idx_report_info_xray_id` (`xray_id`),
  KEY `idx_report_info_segment_id` (`segment_id`),
  KEY `idx_report_info_audit_user_id` (`audit_user_id`),
  CONSTRAINT `fk_report_info_xray`
    FOREIGN KEY (`xray_id`) REFERENCES `xray_info` (`xray_id`)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT `fk_report_info_segment`
    FOREIGN KEY (`segment_id`) REFERENCES `segment_result` (`segment_id`)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT `fk_report_info_audit_user`
    FOREIGN KEY (`audit_user_id`) REFERENCES `user` (`user_id`)
    ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='结构化诊断报告表';

-- Table: model_manage
CREATE TABLE IF NOT EXISTS `model_manage` (
  `model_id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '模型ID（主键，自增）',
  `model_name` VARCHAR(100) NOT NULL COMMENT '模型名称：如U-Net',
  `model_version` VARCHAR(50) NOT NULL COMMENT '模型版本号（唯一）',
  `model_type` SMALLINT NOT NULL COMMENT '模型类型：1语义分割，2特征提取',
  `model_path` VARCHAR(255) NOT NULL COMMENT '模型文件存储路径',
  `is_default` SMALLINT NOT NULL COMMENT '是否默认模型：0否，1是',
  `create_user_id` BIGINT NOT NULL COMMENT '创建管理员ID（关联 user.user_id）',
  `create_time` DATETIME NOT NULL COMMENT '模型上传/创建时间',
  `model_desc` VARCHAR(500) NULL COMMENT '模型功能描述',
  `system_id` BIGINT NULL COMMENT '系统编号',
  PRIMARY KEY (`model_id`),
  UNIQUE KEY `uk_model_manage_version` (`model_version`),
  KEY `idx_model_manage_create_user_id` (`create_user_id`),
  CONSTRAINT `fk_model_manage_user`
    FOREIGN KEY (`create_user_id`) REFERENCES `user` (`user_id`)
    ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='模型管理表';

SET FOREIGN_KEY_CHECKS = 1;
