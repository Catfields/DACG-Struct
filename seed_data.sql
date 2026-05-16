SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- roles
INSERT INTO `role` (`role_id`, `role_name`, `role_desc`, `create_time`, `system_id`) VALUES
  (1, '影像科医生', '影像科医生可审核修订报告', '2026-03-10 09:00:00', 1),
  (2, '主治医生', '主治医生可上传与查看报告', '2026-03-10 09:05:00', 1),
  (3, '管理员', '系统与模型管理权限', '2026-03-10 09:10:00', 1);

-- users
INSERT INTO `user` (`user_id`, `login_name`, `login_flag`, `pwd`, `real_name`) VALUES
  (1, 'RAD001', 1, 'pass@RAD001', '李明'),
  (2, 'RAD002', 1, 'pass@RAD002', '王雪'),
  (3, 'ATT001', 1, 'pass@ATT001', '赵强'),
  (4, 'ADMIN01', 1, 'pass@ADMIN01', '周敏'),
  (5, 'RAD003', 1, 'pass@RAD003', '陈宇');

-- model management
INSERT INTO `model_manage` (`model_id`, `model_name`, `model_version`, `model_type`, `model_path`, `is_default`, `create_user_id`, `create_time`, `model_desc`, `system_id`) VALUES
  (1, 'U-Net', 'unet-v1.2.0', 1, '/models/unet/v1.2.0/model.pth', 1, 4, '2026-03-11 10:00:00', '基于U-Net的胸部X光片分割模型', 1),
  (2, 'U-Net', 'unet-v1.1.0', 1, '/models/unet/v1.1.0/model.pth', 0, 4, '2026-03-01 10:00:00', '历史版本模型', 1),
  (3, 'ResNet-50', 'resnet50-feat-v1.0.0', 2, '/models/resnet50/v1.0.0/model.pth', 0, 4, '2026-03-05 11:30:00', '特征提取模型', 1),
  (4, 'Attention U-Net', 'attention-unet-v1.0', 1, '/data/home/zyx/Ir-UNet/DACG/DACG-Struct/backend/ml_models/seg_models/attention_unet_model.pth', 0, 4, '2026-03-18 10:14:00', '基于 Attention U-Net 的胸部X光片分割模型', 1);

-- xray info
INSERT INTO `xray_info` (`xray_id`, `patient_id`, `patient_name`, `patient_gender`, `patient_age`, `xray_original_path`, `xray_format`, `upload_user_id`, `upload_time`, `segment_status`, `update_time`, `system_id`) VALUES
  (1, 'MRN20260317001', '张晨', 1, 45, '/data/xray/2026/03/17/MRN20260317001.png', 'PNG', 1, '2026-03-17 08:12:00', 2, '2026-03-17 08:25:00', 1),
  (2, 'MRN20260317002', '刘芳', 2, 52, '/data/xray/2026/03/17/MRN20260317002.jpg', 'JPG', 2, '2026-03-17 09:05:00', 2, '2026-03-17 09:18:00', 1),
  (3, 'MRN20260316003', '孙杰', 1, 36, '/data/xray/2026/03/16/MRN20260316003.dcm', 'DICOM', 3, '2026-03-16 16:20:00', 2, '2026-03-16 16:40:00', 1),
  (4, 'MRN20260315004', '何静', 2, 64, '/data/xray/2026/03/15/MRN20260315004.png', 'PNG', 5, '2026-03-15 14:10:00', 2, '2026-03-15 14:35:00', 1),
  (5, 'MRN20260314005', '高磊', 1, 28, '/data/xray/2026/03/14/MRN20260314005.jpg', 'JPG', 1, '2026-03-14 10:50:00', 2, '2026-03-14 11:12:00', 1),
  (6, 'MRN20260313006', '唐梅', 2, 57, '/data/xray/2026/03/13/MRN20260313006.png', 'PNG', 2, '2026-03-13 09:30:00', 2, '2026-03-13 09:55:00', 1);

