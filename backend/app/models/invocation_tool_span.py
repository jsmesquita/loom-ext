"""Tool spans within an agent invocation (Spec 028 FinOps / usage)."""
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String
from app.db import Base


class InvocationToolSpan(Base):
    __tablename__ = "invocation_tool_spans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    invocation_id = Column(String, nullable=False, index=True)
    server_name = Column(String, nullable=True)
    tool_name = Column(String, nullable=False)
    duration_ms = Column(Float, nullable=True)
    status = Column(String, nullable=False, default="ok")  # ok | error | denied
    error_code = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "invocation_id": self.invocation_id,
            "server_name": self.server_name,
            "tool_name": self.tool_name,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "error_code": self.error_code,
            "created_at": (self.created_at.isoformat() + "Z") if self.created_at else None,
        }
