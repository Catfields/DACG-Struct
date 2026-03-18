from sqlalchemy.orm import Session
from app.models.operation_log import OperationLog


async def write(
    db: Session,
    user_id: int,
    user_name: str,
    operation_type: str,
    operation_content: str,
    ip_address: str | None,
    operation_status: int,
    system_id: int | None = None,
) -> None:
    """Write operation log asynchronously."""
    log = OperationLog(
        user_id=user_id,
        user_name=user_name,
        operation_type=operation_type,
        operation_content=operation_content,
        ip_address=ip_address,
        operation_status=operation_status,
        system_id=system_id,
    )
    db.add(log)
    db.commit()
