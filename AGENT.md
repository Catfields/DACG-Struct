# AGENT.md — 胸部X光影像诊断后端系统开发指南

> 本文档用于指导 AI Coding Agent（如 OpenAI Codex、GitHub Copilot Agent、Cursor 等）
> 辅助开发基于 FastAPI 的医疗影像诊断后端系统。**请完整阅读本文档后再开始生成任何代码。**

---

## 0. 项目概览

| 项目        | 说明                                              |
|-------------|---------------------------------------------------|
| 框架        | Python 3.10 + FastAPI                            |
| 数据库      | MySQL 8.x（通过 SQLAlchemy ORM 访问）             |
| 影像处理    | OpenCV + PyTorch（DACG/U-Net 分割模型）           |
| 存储        | 本地文件系统（影像原图 + 掩码 + 局部视图 + PDF）  |
| 外部 API    | 火山引擎豆包大模型（通过 OpenAI SDK 接入）        |
| 鉴权        | JWT（python-jose）+ `role` 表 + `user` 表联合校验 |
| 报告导出    | PDF（ReportLab）                                  |
| 部署目标    | Docker 容器化，支持单机或 Compose 部署            |

---

## 1. 项目目录结构

严格按照以下结构组织代码，不得随意新增顶层目录：

```
backend/
├── app/
│   ├── main.py                      # FastAPI 应用入口，注册所有 router
│   ├── config.py                    # 全局配置（pydantic-settings，从 .env 读取）
│   ├── database.py                  # SQLAlchemy engine / SessionLocal / Base
│   ├── dependencies.py              # 公共依赖注入（get_db, get_current_user 等）
│   │
│   ├── models/                      # SQLAlchemy ORM 模型（严格对应数据库表）
│   │   ├── role.py                  # → 表 role
│   │   ├── user.py                  # → 表 user
│   │   ├── operation_log.py         # → 表 operation_log
│   │   ├── xray_info.py             # → 表 xray_info
│   │   ├── segment_result.py        # → 表 segment_result
│   │   ├── translate_record.py      # → 表 translate_record
│   │   ├── report_info.py           # → 表 report_info
│   │   └── model_manage.py          # → 表 model_manage
│   │
│   ├── schemas/                     # Pydantic 请求/响应 Schema（与 ORM 模型分离）
│   │   ├── auth.py
│   │   ├── user.py
│   │   ├── xray.py
│   │   ├── segment.py
│   │   ├── report.py
│   │   └── model.py
│   │
│   ├── routers/                     # 路由层（薄层，只做参数校验和调用 service）
│   │   ├── auth.py                  # 登录、刷新 Token
│   │   ├── users.py                 # 用户管理（仅 admin）
│   │   ├── xray.py                  # X光片上传与分割任务
│   │   ├── reports.py               # 报告查看、审核修订、PDF 导出
│   │   └── admin.py                 # 日志审计、模型版本管理
│   │
│   ├── services/                    # 业务逻辑层
│   │   ├── auth_service.py          # 登录验证、Token 签发
│   │   ├── user_service.py          # 用户 CRUD
│   │   ├── xray_service.py          # 上传入库、触发分割
│   │   ├── segmentation_service.py  # OpenCV 预处理 + PyTorch 推理
│   │   ├── generation_service.py    # 诊断条目生成（英文结构化输出）
│   │   ├── translation_service.py   # 豆包 API 翻译
│   │   ├── report_service.py        # 报告组装、审核、PDF 导出
│   │   ├── model_service.py         # 模型版本管理
│   │   └── log_service.py           # 操作日志写入
│   │
│   ├── core/
│   │   ├── security.py              # JWT 签发与解析、密码哈希
│   │   ├── permissions.py           # 角色常量、require_roles 依赖工厂
│   │   └── exceptions.py            # 统一异常类定义
│   │
│   └── utils/
│       ├── file_storage.py          # 文件读写工具（路径生成、保存、删除）
│       └── logger.py                # 结构化日志配置
│
├── ml_models/                       # 存放 .pth 权重文件（不提交至 Git）
├── storage/
│   ├── uploads/                     # 原始 X 光片
│   ├── masks/                       # 分割掩码叠加图
│   ├── views/                       # 局部视图（left_lung / right_lung / heart）
│   └── reports/                     # 导出的 PDF 报告
├── tests/
├── alembic/
├── requirements.txt
├── .env.example
├── Dockerfile
└── docker-compose.yml
```

