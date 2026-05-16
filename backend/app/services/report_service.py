from datetime import datetime
from uuid import uuid4
from pathlib import Path
from sqlalchemy.orm import Session
from sqlalchemy import select
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader
from app.config import settings
from app.models.translate_record import TranslateRecord
from app.models.report_info import ReportInfo
from app.models.report_history import ReportHistory
from app.models.user import User
from app.models.xray_info import XrayInfo
from app.models.segment_result import SegmentResult
from app.core.exceptions import AppException
from app.utils.file_storage import build_report_path
from app.utils.file_storage import save_upload


def _gender_label(gender: int | None) -> str:
    if gender == 1:
        return "男"
    if gender == 2:
        return "女"
    return "未知"


REPORT_ACTION_BASELINE = "baseline"
REPORT_ACTION_BACKEND_GENERATE = "backend_generate"
REPORT_ACTION_FRONTEND_GENERATE = "frontend_generate"
REPORT_ACTION_MANUAL_SAVE = "manual_save"
REPORT_ACTION_MANUAL_REVISION = "manual_revision"
REPORT_ACTION_AUDIT = "audit"
REPORT_ACTION_AUDIT_REVISION = "audit_revision"
REPORT_ACTION_PDF_EXPORT = "pdf_export"

_MANUAL_SAVE_ACTIONS = {
    REPORT_ACTION_FRONTEND_GENERATE,
    REPORT_ACTION_MANUAL_SAVE,
    REPORT_ACTION_MANUAL_REVISION,
}


def _normalize_manual_save_action(action_type: str | None) -> str:
    action = str(action_type or "").strip()
    if action in _MANUAL_SAVE_ACTIONS:
        return action
    return REPORT_ACTION_MANUAL_SAVE


def _manual_action_note(action_type: str, is_first_snapshot: bool) -> str:
    if action_type == REPORT_ACTION_FRONTEND_GENERATE:
        return "前端生成首个报告" if is_first_snapshot else "前端重复生成报告"
    if action_type == REPORT_ACTION_MANUAL_REVISION:
        return "前端人工修订首个报告" if is_first_snapshot else "前端人工修订报告"
    return "前端人工保存首个报告" if is_first_snapshot else "前端人工保存报告"


def _get_latest_report_history(db: Session, report_id: int) -> ReportHistory | None:
    return db.execute(
        select(ReportHistory)
        .where(ReportHistory.report_id == report_id)
        .order_by(ReportHistory.action_time.desc(), ReportHistory.history_id.desc())
    ).scalars().first()


def _create_report_history(
    db: Session,
    report: ReportInfo,
    *,
    action_type: str,
    action_user_id: int | None = None,
    parent_history_id: int | None = None,
    action_note: str | None = None,
) -> ReportHistory:
    db.flush()
    parent_id = parent_history_id
    if parent_id is None:
        latest = _get_latest_report_history(db, report.report_id)
        parent_id = latest.history_id if latest else None

    history = ReportHistory(
        report_id=report.report_id,
        xray_id=report.xray_id,
        segment_id=report.segment_id,
        parent_history_id=parent_id,
        action_type=action_type,
        action_user_id=action_user_id,
        action_note=action_note,
        report_content=report.report_content,
        revise_content=report.revise_content,
        report_pdf_path=report.report_pdf_path,
        generate_time=report.generate_time,
        audit_status=report.audit_status or 0,
        audit_user_id=report.audit_user_id,
        audit_time=report.audit_time,
        system_id=report.system_id,
    )
    db.add(history)
    db.flush()
    return history


def _ensure_report_history_baseline(db: Session, report: ReportInfo) -> ReportHistory:
    latest = _get_latest_report_history(db, report.report_id)
    if latest:
        return latest
    return _create_report_history(
        db,
        report,
        action_type=REPORT_ACTION_BASELINE,
        action_note="历史表启用前的当前报告快照",
    )


