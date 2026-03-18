from pydantic import BaseModel, ConfigDict


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    report_id: int
    xray_id: int
    segment_id: int
    report_content: str
    report_pdf_path: str | None = None
    generate_time: str
    audit_status: int
    audit_user_id: int | None = None
    audit_time: str | None = None
    revise_content: str | None = None
    system_id: int | None = None


class AuditRequest(BaseModel):
    audit_status: int
    revise_content: str | None = None


class ReviseRequest(BaseModel):
    revise_content: str
    report_content: str | None = None