---

## 2. 数据库表与 ORM 模型

> ⚠️ **以下表结构为权威定义。ORM 模型字段必须与此严格一致，禁止自行增减字段。**
> `user` 表中存在若干待补充字段，Agent 应预留 `role_id`（FK → role.role_id）、
> `phone`（varchar(20)，可为空）两个字段，其余不得臆测补充。

### 2.1 role 表 — 角色表

```python
# app/models/role.py
class Role(Base):
    __tablename__ = "role"
    role_id     = Column(BigInteger, primary_key=True, autoincrement=True)
    role_name   = Column(String(50), nullable=False)   # 影像科医生 / 主治医生 / 管理员
    role_desc   = Column(String(200), nullable=True)
    create_time = Column(DateTime, nullable=False, default=func.now())
    system_id   = Column(BigInteger, nullable=True)
```

### 2.2 user 表 — 用户表

```python
# app/models/user.py
class User(Base):
    __tablename__ = "user"
    user_id    = Column(BigInteger, primary_key=True, autoincrement=True)
    login_name = Column(String(50), nullable=False, unique=True)
    login_flag = Column(SmallInteger, nullable=False)  # 1=工号, 2=手机号
    pwd        = Column(String(100), nullable=False)   # bcrypt 哈希后存储
    real_name  = Column(String(50), nullable=False)
    role_id    = Column(BigInteger, ForeignKey("role.role_id"), nullable=True)
    phone      = Column(String(20), nullable=True)
    # 关系
    role       = relationship("Role", back_populates="users")
```

### 2.3 operation_log 表 — 系统操作日志表

```python
# app/models/operation_log.py
class OperationLog(Base):
    __tablename__ = "operation_log"
    log_id            = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id           = Column(BigInteger, ForeignKey("user.user_id"), nullable=False)
    user_name         = Column(String(50), nullable=False)   # 冗余存储，便于日志查询
    operation_type    = Column(String(50), nullable=False)   # X光片上传/报告审核/模型更新等
    operation_content = Column(String(500), nullable=False)
    operation_time    = Column(DateTime, nullable=False, default=func.now())
    ip_address        = Column(String(50), nullable=True)
    operation_status  = Column(SmallInteger, nullable=False) # 1=成功, 0=失败
    system_id         = Column(BigInteger, nullable=True)
```

### 2.4 xray_info 表 — 患者X光片信息表

```python
# app/models/xray_info.py
class XrayInfo(Base):
    __tablename__ = "xray_info"
    xray_id            = Column(BigInteger, primary_key=True, autoincrement=True)
    patient_id         = Column(String(30), nullable=False, unique=True)  # 病历号
    patient_name       = Column(String(50), nullable=False)
    patient_gender     = Column(SmallInteger, nullable=True)  # 1=男, 2=女
    patient_age        = Column(SmallInteger, nullable=True)
    xray_original_path = Column(String(255), nullable=False)
    xray_format        = Column(String(10), nullable=False)   # JPG/PNG/DICOM
    upload_user_id     = Column(BigInteger, ForeignKey("user.user_id"), nullable=False)
    upload_time        = Column(DateTime, nullable=False, default=func.now())
    segment_status     = Column(SmallInteger, nullable=False, default=0)
    # 0=未分割, 1=分割中, 2=已完成, 3=失败
    update_time        = Column(DateTime, nullable=True, onupdate=func.now())
    system_id          = Column(BigInteger, nullable=True)
```

