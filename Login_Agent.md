# Login_Agent.md

## 1. 核心目标
指导 Agent 在 `backend/app/` 目录下完成基于 **FastAPI + SQLAlchemy** 的真实登录与鉴权逻辑，打通 `user` 与 `role` 表的联查，实现角色权限控制。

## 2. 数据库与 ORM 对接
必须严格遵循 `AGENT.md` 第 2 节的实体定义：
* **User 模型**: 匹配 `login_name`, `login_flag` (1=工号, 2=手机号), `pwd` (bcrypt存储), `role_id`。
* **Role 模型**: 联查 `role_name` 以获取用户角色（管理员/影像科医生/主治医生）。
* **注意**: 严禁修改字段名，严禁在响应中暴露 `pwd`。

## 3. 认证逻辑实现 (Authentication)
### 3.1 登录流程 (`auth_service.py`)
1.  **查询**: 根据 `login_name` 查库。
2.  **校验**: 使用 `passlib[bcrypt]` 验证输入密码与数据库 `pwd` 哈希。
3.  **签发**: 构造 JWT Payload。
    * `sub`: `str(user_id)`
    * `role_name`: `role.role_name` (来自联查)
    * `exp`: 从 `settings.JWT_EXPIRE_MINUTES` 读取。

### 3.2 权限控制 (`dependencies.py` & `permissions.py`)
* **禁止硬编码**: 权限判断必须使用 `RoleName` 常量类。
* **依赖工厂**: 实现 `require_roles(*role_names)` 函数，通过解析 Token 中的 `role_name` 字段拦截非法请求。

## 4. 接口规范
* **POST `/auth/login`**: 接收登录凭证，返回 Token 及非敏感用户信息。
* **日志写入**: 登录成功或失败后，必须异步调用 `log_service.write` 记录至 `operation_log` 表。
* **异常处理**: 认证失败统一抛出 `AppException`，由全局 handler 转换为标准 JSON 响应。

## 5. 开发约束 (Agent 必读)
* **异步要求**: 数据库操作使用 `AsyncSession`，密码计算若耗时较长建议在线程池运行。
* **配置读取**: JWT 密钥、算法等必须从 `app/config.py` 的 `Settings` 对象读取。
* **安全性**: 严禁在日志中打印明文密码或哈希值。

---
END