"""Relational controls and execution records added after the initial application."""
from datetime import datetime
from sqlalchemy import JSON, DateTime, ForeignKey, LargeBinary, String, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base, uid, now, immutable,FinancialJSON


class FinancialAccount(Base):
    __tablename__ = 'financial_accounts'
    __table_args__ = (UniqueConstraint('org_id', 'code'),)
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), index=True)
    code: Mapped[str]
    name: Mapped[str]
    currency: Mapped[str] = mapped_column(default='*')
    active: Mapped[bool] = mapped_column(default=True)


class AccountingPolicy(Base):
    __tablename__ = 'accounting_policies'
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), primary_key=True)
    version: Mapped[int] = mapped_column(default=1)
    settings: Mapped[dict] = mapped_column(FinancialJSON)


class CanonicalRecord(Base):
    __tablename__ = 'normalized_transactions'
    transaction_id: Mapped[str] = mapped_column(ForeignKey('imported_transactions.id'), primary_key=True)
    fields: Mapped[dict] = mapped_column(FinancialJSON)
    transformations: Mapped[list] = mapped_column(FinancialJSON)


class ImportedFile(Base):
    __tablename__ = 'imported_files'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    dataset_id: Mapped[str] = mapped_column(ForeignKey('datasets.id'), unique=True)
    sha256: Mapped[str]
    filename: Mapped[str]
    content: Mapped[bytes] = mapped_column(LargeBinary)


class MatchMembership(Base):
    __tablename__ = 'match_memberships'
    __table_args__ = (UniqueConstraint('job_id', 'transaction_id'),)
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    job_id: Mapped[str] = mapped_column(ForeignKey('reconciliation_jobs.id'), index=True)
    match_id: Mapped[str] = mapped_column(ForeignKey('reconciliation_matches.id'))
    transaction_id: Mapped[str] = mapped_column(ForeignKey('imported_transactions.id'))
    side: Mapped[str]


class MatchDecision(Base):
    __tablename__ = 'match_decisions'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    match_id: Mapped[str] = mapped_column(ForeignKey('reconciliation_matches.id'), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    decision: Mapped[str]
    reason: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AgentExecution(Base):
    __tablename__ = 'agent_executions'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    exception_id: Mapped[str] = mapped_column(ForeignKey('reconciliation_exceptions.id'), index=True)
    run_id: Mapped[str] = mapped_column(index=True)
    agent: Mapped[str]
    iteration: Mapped[int]
    output: Mapped[dict] = mapped_column(FinancialJSON)
    duration_ms: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class WorkflowCheckpoint(Base):
    __tablename__ = 'workflow_checkpoints'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    exception_id: Mapped[str] = mapped_column(ForeignKey('reconciliation_exceptions.id'), index=True)
    run_id: Mapped[str] = mapped_column(index=True)
    node: Mapped[str]
    state: Mapped[dict] = mapped_column(FinancialJSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Task(Base):
    __tablename__ = 'background_jobs'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    kind: Mapped[str]
    resource_id: Mapped[str]
    status: Mapped[str] = mapped_column(default='queued', index=True)
    attempts: Mapped[int] = mapped_column(default=0)
    result: Mapped[dict] = mapped_column(FinancialJSON, default=dict)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class MappingTemplate(Base):
    __tablename__ = 'mapping_templates'
    __table_args__ = (UniqueConstraint('org_id', 'name'),)
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), index=True)
    name: Mapped[str]
    mapping: Mapped[dict] = mapped_column(FinancialJSON)


class TokenGrant(Base):
    __tablename__ = 'access_tokens'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    token_hash: Mapped[str] = mapped_column(unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(default=False)


class LoginAccount(Base):
    __tablename__ = 'login_accounts'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'),primary_key=True)
    username_key: Mapped[str] = mapped_column(String(80),unique=True)
    password_hash: Mapped[str] = mapped_column(String(256))


class ModelArtifact(Base):
    __tablename__ = 'model_artifacts'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), index=True)
    version: Mapped[str]
    kind: Mapped[str]
    artifact: Mapped[bytes] = mapped_column(LargeBinary)
    metrics: Mapped[dict] = mapped_column(FinancialJSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class RateCounter(Base):
    __tablename__ = 'rate_counters'
    key: Mapped[str] = mapped_column(primary_key=True)
    window: Mapped[int] = mapped_column(index=True)
    count: Mapped[int]


class CaseState(Base):
    __tablename__='exception_case_states'
    exception_id:Mapped[str]=mapped_column(ForeignKey('reconciliation_exceptions.id'),primary_key=True)
    assigned_user_id:Mapped[str|None]=mapped_column(ForeignKey('users.id'))
    resolved_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))


for model in (CanonicalRecord, ImportedFile, AgentExecution, WorkflowCheckpoint, MatchDecision):
    event.listen(model, 'before_update', immutable)
    event.listen(model, 'before_delete', immutable)