def generate_report(db: Session, xray_id: int, action_user_id: int | None = None) -> ReportInfo:
    """Generate report content and save to report_info."""
    xray = db.get(XrayInfo, xray_id)
    if not xray:
        raise AppException("XRAY_NOT_FOUND", "影像不存在", status_code=404)
    if xray.segment_status != 2:
        raise AppException("SEGMENT_NOT_READY", "影像分割尚未完成，无法生成报告", status_code=400)

    segment = db.execute(select(SegmentResult).where(SegmentResult.xray_id == xray_id)).scalar_one_or_none()
    if not segment:
        raise AppException("SEGMENT_NOT_FOUND", "分割结果不存在", status_code=404)

    trans_result = db.execute(
        select(TranslateRecord)
        .where(TranslateRecord.segment_id == segment.segment_id)
        .order_by(TranslateRecord.translate_time.desc())
    )
    trans = trans_result.scalars().first()

    if trans and trans.translate_status == 1:
        findings = trans.chinese_translate
    elif trans:
        findings = trans.english_original
    else:
        findings = ""

    previous_report = db.execute(
        select(ReportInfo)
        .where(ReportInfo.xray_id == xray_id)
        .order_by(ReportInfo.generate_time.desc(), ReportInfo.report_id.desc())
    ).scalars().first()
    parent_history_id = None
    if previous_report:
        parent_history_id = _ensure_report_history_baseline(db, previous_report).history_id

    lung_total = (segment.left_lung_area or 0) + (segment.right_lung_area or 0)
    ctr = (segment.heart_area or 0) / lung_total if lung_total > 0 else 0.0

    content = (
        f"【患者信息】姓名：{xray.patient_name}，性别：{_gender_label(xray.patient_gender)}，"
        f"年龄：{xray.patient_age}岁，病历号：{xray.patient_id}\n"
        f"【检查日期】{xray.upload_time}\n"
        f"【影像所见】\n{findings}\n"
        "【定量指标】\n"
        f"  - 心脏区域面积：{(segment.heart_area or 0):.2f} 像素\n"
        f"  - 左肺区域面积：{(segment.left_lung_area or 0):.2f} 像素\n"
        f"  - 右肺区域面积：{(segment.right_lung_area or 0):.2f} 像素\n"
        f"  - 心胸比（CTR）：{ctr:.2f}\n"
        "【诊断意见】\n（待影像科医生审核修订）\n"
        f"【分割模型版本】{segment.model_version}"
    )

    report = ReportInfo(
        xray_id=xray_id,
        segment_id=segment.segment_id,
        report_content=content,
        report_pdf_path=None,
        audit_status=0,
        audit_user_id=None,
        audit_time=None,
        revise_content=None,
    )
    db.add(report)
    db.flush()
    _create_report_history(
        db,
        report,
        action_type=REPORT_ACTION_BACKEND_GENERATE,
        action_user_id=action_user_id,
        parent_history_id=parent_history_id,
        action_note="后台结构化报告生成",
    )
    db.commit()
    db.refresh(report)
    return report


def audit_report(db: Session, report_id: int, audit_status: int, audit_user_id: int, revise_content: str | None) -> ReportInfo:
    """Audit report."""
    report = db.get(ReportInfo, report_id)
    if not report:
        raise AppException("REPORT_NOT_FOUND", "报告不存在", status_code=404)
    parent = _ensure_report_history_baseline(db, report)
    report.audit_status = audit_status
    report.audit_user_id = audit_user_id
    report.audit_time = datetime.now()
    if revise_content:
        report.revise_content = revise_content
    db.add(report)
    _create_report_history(
        db,
        report,
        action_type=REPORT_ACTION_AUDIT_REVISION if revise_content else REPORT_ACTION_AUDIT,
        action_user_id=audit_user_id,
        parent_history_id=parent.history_id,
        action_note="报告审核并修订" if revise_content else "报告审核",
    )
    db.commit()
    db.refresh(report)
    return report


def revise_report(
    db: Session,
    report_id: int,
    revise_content: str,
    report_content: str | None,
    action_user_id: int | None = None,
) -> ReportInfo:
    """Revise report content."""
    report = db.get(ReportInfo, report_id)
    if not report:
        raise AppException("REPORT_NOT_FOUND", "报告不存在", status_code=404)
    parent = _ensure_report_history_baseline(db, report)
    report.revise_content = revise_content
    if report_content is not None:
        report.report_content = report_content
    db.add(report)
    _create_report_history(
        db,
        report,
        action_type=REPORT_ACTION_MANUAL_REVISION,
        action_user_id=action_user_id,
        parent_history_id=parent.history_id,
        action_note="报告人工修订",
    )
    db.commit()
    db.refresh(report)
    return report


