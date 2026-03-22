from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.operation_log import OperationLog


async def write(
    db: Session | None,
    user_id: int,
    user_name: str,
    operation_type: str,
    operation_content: str,
    ip_address: str | None,
    operation_status: int,
    system_id: int | None = None,
) -> None:
    """Write operation log asynchronously."""
    if db is None:
        session = SessionLocal()
        try:
            log = OperationLog(
                user_id=user_id,
                user_name=user_name,
                operation_type=operation_type,
                operation_content=operation_content,
                ip_address=ip_address,
                operation_status=operation_status,
                system_id=system_id,
            )
            session.add(log)
            session.commit()
        finally:
            session.close()
        return

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