### 2.5 segment_result 表 — 分割结果表

```python
# app/models/segment_result.py
class SegmentResult(Base):
    __tablename__ = "segment_result"
    segment_id           = Column(BigInteger, primary_key=True, autoincrement=True)
    xray_id              = Column(BigInteger, ForeignKey("xray_info.xray_id"), nullable=False)
    mask_path            = Column(String(255), nullable=False)   # 心脏/双肺彩色叠加图
    left_lung_view_path  = Column(String(255), nullable=False)
    right_lung_view_path = Column(String(255), nullable=False)
    heart_view_path      = Column(String(255), nullable=False)
    heart_area           = Column(Float, nullable=True)          # 像素面积
    left_lung_area       = Column(Float, nullable=True)
    right_lung_area      = Column(Float, nullable=True)
    model_version        = Column(String(50), nullable=False)    # 来自 model_manage.model_version
    segment_time         = Column(DateTime, nullable=False, default=func.now())
    system_id            = Column(BigInteger, nullable=True)
```

### 2.6 translate_record 表 — 翻译记录表

```python
# app/models/translate_record.py
class TranslateRecord(Base):
    __tablename__ = "translate_record"
    translate_id      = Column(BigInteger, primary_key=True, autoincrement=True)
    segment_id        = Column(BigInteger, ForeignKey("segment_result.segment_id"), nullable=False)
    english_original  = Column(Text, nullable=False)   # generation_service 输出的英文诊断原文
    chinese_translate = Column(Text, nullable=False)   # 豆包翻译后的中文
    translate_time    = Column(DateTime, nullable=False, default=func.now())
    translate_status  = Column(SmallInteger, nullable=False)  # 1=成功, 0=失败
    system_id         = Column(BigInteger, nullable=True)
```

### 2.7 report_info 表 — 结构化诊断报告表

```python
# app/models/report_info.py
class ReportInfo(Base):
    __tablename__ = "report_info"
    report_id       = Column(BigInteger, primary_key=True, autoincrement=True)
    xray_id         = Column(BigInteger, ForeignKey("xray_info.xray_id"), nullable=False)
    segment_id      = Column(BigInteger, ForeignKey("segment_result.segment_id"), nullable=False)
    report_content  = Column(Text, nullable=False)         # 中文结构化报告正文
    report_pdf_path = Column(String(255), nullable=True)   # 导出后回填
    generate_time   = Column(DateTime, nullable=False, default=func.now())
    audit_status    = Column(SmallInteger, nullable=False, default=0)
    # 0=未审核, 1=通过, 2=驳回
    audit_user_id   = Column(BigInteger, ForeignKey("user.user_id"), nullable=True)
    audit_time      = Column(DateTime, nullable=True)
    revise_content  = Column(Text, nullable=True)          # 为空表示未修订
    system_id       = Column(BigInteger, nullable=True)
```

### 2.8 model_manage 表 — 模型管理表

```python
# app/models/model_manage.py
class ModelManage(Base):
    __tablename__ = "model_manage"
    model_id       = Column(BigInteger, primary_key=True, autoincrement=True)
    model_name     = Column(String(100), nullable=False)
    model_version  = Column(String(50), nullable=False, unique=True)
    model_type     = Column(SmallInteger, nullable=False)  # 1=语义分割, 2=特征提取
    model_path     = Column(String(255), nullable=False)
    is_default     = Column(SmallInteger, nullable=False, default=0)  # 0=否, 1=是
    create_user_id = Column(BigInteger, ForeignKey("user.user_id"), nullable=False)
    create_time    = Column(DateTime, nullable=False, default=func.now())
    model_desc     = Column(String(500), nullable=True)
    system_id      = Column(BigInteger, nullable=True)
```

---

## 3. 模块一：用户权限管理

### 3.1 角色常量

角色名称与 `role.role_name` 字段值严格对应，**不得使用英文字符串做角色判断**：