def get_report(db: Session, report_id: int) -> ReportInfo:
    """Get report by id."""
    report = db.get(ReportInfo, report_id)
    if not report:
        raise AppException("REPORT_NOT_FOUND", "报告不存在", status_code=404)
    return report


def list_reports(db: Session, xray_id: int | None, audit_status: int | None, page: int, size: int):
    """List reports with filters."""
    stmt = select(ReportInfo)
    if xray_id:
        stmt = stmt.where(ReportInfo.xray_id == xray_id)
    if audit_status is not None:
        stmt = stmt.where(ReportInfo.audit_status == audit_status)
    offset = (page - 1) * size
    return db.execute(stmt.order_by(ReportInfo.generate_time.desc()).offset(offset).limit(size)).scalars().all()


def list_report_history(db: Session, report_id: int):
    """List immutable report snapshots in chain order."""
    get_report(db, report_id)
    return db.execute(
        select(ReportHistory)
        .where(ReportHistory.report_id == report_id)
        .order_by(ReportHistory.action_time.asc(), ReportHistory.history_id.asc())
    ).scalars().all()


def export_pdf(db: Session, report_id: int) -> str:
    """Export report as PDF and return file path."""
    report = get_report(db, report_id)
    xray = db.get(XrayInfo, report.xray_id)
    segment = db.get(SegmentResult, report.segment_id)

    font_path = Path(settings.FONT_PATH)
    if font_path.exists():
        pdfmetrics.registerFont(TTFont("ReportFont", str(font_path)))
        font_name = "ReportFont"
    else:
        font_name = "Helvetica"

    pdf_path = build_report_path(report_id)
    c = canvas.Canvas(pdf_path, pagesize=A4)
    width, height = A4

    c.setFont(font_name, 16)
    c.drawString(20 * mm, height - 20 * mm, f"{settings.HOSPITAL_NAME} 影像诊断报告")

    c.setFont(font_name, 10)
    y = height - 30 * mm
    if xray:
        info = f"姓名：{xray.patient_name}  性别：{_gender_label(xray.patient_gender)}  年龄：{xray.patient_age}  病历号：{xray.patient_id}"
        c.drawString(20 * mm, y, info)
        y -= 10 * mm

    if segment:
        img_paths = [segment.left_lung_view_path, segment.right_lung_view_path, segment.heart_view_path]
        x = 20 * mm
        for p in img_paths:
            if p and Path(p).exists():
                c.drawImage(ImageReader(p), x, y - 40 * mm, width=50 * mm, height=40 * mm)
            x += 55 * mm
        y -= 50 * mm

        if segment.mask_path and Path(segment.mask_path).exists():
            c.drawImage(ImageReader(segment.mask_path), 20 * mm, y - 70 * mm, width=170 * mm, height=70 * mm)
            y -= 80 * mm

    c.setFont(font_name, 10)
    text_obj = c.beginText(20 * mm, y)
    for line in report.report_content.splitlines():
        text_obj.textLine(line)
    if report.revise_content:
        text_obj.textLine("\n【修订内容】")
        for line in report.revise_content.splitlines():
            text_obj.textLine(line)
    c.drawText(text_obj)

    footer = f"生成时间：{report.generate_time}  模型版本：{segment.model_version if segment else ''}"
    if report.audit_user_id:
        auditor = db.get(User, report.audit_user_id)
        auditor_name = auditor.real_name if auditor else str(report.audit_user_id)
        footer += f"  审核医生：{auditor_name}"
    c.drawString(20 * mm, 10 * mm, footer)

    c.showPage()
    c.save()

    parent = _ensure_report_history_baseline(db, report)
    report.report_pdf_path = pdf_path
    db.add(report)
    _create_report_history(
        db,
        report,
        action_type=REPORT_ACTION_PDF_EXPORT,
        parent_history_id=parent.history_id,
        action_note="导出报告 PDF",
    )
    db.commit()

    return pdf_path


def _build_manual_patient_id() -> str:
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    suffix = uuid4().hex[:6].upper()
    return f"MANUAL{ts}{suffix}"


def _parse_manual_upload_time(exam_date: str | None) -> datetime:
    if not exam_date:
        return datetime.now()
    try:
        return datetime.strptime(exam_date, "%Y-%m-%d")
    except ValueError as exc:
        raise AppException("INVALID_EXAM_DATE", "检查日期格式应为 YYYY-MM-DD", status_code=400) from exc