-- segment results
INSERT INTO `segment_result` (`segment_id`, `xray_id`, `mask_path`, `left_lung_view_path`, `right_lung_view_path`, `heart_view_path`, `heart_area`, `left_lung_area`, `right_lung_area`, `model_version`, `segment_time`, `system_id`) VALUES
  (1, 1, '/data/seg/2026/03/17/MRN20260317001_mask.png', '/data/seg/2026/03/17/MRN20260317001_left.png', '/data/seg/2026/03/17/MRN20260317001_right.png', '/data/seg/2026/03/17/MRN20260317001_heart.png', 15234.50, 46321.20, 47110.80, 'unet-v1.2.0', '2026-03-17 08:24:00', 1),
  (2, 2, '/data/seg/2026/03/17/MRN20260317002_mask.png', '/data/seg/2026/03/17/MRN20260317002_left.png', '/data/seg/2026/03/17/MRN20260317002_right.png', '/data/seg/2026/03/17/MRN20260317002_heart.png', 14890.10, 45510.40, 46222.30, 'unet-v1.2.0', '2026-03-17 09:17:00', 1),
  (3, 3, '/data/seg/2026/03/16/MRN20260316003_mask.png', '/data/seg/2026/03/16/MRN20260316003_left.png', '/data/seg/2026/03/16/MRN20260316003_right.png', '/data/seg/2026/03/16/MRN20260316003_heart.png', 16002.00, 47080.70, 47890.60, 'unet-v1.1.0', '2026-03-16 16:38:00', 1),
  (4, 4, '/data/seg/2026/03/15/MRN20260315004_mask.png', '/data/seg/2026/03/15/MRN20260315004_left.png', '/data/seg/2026/03/15/MRN20260315004_right.png', '/data/seg/2026/03/15/MRN20260315004_heart.png', 17012.80, 45200.00, 46050.90, 'unet-v1.2.0', '2026-03-15 14:33:00', 1),
  (5, 5, '/data/seg/2026/03/14/MRN20260314005_mask.png', '/data/seg/2026/03/14/MRN20260314005_left.png', '/data/seg/2026/03/14/MRN20260314005_right.png', '/data/seg/2026/03/14/MRN20260314005_heart.png', 14220.30, 48990.10, 49510.20, 'unet-v1.2.0', '2026-03-14 11:10:00', 1),
  (6, 6, '/data/seg/2026/03/13/MRN20260313006_mask.png', '/data/seg/2026/03/13/MRN20260313006_left.png', '/data/seg/2026/03/13/MRN20260313006_right.png', '/data/seg/2026/03/13/MRN20260313006_heart.png', 15580.60, 46820.50, 47240.40, 'unet-v1.1.0', '2026-03-13 09:52:00', 1);

-- translation records
INSERT INTO `translate_record` (`translate_id`, `segment_id`, `english_original`, `chinese_translate`, `translate_time`, `translate_status`, `system_id`) VALUES
  (1, 1, 'No acute cardiopulmonary abnormality. Mild vascular congestion.', '未见急性心肺异常。可见轻度肺血管充盈。', '2026-03-17 08:26:00', 1, 1),
  (2, 2, 'Patchy opacity in the right lower lobe, consider pneumonia.', '右下叶片状致密影，考虑肺炎可能。', '2026-03-17 09:20:00', 1, 1),
  (3, 3, 'Hyperinflation with flattened diaphragms, suggestive of COPD.', '肺过度充气伴膈肌变平，提示慢阻肺。', '2026-03-16 16:42:00', 1, 1),
  (4, 4, 'Enlarged cardiac silhouette. No pleural effusion.', '心影增大。未见胸腔积液。', '2026-03-15 14:36:00', 1, 1),
  (5, 5, 'Left basilar atelectasis. No focal consolidation.', '左下肺不张。未见局灶性实变。', '2026-03-14 11:13:00', 1, 1),
  (6, 6, 'Mild interstitial markings, likely chronic changes.', '轻度间质纹理增多，考虑慢性改变。', '2026-03-13 09:58:00', 1, 1);

-- report info
INSERT INTO `report_info` (`report_id`, `xray_id`, `segment_id`, `report_content`, `report_pdf_path`, `generate_time`, `audit_status`, `audit_user_id`, `audit_time`, `revise_content`, `system_id`) VALUES
  (1, 1, 1, '阴性发现：未见急性心肺异常。阳性发现：轻度肺血管充盈。建议结合临床。', '/data/report/2026/03/17/MRN20260317001.pdf', '2026-03-17 08:27:00', 1, 5, '2026-03-17 10:05:00', NULL, 1),
  (2, 2, 2, '阳性发现：右下叶片状致密影，考虑感染。阴性发现：未见胸腔积液。', '/data/report/2026/03/17/MRN20260317002.pdf', '2026-03-17 09:22:00', 0, NULL, NULL, NULL, 1),
  (3, 3, 3, '阳性发现：肺过度充气、膈肌变平。阴性发现：未见明显实变。', '/data/report/2026/03/16/MRN20260316003.pdf', '2026-03-16 16:45:00', 1, 1, '2026-03-16 18:10:00', '建议补充肺功能检查。', 1),
  (4, 4, 4, '阳性发现：心影增大。阴性发现：未见胸腔积液。', '/data/report/2026/03/15/MRN20260315004.pdf', '2026-03-15 14:40:00', 2, 2, '2026-03-15 17:00:00', '请补充心脏超声结果后再评估。', 1),
  (5, 5, 5, '阳性发现：左下肺不张。阴性发现：未见局灶性实变。', '/data/report/2026/03/14/MRN20260314005.pdf', '2026-03-14 11:15:00', 1, 5, '2026-03-14 13:20:00', NULL, 1),
  (6, 6, 6, '阳性发现：间质纹理增多。阴性发现：未见明显实变。', '/data/report/2026/03/13/MRN20260313006.pdf', '2026-03-13 10:00:00', 1, 1, '2026-03-13 12:30:00', NULL, 1);