```python
# app/core/permissions.py
class RoleName:
    ADMIN       = "管理员"
    RADIOLOGIST = "影像科医生"
    ATTENDING   = "主治医生"
```

### 3.2 权限矩阵

| 接口操作                          | 管理员 | 影像科医生 | 主治医生 |
|-----------------------------------|:------:|:----------:|:--------:|
| 用户管理（CRUD）                  |  ✅    |     ❌     |    ❌    |
| 日志审计查询                      |  ✅    |     ❌     |    ❌    |
| 模型版本管理（上传/切换默认）     |  ✅    |     ❌     |    ❌    |
| 上传 X 光片                       |  ✅    |     ✅     |    ❌    |
| 查看分割结果与面积指标            |  ✅    |     ✅     |    ❌    |
| 生成 / 修订诊断报告               |  ✅    |     ✅     |    ❌    |
| 审核报告（通过/驳回）             |  ✅    |     ✅     |    ❌    |
| 只读查看诊断报告                  |  ✅    |     ✅     |    ✅    |
| 导出 PDF 报告                     |  ✅    |     ✅     |    ✅    |

### 3.3 鉴权实现规范

- 使用 `python-jose[cryptography]`，算法 HS256。
- Token payload 包含：`sub`（user_id 字符串）、`role_name`（从 `role.role_name` 查询）、`exp`。
- `get_current_user` 依赖：解析 Token → 查 `user` 表确认用户存在 → 联查 `role` 表取 `role_name` → 注入请求上下文。
- `require_roles(*role_names)` 依赖工厂，传入 `RoleName` 常量：

```python
@router.post("/xray/upload")
async def upload_xray(
    ...,
    current_user = Depends(require_roles(RoleName.RADIOLOGIST, RoleName.ADMIN))
):
    ...
```

- 鉴权失败统一返回 HTTP 401（Token 无效/过期）或 403（权限不足）。
- 每次接口调用，通过 `log_service.write` 异步写入 `operation_log` 表（含成功/失败状态）。

---

## 4. 模块二：影像上传与分割

### 4.1 接口规范

```
POST  /xray/upload               上传X光片，写入 xray_info，触发分割
GET   /xray/{xray_id}            查询分割状态（含 segment_result 数据）
GET   /xray/{xray_id}/mask       返回掩码叠加图文件（FileResponse）
GET   /xray/{xray_id}/views      返回三张局部视图路径（JSON）
GET   /xray/                     分页列表（按 patient_id / upload_time 筛选）
```

### 4.2 分割处理流水线

以下步骤必须实现为独立函数，**禁止合并**：

```
POST /xray/upload 接收文件及患者信息表单
        │
        ▼
[1] file_storage.save_upload(file) → xray_original_path
        │   路径规则：storage/uploads/{patient_id}/{timestamp}.{ext}
        │
        ▼
[2] xray_service.create_record(form, path, uploader_id) → xray_id
        │   写入 xray_info，segment_status=0
        │
        ▼
[3] 接口立即返回 {"xray_id": ..., "segment_status": 0}
        │   使用 asyncio.create_task 异步执行后续步骤 [4]–[10]
        │
        ▼
[4] xray_service.update_status(xray_id, status=1)   # 分割中
        │
        ▼
[5] segmentation_service.preprocess(xray_original_path) → tensor
        │   - 灰度化 → CLAHE 对比度增强 → Resize(512×512)
        │   - 归一化为 [0,1] float32 tensor
        │
        ▼
[6] segmentation_service.run_inference(tensor) → mask_tensor
        │   - 调用分割模型单例（app.state.seg_model，启动时预加载，见 §4.3）
        │   - 输出三通道掩码：心脏 / 左肺 / 右肺
        │
        ▼
[7] segmentation_service.post_process(mask_tensor, original_img, xray_id)
        │   → 保存 mask_path、left/right_lung_view_path、heart_view_path
        │   → 计算 heart_area、left_lung_area、right_lung_area（像素面积）
        │
        ▼
[8] generation_service.generate_findings(areas_dict) → english_text
        │   - 根据面积指标生成英文结构化诊断条目（详见 §4.4）
        │   - 纯计算逻辑，不调用任何外部 API
        │
        ▼
[9] 写入 segment_result 表
        │   model_version 从当前 is_default=1 的模型管理记录中获取
        │
        ▼
[10] translation_service.translate(english_text) → (chinese_text, status)
        │
        ▼
[11] 写入 translate_record 表
        │
        ▼
[12] xray_service.update_status(xray_id, status=2)   # 成功
        │   任意步骤 [5]–[11] 抛出异常时，捕获后执行 update_status(xray_id, status=3)
```

