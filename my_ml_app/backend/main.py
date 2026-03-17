"""
FastAPI主应用程序
提供机器学习模型的Web API接口
"""

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os
import sys
import tempfile
import base64
from io import BytesIO
from pathlib import Path
from typing import Dict, Any

from PIL import Image
import numpy as np

from model_pipeline import load_models, run_pipeline

try:
    from integrated_report_generator import IntegratedMedicalReportGenerator
except ModuleNotFoundError:
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.append(str(PROJECT_ROOT))
    # 从bin目录导入
    sys.path.append(str(PROJECT_ROOT / "bin"))
    from integrated_report_generator import IntegratedMedicalReportGenerator

try:
    from segmentation_modules.evaluator import Evaluator, overlay_mask_with_prob
    from segmentation_modules.config import CLASS_NAMES, CLASS_COLOR_MAP
except ModuleNotFoundError:
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.append(str(PROJECT_ROOT))
    from segmentation_modules.evaluator import Evaluator, overlay_mask_with_prob
    from segmentation_modules.config import CLASS_NAMES, CLASS_COLOR_MAP

# 分割模型路径（支持环境变量覆盖）
SEG_MODEL_DIR = os.getenv(
    "SEG_MODEL_DIR",
    "/home/y530/handsome/DACG/my_ml_app/models",
)
SEG_MODEL_FILENAME = os.getenv("SEG_MODEL_FILENAME", "upp_model.pth")

# 创建FastAPI应用实例
app = FastAPI(
    title="ML Model API",
    description="机器学习模型推理API",
    version="1.0.0"
)

# 配置CORS中间件，允许所有来源
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局变量存储加载的模型
model1 = None
model2 = None

# 集成医疗图像报告生成器（与 CLI 复用）
report_generator = None

# 分割评估器（器官可视化）
seg_evaluator = None

@app.on_event("startup")
async def startup_event():
    """
    应用启动时加载模型
    """
    global model1, model2, report_generator, seg_evaluator
    try:
        model1, model2 = load_models()
        # 从环境变量读取每段翻译模型，默认与测试策略一致
        f_model = os.getenv("TRANSLATOR_MODEL_FINDINGS", "ep-20251018154549-2z528")
        i_model = os.getenv("TRANSLATOR_MODEL_IMPRESSIONS", "ep-20251018154549-2z528")
        report_generator = IntegratedMedicalReportGenerator(
            translator_model_findings=f_model,
            translator_model_impressions=i_model,
        )
        model_full_path = os.path.join(SEG_MODEL_DIR, SEG_MODEL_FILENAME)
        if not os.path.exists(model_full_path):
            raise RuntimeError(f"Segmentation model not found: {model_full_path}")
        seg_evaluator = Evaluator(model_full_path)
        print("应用启动成功，模型与报告生成器已加载")
    except Exception as e:
        print(f"模型或报告生成器加载失败: {e}")
        raise

@app.get("/")
async def root():
    """
    根路径端点，返回API信息
    """
    return {
        "message": "ML Model API",
        "version": "1.0.0",
        "status": "running"
    }

@app.get("/health")
async def health_check():
    """
    健康检查端点
    """
    return {
        "status": "healthy",
        "models_loaded": model1 is not None and model2 is not None
    }

@app.post("/predict")
async def predict(file: UploadFile = File(...)):
    """
    预测端点，接受文件上传并返回预测结果

    Args:
        file: 上传的文件

    Returns:
        dict: 包含预测结果的JSON响应
    """
    global model1, model2

    # 检查模型是否已加载
    if model1 is None or model2 is None:
        raise HTTPException(status_code=500, detail="模型未加载")

    # 检查文件类型
    if not file.filename:
        raise HTTPException(status_code=400, detail="未提供文件")

    try:
        # 创建临时文件保存上传的内容
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as temp_file:
            # 读取上传文件的内容
            content = await file.read()
            temp_file.write(content)
            temp_file_path = temp_file.name

        # 运行机器学习流水线
        prediction = run_pipeline(temp_file_path, model1, model2)

        # 清理临时文件
        os.unlink(temp_file_path)

        # 返回预测结果
        return JSONResponse(
            content={"prediction": prediction},
            status_code=200
        )

    except Exception as e:
        # 确保清理临时文件
        if 'temp_file_path' in locals():
            try:
                os.unlink(temp_file_path)
            except:
                pass

        raise HTTPException(
            status_code=500,
            detail=f"预测过程中发生错误: {str(e)}"
        )