-- report history baselines
INSERT INTO `report_history` (`history_id`, `report_id`, `xray_id`, `segment_id`, `parent_history_id`, `action_type`, `action_user_id`, `action_time`, `action_note`, `report_content`, `revise_content`, `report_pdf_path`, `generate_time`, `audit_status`, `audit_user_id`, `audit_time`, `system_id`) VALUES
  (1, 1, 1, 1, NULL, 'baseline', NULL, '2026-03-17 08:27:00', '初始演示报告快照', '阴性发现：未见急性心肺异常。阳性发现：轻度肺血管充盈。建议结合临床。', NULL, '/data/report/2026/03/17/MRN20260317001.pdf', '2026-03-17 08:27:00', 1, 5, '2026-03-17 10:05:00', 1),
  (2, 2, 2, 2, NULL, 'baseline', NULL, '2026-03-17 09:22:00', '初始演示报告快照', '阳性发现：右下叶片状致密影，考虑感染。阴性发现：未见胸腔积液。', NULL, '/data/report/2026/03/17/MRN20260317002.pdf', '2026-03-17 09:22:00', 0, NULL, NULL, 1),
  (3, 3, 3, 3, NULL, 'baseline', NULL, '2026-03-16 16:45:00', '初始演示报告快照', '阳性发现：肺过度充气、膈肌变平。阴性发现：未见明显实变。', '建议补充肺功能检查。', '/data/report/2026/03/16/MRN20260316003.pdf', '2026-03-16 16:45:00', 1, 1, '2026-03-16 18:10:00', 1),
  (4, 4, 4, 4, NULL, 'baseline', NULL, '2026-03-15 14:40:00', '初始演示报告快照', '阳性发现：心影增大。阴性发现：未见胸腔积液。', '请补充心脏超声结果后再评估。', '/data/report/2026/03/15/MRN20260315004.pdf', '2026-03-15 14:40:00', 2, 2, '2026-03-15 17:00:00', 1),
  (5, 5, 5, 5, NULL, 'baseline', NULL, '2026-03-14 11:15:00', '初始演示报告快照', '阳性发现：左下肺不张。阴性发现：未见局灶性实变。', NULL, '/data/report/2026/03/14/MRN20260314005.pdf', '2026-03-14 11:15:00', 1, 5, '2026-03-14 13:20:00', 1),
  (6, 6, 6, 6, NULL, 'baseline', NULL, '2026-03-13 10:00:00', '初始演示报告快照', '阳性发现：间质纹理增多。阴性发现：未见明显实变。', NULL, '/data/report/2026/03/13/MRN20260313006.pdf', '2026-03-13 10:00:00', 1, 1, '2026-03-13 12:30:00', 1);

-- operation logs
INSERT INTO `operation_log` (`log_id`, `user_id`, `user_name`, `operation_type`, `operation_content`, `operation_time`, `ip_address`, `operation_status`, `system_id`) VALUES
  (1, 1, '李明', 'X光片上传', '上传患者张晨的X光片', '2026-03-17 08:12:30', '10.0.0.11', 1, 1),
  (2, 2, '王雪', 'X光片上传', '上传患者刘芳的X光片', '2026-03-17 09:05:30', '10.0.0.12', 1, 1),
  (3, 3, '赵强', '报告审核', '审核患者孙杰报告并通过', '2026-03-16 18:10:30', '10.0.0.21', 1, 1),
  (4, 4, '周敏', '模型更新', '上传并设置默认模型 unet-v1.2.0', '2026-03-11 10:05:00', '10.0.0.31', 1, 1),
  (5, 5, '陈宇', '报告审核', '审核患者张晨报告并通过', '2026-03-17 10:05:30', '10.0.0.14', 1, 1),
  (6, 2, '王雪', '报告审核', '驳回患者何静报告，需补充检查', '2026-03-15 17:01:00', '10.0.0.12', 1, 1);

SET FOREIGN_KEY_CHECKS = 1;