### 4.3 分割模型加载规范

- 在 `main.py` 的 `lifespan` 事件中预加载，存为 `app.state.seg_model`。
- 加载优先级：① 查询 `model_manage` 表中 `is_default=1` 且 `model_type=1` 的记录取 `model_path`；② 回退读取 `config.FALLBACK_MODEL_PATH`。
- 若两者均不可用，启动时抛出 `RuntimeError`，**不能静默失败**。
- 切换默认模型时热重载（见 §7.2），无需重启服务。

### 4.4 诊断条目生成服务（generation_service）

`generation_service.generate_findings` 根据分割面积指标生成英文结构化诊断文本：

```python
# app/services/generation_service.py

def generate_findings(areas: dict) -> str:
    """
    根据分割面积指标生成英文结构化诊断描述条目。

    Args:
        areas: {
            "heart_area": float,
            "left_lung_area": float,
            "right_lung_area": float,
            "image_total_area": float   # 原图总像素，用于比例计算
        }
    Returns:
        多行英文诊断条目字符串，每条以 "- " 开头。

    实现规则：
    - 计算 CTR = heart_area / (left_lung_area + right_lung_area)
    - CTR > 0.50 → "Cardiothoracic ratio is {ctr:.2f}, suggesting possible cardiomegaly."
    - CTR <= 0.50 → "Cardiothoracic ratio is {ctr:.2f}, within normal limits."
    - 双肺面积差 > 15% → "Asymmetric lung volumes noted (left: {l:.2f}px, right: {r:.2f}px)."
    - 双肺面积差 <= 15% → "Bilateral lung volumes appear symmetric."
    - 所有数值保留两位小数
    - 此函数为纯计算逻辑，不调用任何外部 API 或数据库
    """
```

---

## 5. 模块三：报告生成与管理

### 5.1 接口规范

```
POST  /reports/generate/{xray_id}      基于已完成的分割结果生成报告草稿
GET   /reports/{report_id}             查看报告
PATCH /reports/{report_id}/audit       审核（通过/驳回），radiologist/admin
PATCH /reports/{report_id}/revise      修订报告内容，radiologist/admin
GET   /reports/{report_id}/export      导出 PDF（FileResponse）
GET   /reports/                        分页列表（按 xray_id / audit_status 筛选）
```

### 5.2 报告生成逻辑

1. 校验 `xray_info.segment_status == 2`，否则返回 400（`SEGMENT_NOT_READY`）。
2. 查询对应 `translate_record`（`translate_status=1`），取 `chinese_translate`；若无成功记录则降级使用 `english_original`。
3. 查询 `segment_result`，取面积数据和局部视图路径。
4. 组装 `report_content`（Text 字段），格式如下：

```
【患者信息】姓名：{patient_name}，性别：{gender_label}，年龄：{patient_age}岁，病历号：{patient_id}
【检查日期】{upload_time}
【影像所见】
{chinese_translate}
【定量指标】
  - 心脏区域面积：{heart_area:.2f} 像素
  - 左肺区域面积：{left_lung_area:.2f} 像素
  - 右肺区域面积：{right_lung_area:.2f} 像素
  - 心胸比（CTR）：{ctr:.2f}
【诊断意见】
（待影像科医生审核修订）
【分割模型版本】{model_version}
```

