# 项目运行说明（README）

## 一、数据库配置

### 1. 数据库初始化
已在服务器上完成如下配置：
- 数据库名称：`mydb`
- 已创建 8 张数据表

### 2. 登录数据库
```bash
sudo mysql mydb
```

### 3. 创建用户
```sql
CREATE USER 'admin'@'localhost' IDENTIFIED BY '88888888';
```

### 4. 使用用户登录
```bash
mysql -u admin -p mydb
```

---

## 二、数据库启停

### 1. 启动 MySQL
```bash
sudo systemctl start mysql
```

### 2. 停止 MySQL
```bash
sudo systemctl stop mysql
```

---

## 三、后端服务运行

### 1. 进入后端目录
```bash
cd backend
```

### 2. 安装依赖
```bash
pip install -r requirements.txt
```

### 3. 配置环境变量
```bash
cp .env.example .env
```

> 请在 `.env` 文件中填写：
- 数据库连接信息
- 豆包（AI 服务）相关配置

### 4. 启动后端服务
```bash
uvicorn app.main:app --reload --port 9000
```

---

## 四、前端测试账号

| 角色           | 用户名 | 密码   |
|----------------|--------|--------|
| 影像科医生     | rad1   | 123456 |
| 主治医生       | doc1   | 123456 |
| 管理员         | admin  | 123456 |

---

## 五、备注

- 日期记录：2026-03-18
- 本文档用于快速部署与启动服务
- 如数据库或端口发生变更，请同步修改 `.env` 配置文件