def _get_or_create_manual_segment(db: Session, xray: XrayInfo) -> SegmentResult:
    segment = db.execute(
        select(SegmentResult).where(SegmentResult.xray_id == xray.xray_id)
    ).scalar_one_or_none()
    if segment:
        return segment

    original_path = xray.xray_original_path
    segment = SegmentResult(
        xray_id=xray.xray_id,
        mask_path=original_path,
        left_lung_view_path=original_path,
        right_lung_view_path=original_path,
        heart_view_path=original_path,
        heart_area=None,
        left_lung_area=None,
        right_lung_area=None,
        model_version="manual-mock",
    )
    db.add(segment)
    db.flush()
    return segment


def manual_save_report(
    db: Session,
    *,
    patient_name: str,
    patient_gender: int | None,
    patient_age: int | None,
    exam_date: str | None,
    xray_format: str | None,
    report_content: str,
    upload_file,
    upload_user_id: int,
    report_id: int | None = None,
    xray_id: int | None = None,
    action_type: str | None = None,
) -> ReportInfo:
    content = str(report_content or "").strip()
    if not content:
        raise AppException("EMPTY_REPORT", "报告内容不能为空", status_code=400)

    history_action = _normalize_manual_save_action(action_type)
    upload_time = _parse_manual_upload_time(exam_date)
    target_report = None

    if report_id is not None:
        target_report = db.get(ReportInfo, report_id)
        if not target_report:
            raise AppException("REPORT_NOT_FOUND", "报告不存在", status_code=404)
        if xray_id is not None and target_report.xray_id != xray_id:
            raise AppException("REPORT_XRAY_MISMATCH", "报告与影像记录不匹配", status_code=400)
        xray_id = target_report.xray_id

    try:
        if xray_id is not None:
            xray = db.get(XrayInfo, xray_id)
            if not xray:
                raise AppException("XRAY_NOT_FOUND", "影像不存在", status_code=404)

            xray.patient_name = patient_name
            xray.patient_gender = patient_gender
            xray.patient_age = patient_age
            xray.xray_format = xray_format or xray.xray_format or "PNG"
            if exam_date:
                xray.upload_time = upload_time
            db.add(xray)
            db.flush()
        else:
            if upload_file is None:
                raise AppException("XRAY_FILE_REQUIRED", "请先上传胸片文件", status_code=400)
            patient_id = _build_manual_patient_id()
            file_path = save_upload(upload_file, patient_id)

            xray = XrayInfo(
                patient_id=patient_id,
                patient_name=patient_name,
                patient_gender=patient_gender,
                patient_age=patient_age,
                xray_original_path=file_path,
                xray_format=xray_format or "PNG",
                upload_user_id=upload_user_id,
                upload_time=upload_time,
                segment_status=0,  # Set to pending so real segmentation can be triggered on-demand
            )
            db.add(xray)
            db.flush()

        # 手工保存报告时如果真实分割尚未完成，写入占位分割记录以满足 report_info 外键约束。
        # 分割流水完成后会用真实结果覆盖 manual-mock 记录。
        segment = _get_or_create_manual_segment(db, xray)

        if target_report is None and xray_id is not None:
            target_report = db.execute(
                select(ReportInfo)
                .where(ReportInfo.xray_id == xray.xray_id)
                .order_by(ReportInfo.generate_time.desc())
            ).scalars().first()

        if target_report is not None:
            parent = _ensure_report_history_baseline(db, target_report)
            target_report.segment_id = segment.segment_id
            target_report.report_content = content
            target_report.report_pdf_path = None
            db.add(target_report)
            _create_report_history(
                db,
                target_report,
                action_type=history_action,
                action_user_id=upload_user_id,
                parent_history_id=parent.history_id,
                action_note=_manual_action_note(history_action, is_first_snapshot=False),
            )
            db.commit()
            db.refresh(target_report)
            return target_report

        report = ReportInfo(
            xray_id=xray.xray_id,
            segment_id=segment.segment_id,
            report_content=content,
            report_pdf_path=None,
            audit_status=0,
            audit_user_id=None,
            audit_time=None,
            revise_content=None,
        )
        db.add(report)
        db.flush()
        _create_report_history(
            db,
            report,
            action_type=history_action,
            action_user_id=upload_user_id,
            action_note=_manual_action_note(history_action, is_first_snapshot=True),
        )
        db.commit()
        db.refresh(report)
        return report
    except Exception:
        db.rollback()
        raise