5. 写入 `report_info` 表：`audit_status=0`，`report_pdf_path=NULL`，`audit_user_id=NULL`。

### 5.3 审核与修订

- **审核**（`PATCH /reports/{report_id}/audit`）：
  - 请求体：`{"audit_status": 1}` 或 `{"audit_status": 2, "revise_content": "..."}`
  - 写入 `audit_user_id`（当前用户）、`audit_time`（当前时间）

- **修订**（`PATCH /reports/{report_id}/revise`）：
  - 请求体：`{"revise_content": "...", "report_content": "（可选）"}`
  - 若同时传 `report_content`，则更新报告正文；否则仅追加修订批注

### 5.4 PDF 导出要求

- 使用 **ReportLab**，字体路径从 `config.FONT_PATH` 读取（`NotoSansSC` 或 `SimSun`）。
- PDF 内容布局（从上到下）：
  1. 页眉：`config.HOSPITAL_NAME` + 报告标题
  2. 患者基本信息横排表格
  3. 三张局部视图缩略图（左肺 / 右肺 / 心脏）并排
  4. 掩码叠加图（居中，较大尺寸）
  5. 报告正文及修订内容（若 `revise_content` 非空则附加展示）
  6. 页脚：生成时间 + 模型版本 + 审核医生姓名（若已审核）
- 导出后保存至 `storage/reports/{report_id}.pdf`，并回填 `report_info.report_pdf_path`。
- 接口返回 `FileResponse`，`Content-Disposition: attachment; filename="report_{report_id}.pdf"`。

---

## 6. 模块四：翻译引擎

### 6.1 集成实现

```python
# app/services/translation_service.py
from openai import OpenAI
from app.config import settings

_client = OpenAI(
    api_key=settings.DOUBAO_API_KEY,
    base_url=settings.DOUBAO_BASE_URL,
)

async def translate(english_text: str) -> tuple[str, int]:
    """
    将英文诊断条目翻译为规范中文医学术语。
    Returns: (chinese_text, status)  status: 1=成功, 0=失败（降级返回原文）
    """
```

### 6.2 System Prompt（禁止修改）

```
你是一名专业医学翻译助手，专门将英文放射影像诊断描述翻译为规范的中文医学术语。
要求：
1. 严格使用中文医学标准术语，不使用口语化表达。
2. 保留所有数值、单位及标点符号的准确性。
3. 禁止添加任何原文未包含的诊断结论或主观推断。
4. 仅返回翻译结果，不附加解释或说明。
```

### 6.3 降级策略

- API 调用失败或超时：记录 `ERROR` 级别日志（含 segment_id）→ `chinese_translate` 回填原英文 → `translate_status=0`。
- **不抛出异常，不中断分割流水线。**
- 返回文本空值校验：若翻译结果为空字符串，同样降级处理。

---

## 7. 模块五：管理员功能

### 7.1 日志审计

```
GET /admin/logs?user_id=&operation_type=&start_time=&end_time=&page=&size=
```

- 查询 `operation_log` 表，支持多条件组合过滤，返回分页结果。
- 仅 `管理员` 角色可访问。

### 7.2 模型版本管理

```
GET    /admin/models                          列出所有模型版本
POST   /admin/models                          新增模型记录（写入 model_manage）
PATCH  /admin/models/{model_id}/default       设为默认模型
DELETE /admin/models/{model_id}               删除模型记录（不删除磁盘文件）
```

- 设置新默认模型：将原 `is_default=1` 的记录更新为 `0`，再将目标记录更新为 `1`，两步在同一事务中执行。
- 切换默认模型后，**热重载** `app.state.seg_model`，加载失败时保持原模型不变并返回 500。

---

## 8. 通用开发规范

### 8.1 代码风格

- 全部使用 Python **类型注解**（Type Hints）。
- 异步接口统一 `async def`；PyTorch 推理用 `asyncio.run_in_executor` 包装线程池。
- Pydantic v2 语法（`model_config = ConfigDict(...)`）。
- 每个 service 函数必须有 docstring。

