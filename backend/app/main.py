from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.utils.logger import setup_logger
from app.core.exceptions import AppException
from app.database import SessionLocal
from app.services import model_service, segmentation_service
from app.routers import auth, users, xray, reports, admin, translation
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logger()
    db = SessionLocal()
    try:
        model_record = model_service.get_default_model(db)
        if model_record:
            model_path = model_record.model_path
            model_version = model_record.model_version
        else:
            model_path = settings.FALLBACK_MODEL_PATH
            model_version = "fallback"

        app.state.seg_model = segmentation_service.load_model(model_path)
        app.state.model_version = model_version
        yield
    finally:
        db.close()


app = FastAPI(lifespan=lifespan)

# Allow frontend dev server to call APIs (CORS preflight)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppException)
async def app_exception_handler(_, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error_code": exc.error_code, "message": exc.message, "detail": exc.detail},
    )


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "model_loaded": app.state.seg_model is not None,
        "model_version": app.state.model_version,
    }


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(xray.router)
app.include_router(reports.router)
app.include_router(admin.router)
app.include_router(translation.router)
