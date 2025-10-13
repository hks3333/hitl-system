# models.py
import uuid
from sqlalchemy import Column, String, DateTime, JSON, Enum, ForeignKey, BigInteger, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

# This defines the same ENUM we created in SQL
WorkflowStateEnum = Enum(
    'PENDING_APPROVAL', 'APPROVED', 'REJECTED', 'TIMED_OUT', 'RUNNING',
    'COMPLETED', 'FAILED', 'ROLLBACK_COMPLETE',
    name='workflow_state'
)

class Workflow(Base):
    __tablename__ = 'workflows'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    current_state = Column(WorkflowStateEnum, nullable=False)
    context_data = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class AuditLog(Base):
    __tablename__ = 'audit_log'
    log_id = Column(BigInteger, primary_key=True, autoincrement=True)
    workflow_id = Column(UUID(as_uuid=True), ForeignKey('workflows.id'))
    from_state = Column(WorkflowStateEnum, nullable=True)
    to_state = Column(WorkflowStateEnum, nullable=False)
    triggered_by = Column(String(255), default='system')
    comment = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)