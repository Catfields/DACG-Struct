from fastapi import APIRouter, Depends, Request, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.dependencies import get_db
from app.core.permissions import require_roles, RoleName
from app.schemas.report import ReportOut, AuditRequest, ReviseRequest
from app.services import report_service, log_service

router = APIRouter(prefix="/reports", tags=["reports"])


def _format_datetime_value(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _serialize_report_out(report):
    return {
        "report_id": report.report_id,
        "xray_id": report.xray_id,
        "segment_id": report.segment_id,
        "report_content": report.report_content,
        "report_pdf_path": report.report_pdf_path,
        "generate_time": _format_datetime_value(report.generate_time),
        "audit_status": report.audit_status,
        "audit_user_id": report.audit_user_id,
        "audit_time": _format_datetime_value(report.audit_time),
        "revise_content": report.revise_content,
        "system_id": report.system_id,
    }


@router.post("/generate/{xray_id}", response_model=ReportOut)
async def generate_report(xray_id: int, request: Request, db: Session = Depends(get_db), current_user=Depends(require_roles(RoleName.RADIOLOGIST, RoleName.ADMIN))):
    report = report_service.generate_report(db, xray_id)
    await log_service.write(
        db=db,
        user_id=current_user.user_id,
        user_name=current_user.real_name,
        operation_type="报告生成",
        operation_content=f"生成报告 {report.report_id}",
        ip_address=request.client.host if request.client else None,
        operation_status=1,
    )
    return _serialize_report_out(report)


@router.get("/{report_id}", response_model=ReportOut)
async def get_report(report_id: int, db: Session = Depends(get_db), current_user=Depends(require_roles(RoleName.RADIOLOGIST, RoleName.ADMIN, RoleName.ATTENDING))):
    report = report_service.get_report(db, report_id)
    return _serialize_report_out(report)


@router.patch("/{report_id}/audit", response_model=ReportOut)
async def audit_report(report_id: int, payload: AuditRequest, request: Request, db: Session = Depends(get_db), current_user=Depends(require_roles(RoleName.RADIOLOGIST, RoleName.ADMIN))):
    report = report_service.audit_report(db, report_id, payload.audit_status, current_user.user_id, payload.revise_content)
    await log_service.write(
        db=db,
        user_id=current_user.user_id,
        user_name=current_user.real_name,
        operation_type="报告审核",
        operation_content=f"审核报告 {report.report_id}，状态 {payload.audit_status}",
        ip_address=request.client.host if request.client else None,
        operation_status=1,
    )
    return _serialize_report_out(report)


@router.patch("/{report_id}/revise", response_model=ReportOut)
async def revise_report(report_id: int, payload: ReviseRequest, request: Request, db: Session = Depends(get_db), current_user=Depends(require_roles(RoleName.RADIOLOGIST, RoleName.ADMIN))):
    report = report_service.revise_report(db, report_id, payload.revise_content, payload.report_content)
    await log_service.write(
        db=db,
        user_id=current_user.user_id,
        user_name=current_user.real_name,
        operation_type="报告修订",
        operation_content=f"修订报告 {report.report_id}",
        ip_address=request.client.host if request.client else None,
        operation_status=1,
    )
    return _serialize_report_out(report)


@router.get("/{report_id}/export")
async def export_report(report_id: int, db: Session = Depends(get_db), current_user=Depends(require_roles(RoleName.RADIOLOGIST, RoleName.ADMIN, RoleName.ATTENDING))):
    path = report_service.export_pdf(db, report_id)
    return FileResponse(path, media_type="application/pdf", filename=f"report_{report_id}.pdf")


@router.get("/", response_model=list[ReportOut])
async def list_reports(
    xray_id: int | None = None,
    audit_status: int | None = None,
    page: int = 1,
    size: int = 20,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(RoleName.RADIOLOGIST, RoleName.ADMIN, RoleName.ATTENDING)),
):
    reports = report_service.list_reports(db, xray_id, audit_status, page, size)
    return [_serialize_report_out(report) for report in reports]


@router.post("/manual-save", response_model=ReportOut)
async def manual_save_report(
    request: Request,
    patient_name: str = Form(...),
    patient_gender: int | None = Form(None),
    patient_age: int | None = Form(None),
    exam_date: str | None = Form(None),
    xray_format: str = Form("PNG"),
    report_content: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(RoleName.RADIOLOGIST, RoleName.ADMIN)),
):
    report = report_service.manual_save_report(
        db,
        patient_name=patient_name,
        patient_gender=patient_gender,
        patient_age=patient_age,
        exam_date=exam_date,
        xray_format=xray_format,
        report_content=report_content,
        upload_file=file,
        upload_user_id=current_user.user_id,
    )
    await log_service.write(
        db=db,
        user_id=current_user.user_id,
        user_name=current_user.real_name,
        operation_type="报告保存",
        operation_content=f"手工保存报告 {report.report_id}",
        ip_address=request.client.host if request.client else None,
        operation_status=1,
    )
    return _serialize_report_out(report)