### 8.2 统一错误响应格式

```json
{
  "error_code": "SEGMENT_NOT_READY",
  "message": "影像分割尚未完成，无法生成报告",
  "detail": null
}
```

- 所有业务异常继承 `AppException`，在 `main.py` 全局 handler 中转换为上述格式。
- **禁止**在 router 层直接 `raise HTTPException`。

### 8.3 操作日志自动写入

所有数据变更类接口在 service 层完成后，**必须异步调用** `log_service.write`：

```python
await log_service.write(
    db=db,
    user_id=current_user.user_id,
    user_name=current_user.real_name,
    operation_type="X光片上传",
    operation_content=f"医生 {current_user.real_name} 上传患者 {patient_name}（{patient_id}）的X光片",
    ip_address=request.client.host,
    operation_status=1,   # 1=成功, 0=失败
)
```

### 8.4 配置管理

```python
# app/config.py
class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    JWT_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    FALLBACK_MODEL_PATH: str = "./ml_models/unet_dacg.pth"
    STORAGE_ROOT: str = "./storage"
    DOUBAO_API_KEY: str
    DOUBAO_BASE_URL: str
    HOSPITAL_NAME: str = "医院名称"
    FONT_PATH: str = "./fonts/NotoSansSC-Regular.ttf"

    model_config = ConfigDict(env_file=".env")
```

### 8.5 数据库迁移

- 使用 **Alembic** 管理，**禁止**生产代码中使用 `Base.metadata.create_all()`。

---

## 9. 测试要求

### 9.1 覆盖目标

| 模块              | 最低覆盖率 |
|-------------------|:----------:|
| 鉴权与角色权限    | 90%        |
| 上传与分割流水线  | 80%        |
| 报告生成与审核    | 80%        |
| 诊断条目生成      | 85%        |
| 翻译服务          | 70%        |
| 管理员接口        | 70%        |

### 9.2 测试规范

- 使用 `pytest` + `httpx.AsyncClient`，测试数据库使用 SQLite 内存模式。
- PyTorch 推理在单元测试中 **mock**，不加载真实权重。
- 豆包翻译 API 调用在测试中 **mock**，不消耗真实 token。
- `generation_service.generate_findings` 必须覆盖边界值：CTR=0.5 临界、肺面积差恰好 15%、面积为 0 等异常输入。

---

## 10. 禁止事项（Agent 必须遵守）

- ❌ **禁止**修改数据库表字段名或类型，ORM 必须与第 2 节定义严格一致。
- ❌ **禁止**将角色判断硬编码为英文字符串，必须使用 `RoleName` 常量类。
- ❌ **禁止**在 router 层编写业务逻辑，所有逻辑下沉到 service 层。
- ❌ **禁止**硬编码任何密钥、路径或 URL，一律从 `config.py` 读取。
- ❌ **禁止**在响应体中暴露 `pwd` 字段。
- ❌ **禁止**PyTorch 推理同步阻塞异步路由，须用线程池包装。
- ❌ **禁止**将影像文件内容存入数据库，统一使用文件系统路径字段。
- ❌ **禁止**裸捕获 `Exception` 而不记录日志。
- ❌ **禁止**跳过操作日志写入，所有数据变更操作必须有 `operation_log` 记录。
- ❌ **禁止**在任何日志输出或控制台打印中提及模型就绪状态的内部实现差异。

---

## 11. 启动与验证检查清单

```bash
# 1. 依赖安装
pip install -r requirements.txt

# 2. 数据库迁移
alembic upgrade head

# 3. 启动服务
uvicorn app.main:app --reload

# 4. 健康检查
curl http://localhost:8000/health
# 预期响应：{"status": "ok", "model_loaded": true, "model_version": "v1.x.x"}

# 5. 单元测试
pytest tests/ -v --cov=app
```

---

*文档版本：v2.0 | 数据库适配版 | 最后更新：2026-03-17*
