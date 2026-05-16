#!/usr/bin/env python3
"""
迁移脚本：新增 report_history 表，并把现有 report_info 回填为 baseline 快照。

执行方式：
    cd /data/home/zyx/Ir-UNet/DACG/DACG-Struct/backend
    python scripts/migrate_report_history.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config import settings


CREATE_REPORT_HISTORY_SQL = """
CREATE TABLE IF NOT EXISTS `report_history` (
  `history_id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '报告历史ID（主键，自增）',
  `report_id` BIGINT NOT NULL COMMENT '关联报告ID（report_info.report_id）',
  `xray_id` BIGINT NOT NULL COMMENT '关联X光片ID（xray_info.xray_id）',
  `segment_id` BIGINT NOT NULL COMMENT '关联分割结果ID（segment_result.segment_id）',
  `parent_history_id` BIGINT NULL COMMENT '上一版报告历史ID，用于形成追溯链条',
  `action_type` VARCHAR(50) NOT NULL COMMENT '动作类型',
  `action_user_id` BIGINT NULL COMMENT '执行动作的用户ID',
  `action_time` DATETIME NOT NULL COMMENT '动作发生时间',
  `action_note` VARCHAR(255) NULL COMMENT '动作备注',
  `report_content` TEXT NOT NULL COMMENT '该历史版本的报告正文快照',
  `revise_content` TEXT NULL COMMENT '该历史版本的修订内容快照',
  `report_pdf_path` VARCHAR(255) NULL COMMENT '该历史版本的PDF路径快照',
  `generate_time` DATETIME NULL COMMENT '该历史版本对应的报告生成时间',
  `audit_status` SMALLINT NOT NULL COMMENT '该历史版本的审核状态快照',
  `audit_user_id` BIGINT NULL COMMENT '该历史版本的审核医生ID',
  `audit_time` DATETIME NULL COMMENT '该历史版本的审核时间',
  `system_id` BIGINT NULL COMMENT '系统编号',
  PRIMARY KEY (`history_id`),
  KEY `idx_report_history_report_id` (`report_id`),
  KEY `idx_report_history_xray_id` (`xray_id`),
  KEY `idx_report_history_parent_id` (`parent_history_id`),
  KEY `idx_report_history_action_time` (`action_time`),
  KEY `idx_report_history_action_user_id` (`action_user_id`),
  CONSTRAINT `fk_report_history_report`
    FOREIGN KEY (`report_id`) REFERENCES `report_info` (`report_id`)
    ON UPDATE CASCADE ON DELETE CASCADE,
  CONSTRAINT `fk_report_history_xray`
    FOREIGN KEY (`xray_id`) REFERENCES `xray_info` (`xray_id`)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT `fk_report_history_segment`
    FOREIGN KEY (`segment_id`) REFERENCES `segment_result` (`segment_id`)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT `fk_report_history_parent`
    FOREIGN KEY (`parent_history_id`) REFERENCES `report_history` (`history_id`)
    ON UPDATE CASCADE ON DELETE SET NULL,
  CONSTRAINT `fk_report_history_action_user`
    FOREIGN KEY (`action_user_id`) REFERENCES `user` (`user_id`)
    ON UPDATE CASCADE ON DELETE SET NULL,
  CONSTRAINT `fk_report_history_audit_user`
    FOREIGN KEY (`audit_user_id`) REFERENCES `user` (`user_id`)
    ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='结构化诊断报告历史快照表'
"""

BACKFILL_BASELINE_SQL = """
INSERT INTO `report_history` (
  `report_id`,
  `xray_id`,
  `segment_id`,
  `parent_history_id`,
  `action_type`,
  `action_user_id`,
  `action_time`,
  `action_note`,
  `report_content`,
  `revise_content`,
  `report_pdf_path`,
  `generate_time`,
  `audit_status`,
  `audit_user_id`,
  `audit_time`,
  `system_id`
)
SELECT
  r.`report_id`,
  r.`xray_id`,
  r.`segment_id`,
  NULL,
  'baseline',
  NULL,
  COALESCE(r.`generate_time`, NOW()),
  '迁移时回填的当前报告快照',
  r.`report_content`,
  r.`revise_content`,
  r.`report_pdf_path`,
  r.`generate_time`,
  r.`audit_status`,
  r.`audit_user_id`,
  r.`audit_time`,
  r.`system_id`
FROM `report_info` r
WHERE NOT EXISTS (
  SELECT 1
  FROM `report_history` h
  WHERE h.`report_id` = r.`report_id`
)
"""


def migrate_report_history() -> bool:
    engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True, future=True)
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = session_local()
    try:
        db.execute(text(CREATE_REPORT_HISTORY_SQL))
        result = db.execute(text(BACKFILL_BASELINE_SQL))
        db.commit()
        print("report_history 迁移完成")
        print(f"回填 baseline 快照: {result.rowcount} 条")
        return True
    except Exception as exc:
        db.rollback()
        print(f"report_history 迁移失败: {exc}")
        return False
    finally:
        db.close()


if __name__ == "__main__":
    ok = migrate_report_history()
    sys.exit(0 if ok else 1)