@app.post("/report")
async def generate_report(
    file: UploadFile = File(...),
    findings_only: bool = False,
    impressions_only: bool = False,
):
    """
    生成医疗图像报告，与 CLI 工具保持一致的输出结构

    Args:
        file: 上传的图像文件
        findings_only: 只返回 findings 字段
        impressions_only: 只返回 impressions 字段

    Returns:
        dict: 报告结果
    """
    global report_generator

    if report_generator is None:
        raise HTTPException(status_code=500, detail="报告生成器未初始化")

    if findings_only and impressions_only:
        raise HTTPException(
            status_code=400, detail="不能同时选择 findings_only 和 impressions_only"
        )

    if not file.filename:
        raise HTTPException(status_code=400, detail="未提供文件")

    try:
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=os.path.splitext(file.filename)[1]
        ) as temp_file:
            content = await file.read()
            temp_file.write(content)
            temp_file_path = temp_file.name

        report = report_generator.generate_report(temp_file_path)

        if findings_only:
            report = {
                "findings": report.get("findings", ""),
                "image_path": report.get("image_path", ""),
            }
        elif impressions_only:
            report = {
                "impressions": report.get("impressions", ""),
                "image_path": report.get("image_path", ""),
            }

        os.unlink(temp_file_path)
        return JSONResponse(content=report, status_code=200)

    except Exception as e:
        if "temp_file_path" in locals():
            try:
                os.unlink(temp_file_path)
            except OSError:
                pass
        raise HTTPException(status_code=500, detail=f"生成报告出错: {str(e)}")


@app.post("/segment_overlay")
async def segment_overlay(
    file: UploadFile = File(...),
    alpha_min: float = 0.2,
    alpha_max: float = 0.7,
):
    """
    返回器官区域叠加可视化的 base64 data URL
    """
    global seg_evaluator

    if seg_evaluator is None:
        raise HTTPException(status_code=500, detail="分割评估器未初始化")

    if not file.filename:
        raise HTTPException(status_code=400, detail="未提供文件")

    try:
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=os.path.splitext(file.filename)[1]
        ) as temp_file:
            content = await file.read()
            temp_file.write(content)
            temp_file_path = temp_file.name

        # 分割预测
        pred_mask, prob_map = seg_evaluator.predict_single_image(temp_file_path)
        original_image = Image.open(temp_file_path).convert("RGB")

        overlay = overlay_mask_with_prob(
            np.array(original_image),
            pred_mask,
            prob_map,
            alpha_min=float(alpha_min),
            alpha_max=float(alpha_max),
        )

        buffer = BytesIO()
        Image.fromarray(overlay).save(buffer, format="PNG")
        data_url = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")

        # 掩膜按类别ID编码为灰度图，用于前端像素取样
        mask_buffer = BytesIO()
        Image.fromarray(pred_mask.astype(np.uint8), mode="L").save(mask_buffer, format="PNG")
        mask_data_url = "data:image/png;base64," + base64.b64encode(mask_buffer.getvalue()).decode("ascii")

        os.unlink(temp_file_path)

        return JSONResponse(
            content={
                "overlay_data_url": data_url,
                "mask_data_url": mask_data_url,
                "class_names": CLASS_NAMES,
                "class_colors": CLASS_COLOR_MAP,
                "size": {"width": original_image.width, "height": original_image.height},
            },
            status_code=200,
        )

    except Exception as e:
        if "temp_file_path" in locals():
            try:
                os.unlink(temp_file_path)
            except OSError:
                pass
        raise HTTPException(status_code=500, detail=f"生成器官可视化出错: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
