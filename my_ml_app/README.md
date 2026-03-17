# 机器学习模型推理应用

一个基于FastAPI和现代Web技术的双模型机器学习推理应用程序，支持图像上传和实时预测。

## 项目结构

```
my_ml_app/
├── backend/
│   ├── main.py              # FastAPI主应用程序
│   └── model_pipeline.py    # 机器学习流水线模块
├── frontend/
│   ├── index.html           # 前端HTML页面
│   ├── style.css            # 样式表
│   └── script.js            # 交互脚本
├── models/                  # 模型文件目录（空）
├── requirements.txt         # Python依赖
├── Dockerfile              # Docker容器配置
└── README.md               # 项目说明文档
```

## 功能特性

- 🚀 FastAPI后端，提供高性能API服务
- 🎨 现代化前端界面，支持响应式设计
- 📤 文件上传功能，支持拖拽上传
- 🔄 双模型推理流水线
- 🐳 Docker容器化部署
- 🔍 健康检查和错误处理
- 📱 移动端友好的用户界面

## 快速开始

### 方法一：本地运行

1. **克隆项目**
```bash
git clone <repository-url>
cd my_ml_app
```

2. **创建虚拟环境**
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate     # Windows
```

3. **安装依赖**
```bash
pip install -r requirements.txt
```

4. **启动后端 (FastAPI)**
```bash
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
- 默认地址: http://127.0.0.1:8000
- 健康检查: http://127.0.0.1:8000/health
- Swagger 文档: http://127.0.0.1:8000/docs

5. **启动前端界面**
   - 直接双击 `frontend/index.html` 在浏览器中打开即可。
   - 如需本地静态服务器（推荐，避免浏览器跨域限制）：
     ```bash
     # 在项目根目录下运行
     python -m http.server -d frontend 5500
     # 浏览器访问
     http://127.0.0.1:5500
     ```
   - 前端脚本默认请求 `http://127.0.0.1:8000/report`，并展示 Findings / Impressions。
   - 如果后端端口或主机发生变化，请同步修改 `frontend/script.js` 中的 `API_BASE_URL`。

### 方法二：Docker运行

1. **构建Docker镜像**
```bash
docker build -t ml-app .
```

2. **运行容器**
```bash
docker run -p 8000:8000 ml-app
```

3. **访问应用**
- API地址: http://localhost:8000
- API文档: http://localhost:8000/docs

## API接口

### 健康检查
```
GET /health
```
返回应用和模型加载状态。

### 预测接口
```
POST /predict
Content-Type: multipart/form-data
```
上传图片文件，返回预测结果。

**响应示例：**
```json
{
  "prediction": "Predicted Class: Cat"
}
```

## 使用说明

1. 打开前端界面 (`frontend/index.html`)
2. 点击"选择文件"或拖拽图片到页面上
3. 选择图片文件后，点击"开始预测"按钮
4. 前端会调用后端 `/report` 接口并返回 Findings / Impressions
5. 等待处理完成，查看预测结果
6. 支持的图片格式：JPG、PNG、GIF、BMP等

## 开发指南

### 模型集成

在 `backend/model_pipeline.py` 中：

1. **加载真实模型**
```python
def load_models():
    # 替换为实际的模型加载代码
    model1 = load_model('path/to/model1.h5')
    model2 = load_model('path/to/model2.h5')
    return model1, model2
```

2. **实现推理逻辑**
```python
def run_pipeline(input_data, model1, model2):
    # 实现实际的数据预处理和推理逻辑
    processed_data = preprocess(input_data)
    result1 = model1.predict(processed_data)
    result2 = model2.predict(processed_data)
    final_result = postprocess(result1, result2)
    return final_result
```

### 自定义前端

前端文件位于 `frontend/` 目录：
- `index.html`: HTML结构和内容
- `style.css`: 样式和布局
- `script.js`: 交互逻辑和API调用

## 环境变量

可以通过环境变量配置应用：

```bash
export API_HOST=0.0.0.0
export API_PORT=8000
export MODEL_PATH=/app/models
```

## 部署建议

### 生产环境部署

1. **使用Gunicorn**
```bash
pip install gunicorn
gunicorn backend.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

2. **Nginx反向代理**
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

3. **Docker Compose**
```yaml
version: '3.8'
services:
  ml-app:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./models:/app/models
    environment:
      - API_HOST=0.0.0.0
      - API_PORT=8000
```

## 故障排除

### 常见问题

1. **模型加载失败**
   - 检查模型文件路径
   - 确认模型格式正确

2. **CORS错误**
   - 确认API地址正确
   - 检查防火墙设置

3. **文件上传失败**
   - 检查文件大小限制
   - 确认文件格式支持

### 日志查看

```bash
# Docker容器日志
docker logs <container-id>

# 本地运行日志
# 日志会直接输出到终端
```

## 技术栈

- **后端**: FastAPI, Uvicorn, Python 3.9+
- **前端**: HTML5, CSS3, JavaScript (ES6+)
- **机器学习**: TensorFlow/PyTorch, Scikit-learn
- **容器化**: Docker, Docker Compose
- **部署**: Gunicorn, Nginx

## 许可证

MIT License

## 贡献指南

欢迎提交Issue和Pull Request来改进这个项目！

## 联系方式

如有问题，请通过以下方式联系：
- 提交GitHub Issue
- 发送邮件至: [your-email@example.com]
