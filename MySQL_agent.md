# 胸部X光片影像智能分割与报告生成系统 数据库表字段说明（三线表版）

## 表 3-1 角色表 role 字段说明

| 列名        | 字段类型     | 是否可为空 | 备注                                         |
| ----------- | ------------ | ---------- | -------------------------------------------- |
| role_id     | int8         | 否         | 角色ID（主键，自增）                         |
| role_name   | varchar(50)  | 否         | 角色名称：影像科医生/主治医生/管理员         |
| role_desc   | varchar(200) | 是         | 角色权限描述（如：影像科医生可审核修订报告） |
| create_time | datetime     | 否         | 角色创建时间                                 |
| system_id   | int8         | 是         | 系统编号                                     |

## 表 3-2 用户表 user 字段说明

| 列名       | 字段类型     | 是否可为空 | 备注                           |
| ---------- | ------------ | ---------- | ------------------------------ |
| user_id    | int8         | 否         | 医生ID（主键，自增）           |
| login_name | varchar(50)  | 否         | 登录用户名（唯一，如医生工号） |
| login_flag | int2         | 否         | 登录方式：1为工号，2为手机号   |
| pwd        | varchar(100) | 否         | 密码                           |
| real_name  | varchar(50)  | 否         | 医生真实姓名                   |


## 表 3-3 系统操作日志表  operation_log 字段说明

| 列名              | 字段类型     | 是否可为空 | 备注                                          |
| ----------------- | ------------ | ---------- | --------------------------------------------- |
| log_id            | int8         | 否         | 日志ID（主键，自增）                          |
| user_id           | int8         | 否         | 操作用户ID（关联 user.user_id，即医生ID）     |
| user_name         | varchar(50)  | 否         | 操作医生姓名（冗余存储便于查询）              |
| operation_type    | varchar(50)  | 否         | 操作类型：X光片上传/报告审核/模型更新等       |
| operation_content | varchar(500) | 否         | 操作详情描述（如：医生XXX上传患者XXX的X光片） |
| operation_time    | datetime     | 否         | 操作发生时间                                  |
| ip_address        | varchar(50)  | 是         | 操作医生IP地址                                |
| operation_status  | int2         | 否         | 操作状态：1成功，0失败                        |
| system_id         | int8         | 是         | 系统编号                                      |

## 表 3-4 患者X光片信息表 xray_info 字段说明

| 列名               | 字段类型     | 是否可为空 | 备注                                       |
| ------------------ | ------------ | ---------- | ------------------------------------------ |
| xray_id            | int8         | 否         | X光片记录ID（主键，自增）                  |
| patient_id         | varchar(30)  | 否         | 患者病历号（唯一）                         |
| patient_name       | varchar(50)  | 否         | 患者姓名                                   |
| patient_gender     | int2         | 是         | 患者性别：1男，2女                         |
| patient_age        | int2         | 是         | 患者年龄                                   |
| xray_original_path | varchar(255) | 否         | 原始X光片存储路径                          |
| xray_format        | varchar(10)  | 否         | 图片格式：JPG/PNG/DICOM                    |
| upload_user_id     | int8         | 否         | 上传医生ID（关联 user.user_id）            |
| upload_time        | datetime     | 否         | 上传时间                                   |
| segment_status     | int2         | 否         | 分割状态：0未分割，1分割中，2已完成，3失败 |
| update_time        | datetime     | 是         | 状态更新时间                               |
| system_id          | int8         | 是         | 系统编号                                   |

## 表 3-5 分割结果表 segment_result 字段说明

| 列名                 | 字段类型     | 是否可为空 | 备注                                      |
| -------------------- | ------------ | ---------- | ----------------------------------------- |
| segment_id           | int8         | 否         | 分割结果ID（主键，自增）                  |
| xray_id              | int8         | 否         | 关联X光片ID（xray_info.xray_id）          |
| mask_path            | varchar(255) | 否         | 分割掩码图存储路径（心脏/双肺彩色叠加图） |
| left_lung_view_path  | varchar(255) | 否         | 左肺局部视图存储路径                      |
| right_lung_view_path | varchar(255) | 否         | 右肺局部视图存储路径                      |
| heart_view_path      | varchar(255) | 否         | 心脏局部视图存储路径                      |
| heart_area           | float(10,2)  | 是         | 心脏分割区域面积（像素）                  |
| left_lung_area       | float(10,2)  | 是         | 左肺分割区域面积（像素）                  |
| right_lung_area      | float(10,2)  | 是         | 右肺分割区域面积（像素）                  |
| model_version        | varchar(50)  | 否         | 分割模型版本号                            |
| segment_time         | datetime     | 否         | 分割完成时间                              |
| system_id            | int8         | 是         | 系统编号                                  |

## 表 3-6 翻译记录表 translate_record 字段说明

| 列名              | 字段类型 | 是否可为空 | 备注                                        |
| ----------------- | -------- | ---------- | ------------------------------------------- |
| translate_id      | int8     | 否         | 翻译记录ID（主键，自增）                    |
| segment_id        | int8     | 否         | 关联分割结果ID（segment_result.segment_id） |
| english_original  | text     | 否         | 模型输出的英文诊断原文                      |
| chinese_translate | text     | 否         | 豆包大模型翻译后的中文诊断文本              |
| translate_time    | datetime | 否         | 翻译完成时间                                |
| translate_status  | int2     | 否         | 翻译状态：1成功，0失败                      |
| system_id         | int8     | 是         | 系统编号                                    |

## 表 3-7 结构化诊断报告表 report_info 字段说明

| 列名            | 字段类型     | 是否可为空 | 备注                                        |
| --------------- | ------------ | ---------- | ------------------------------------------- |
| report_id       | int8         | 否         | 报告ID（主键，自增）                        |
| xray_id         | int8         | 否         | 关联X光片ID（xray_info.xray_id）            |
| segment_id      | int8         | 否         | 关联分割结果ID（segment_result.segment_id） |
| report_content  | text         | 否         | 中文结构化诊断报告内容（含阳性/阴性发现）   |
| report_pdf_path | varchar(255) | 是         | 报告PDF文件存储路径                         |
| generate_time   | datetime     | 否         | 报告生成时间                                |
| audit_status    | int2         | 否         | 审核状态：0未审核，1通过，2驳回             |
| audit_user_id   | int8         | 是         | 审核医生ID（关联 user.user_id，影像科医生） |
| audit_time      | datetime     | 是         | 审核时间                                    |
| revise_content  | text         | 是         | 医生修订内容（为空则未修订）                |
| system_id       | int8         | 是         | 系统编号                                    |

## 表 3-8 模型管理表 model_manage 字段说明

| 列名           | 字段类型     | 是否可为空 | 备注                                             |
| -------------- | ------------ | ---------- | ------------------------------------------------ |
| model_id       | int8         | 否         | 模型ID（主键，自增）                             |
| model_name     | varchar(100) | 否         | 模型名称：如U-Net                                |
| model_version  | varchar(50)  | 否         | 模型版本号（唯一）                               |
| model_type     | int2         | 否         | 模型类型：1语义分割，2特征提取                   |
| model_path     | varchar(255) | 否         | 模型文件存储路径                                 |
| is_default     | int2         | 否         | 是否默认模型：0否，1是                           |
| create_user_id | int8         | 否         | 创建管理员ID（关联 user.user_id）                |
| create_time    | datetime     | 否         | 模型上传/创建时间                                |
| model_desc     | varchar(500) | 是         | 模型功能描述（如：基于U-Net，适配胸部X光片分割） |
| system_id      | int8         | 是         | 系统编号                                         |
