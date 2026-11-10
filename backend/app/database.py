import os
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Numeric, String, UniqueConstraint, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.types import TypeDecorator
from sqlalchemy.dialects.postgresql import JSONB
from decimal import Decimal

FinancialJSON=JSON().with_variant(JSONB(),'postgresql')


class ExactMoney(TypeDecorator):
    """SQLite NUMERIC affinity stores floats; use text there to preserve every digit."""
    impl = Numeric(24, 6)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        return dialect.type_descriptor(String(40) if dialect.name == 'sqlite' else Numeric(24, 6))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        amount = Decimal(str(value))
        return str(amount) if dialect.name == 'sqlite' else amount

    def process_result_value(self, value, dialect):
        return Decimal(str(value)) if value is not None else None


def uid():
    return str(uuid4())


def now():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Organization(Base):
    __tablename__ = 'organizations'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    name: Mapped[str]


class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), index=True)
    name: Mapped[str]
    role: Mapped[str]
    token_hash: Mapped[str] = mapped_column(unique=True)


class Dataset(Base):
    __tablename__ = 'datasets'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), index=True)
    name: Mapped[str]
    source: Mapped[str]
    quality: Mapped[dict] = mapped_column(FinancialJSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Transaction(Base):
    __tablename__ = 'imported_transactions'
    __table_args__ = (UniqueConstraint('dataset_id', 'external_id'),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    dataset_id: Mapped[str] = mapped_column(ForeignKey('datasets.id'), index=True)
    external_id: Mapped[str]
    amount: Mapped[Decimal] = mapped_column(ExactMoney())
    currency: Mapped[str]
    account: Mapped[str]
    date: Mapped[str]
    reference: Mapped[str]
    description: Mapped[str]
    counterparty: Mapped[str]
    original: Mapped[dict] = mapped_column(FinancialJSON)
    normalization: Mapped[dict] = mapped_column(FinancialJSON)


class Job(Base):
    __tablename__ = 'reconciliation_jobs'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey('datasets.id'))
    target_id: Mapped[str] = mapped_column(ForeignKey('datasets.id'))
    kind: Mapped[str]
    status: Mapped[str] = mapped_column(default='created')
    rules: Mapped[dict] = mapped_column(FinancialJSON)
    result: Mapped[dict] = mapped_column(FinancialJSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Match(Base):
    __tablename__ = 'reconciliation_matches'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    job_id: Mapped[str] = mapped_column(ForeignKey('reconciliation_jobs.id'), index=True)
    kind: Mapped[str]
    evidence: Mapped[dict] = mapped_column(FinancialJSON)


class ExceptionRecord(Base):
    __tablename__ = 'reconciliation_exceptions'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    job_id: Mapped[str] = mapped_column(ForeignKey('reconciliation_jobs.id'), index=True)
    category: Mapped[str]
    severity: Mapped[str]
    amount: Mapped[Decimal] = mapped_column(ExactMoney())
    currency: Mapped[str]
    status: Mapped[str] = mapped_column(default='open')
    evidence: Mapped[dict] = mapped_column(FinancialJSON)
    analysis: Mapped[dict] = mapped_column(FinancialJSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Proposal(Base):
    __tablename__ = 'correction_proposals'
    __table_args__ = (UniqueConstraint('exception_id'),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    exception_id: Mapped[str] = mapped_column(ForeignKey('reconciliation_exceptions.id'), index=True)
    maker_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    content: Mapped[dict] = mapped_column(FinancialJSON)
    validation: Mapped[dict] = mapped_column(FinancialJSON)
    status: Mapped[str] = mapped_column(default='proposed')
    approvals: Mapped[list] = mapped_column(FinancialJSON, default=list)


class Reflection(Base):
    __tablename__ = 'reflection_iterations'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    exception_id: Mapped[str] = mapped_column(ForeignKey('reconciliation_exceptions.id'), index=True)
    iteration: Mapped[int]
    detail: Mapped[dict] = mapped_column(FinancialJSON)


class Adjustment(Base):
    __tablename__ = 'adjustment_entries'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    proposal_id: Mapped[str] = mapped_column(ForeignKey('correction_proposals.id'), index=True)
    operation_key: Mapped[str] = mapped_column(unique=True)
    entries: Mapped[list] = mapped_column(FinancialJSON)
    reversal_of: Mapped[str | None] = mapped_column(ForeignKey('adjustment_entries.id'), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Audit(Base):
    __tablename__ = 'audit_logs'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    action: Mapped[str]
    resource_id: Mapped[str]
    detail: Mapped[dict] = mapped_column(FinancialJSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


def immutable(mapper, connection, target):
    raise ValueError('Append-only record cannot be modified or deleted')


for model in (Transaction, Adjustment, Audit, Reflection):
    event.listen(model, 'before_update', immutable)
    event.listen(model, 'before_delete', immutable)


def normalize_database_url(url):
    if url.startswith('postgres://'):
        return 'postgresql+psycopg://'+url[len('postgres://'):]
    if url.startswith('postgresql://'):
        return 'postgresql+psycopg://'+url[len('postgresql://'):]
    return url


def make_engine(url):
    url=normalize_database_url(url)
    options={'check_same_thread':False} if url.startswith('sqlite') else {'prepare_threshold':None} if url.startswith('postgresql+psycopg://') else {}
    engine = create_engine(url,connect_args=options,pool_pre_ping=True,pool_recycle=300)
    if url.startswith('sqlite'):
        @event.listens_for(engine, 'connect')
        def sqlite_foreign_keys(connection, record):
            connection.execute('PRAGMA foreign_keys=ON')
    return engine


engine = make_engine(os.getenv('DATABASE_URL', 'sqlite:///./reconciliation.db'))
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_db():
    with SessionLocal() as session:
        yield session


# Register extended metadata for migrations and test database creation.
from . import models_extended  # noqa: E402,F401
