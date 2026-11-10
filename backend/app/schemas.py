from decimal import Decimal
from datetime import date
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class Rules(BaseModel):
    model_config = ConfigDict(extra='forbid')
    amount_tolerance: Decimal = Field(default=Decimal('0'), ge=0, le=10)
    date_days: int = Field(default=3, ge=0, le=30)
    fuzzy_threshold: float = Field(default=.88, ge=.5, le=1)
    fuzzy_enabled: bool = True
    max_group: int = Field(default=4, ge=2, le=6)
    supporting_dataset_ids: list[str] = Field(default_factory=list, max_length=8)
    account_mapping: dict[str, str] = Field(default_factory=dict)


class JobInput(BaseModel):
    source_id: str
    target_id: str
    kind: Literal['bank', 'ap', 'ar', 'gateway', 'intercompany', 'gl'] = 'bank'
    rules: Rules = Field(default_factory=Rules)


class JournalLine(BaseModel):
    account: str = Field(min_length=1, max_length=80)
    debit: Decimal = Field(default=Decimal(0), ge=0)
    credit: Decimal = Field(default=Decimal(0), ge=0)

    @field_validator('debit', 'credit')
    @classmethod
    def precision(cls, value):
        if not value.is_finite() or value != value.quantize(Decimal('.000001')):
            raise ValueError('Journal values require finite monetary amounts with at most six decimals')
        return value


class FieldValue(BaseModel):
    model_config = ConfigDict(extra='forbid')
    field: str
    value: str


class Correction(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['manual_review', 'draft_journal']
    cause: str
    rationale: str
    evidence_ids: list[str]
    currency: str
    financial_impact: Decimal
    lines: list[JournalLine] = Field(default_factory=list)
    uncertainty: list[str] = Field(default_factory=list)
    required_approval: Literal['single', 'dual', 'manual'] = 'manual'
    posting_date: date | None = None
    policy_version: int = 1
    cash_account: str = 'cash'
    target_record: str | None = None
    current_values: list[FieldValue] = Field(default_factory=list)
    proposed_values: list[FieldValue] = Field(default_factory=list)
    risk_classification: Literal['low','medium','high'] = 'high'


class Validation(BaseModel):
    passed: bool
    findings: list[str]


class AgentFinding(BaseModel):
    agent: str
    basis: Literal['deterministic', 'mock', 'llm']
    findings: list[str]
    evidence_ids: list[str]


class Investigation(BaseModel):
    cause: str
    alternative_explanations: list[str]
    uncertainty: list[str]
    agents: list[AgentFinding]


class ManualInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    source: str = Field(min_length=1, max_length=120)
    records: list[dict] = Field(min_length=1, max_length=10000)
    mapping: dict[str, str] = Field(default_factory=dict)
