from datetime import datetime
from pathlib import Path
from fastapi import UploadFile
from app.config import settings
import pydicom
import numpy as np
from PIL import Image


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def save_upload(file: UploadFile, patient_id: str) -> str:
    """Save uploaded file to storage/uploads/{patient_id}/{timestamp}.{ext}"""
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    ext = Path(file.filename or "upload").suffix.lstrip(".") or "bin"
    root = Path(settings.STORAGE_ROOT) / "uploads" / patient_id
    _ensure_dir(root)
    target = root / f"{ts}.{ext}"
    with target.open("wb") as f:
        f.write(file.file.read())
    return str(target)


def build_mask_path(xray_id: int) -> str:
    root = Path(settings.STORAGE_ROOT) / "masks"
    _ensure_dir(root)
    return str(root / f"xray_{xray_id}_mask.png")


def build_view_path(xray_id: int, view_name: str) -> str:
    root = Path(settings.STORAGE_ROOT) / "views" / view_name
    _ensure_dir(root)
    return str(root / f"xray_{xray_id}_{view_name}.png")


def build_visualization_path(xray_id: int) -> str:
    root = Path(settings.STORAGE_ROOT) / "visualizations"
    _ensure_dir(root)
    return str(root / f"xray_{xray_id}_visualization.png")


def build_report_path(report_id: int) -> str:
    root = Path(settings.STORAGE_ROOT) / "reports"
    _ensure_dir(root)
    return str(root / f"report_{report_id}.pdf")


def convert_dicom_to_png(dicom_path: str, output_path: str) -> str:
    """Convert DICOM file to PNG format."""
    try:
        # Read DICOM file
        dicom_data = pydicom.dcmread(dicom_path)
        
        # Get pixel array
        pixel_array = dicom_data.pixel_array
        
        # Normalize pixel values to 0-255 range
        pixel_array = pixel_array.astype(np.float32)
        pixel_array = (pixel_array - pixel_array.min()) / (pixel_array.max() - pixel_array.min() + 1e-8) * 255
        pixel_array = pixel_array.astype(np.uint8)
        
        # Convert to PIL Image and save as PNG
        image = Image.fromarray(pixel_array)
        image.save(output_path, 'PNG')
        
        return output_path
    except Exception as e:
        raise RuntimeError(f"DICOM conversion failed: {str(e)}")
