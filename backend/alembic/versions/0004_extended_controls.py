"""Add canonical, tenant policy, agent execution, task and match control tables."""
from alembic import op
from app.models_extended import FinancialAccount, AccountingPolicy, CanonicalRecord, ImportedFile, MatchMembership, MatchDecision, AgentExecution, WorkflowCheckpoint, Task, MappingTemplate, TokenGrant, ModelArtifact

revision = '0004'
down_revision = '0003'
TABLES = [FinancialAccount, AccountingPolicy, CanonicalRecord, ImportedFile, MatchMembership, MatchDecision, AgentExecution, WorkflowCheckpoint, Task, MappingTemplate, TokenGrant, ModelArtifact]


def upgrade():
    connection = op.get_bind()
    for model in TABLES:
        model.__table__.create(connection, checkfirst=True)
    for model in (CanonicalRecord, ImportedFile, AgentExecution, WorkflowCheckpoint, MatchDecision):
        table = model.__tablename__
        if connection.dialect.name == 'sqlite':
            for action in ('UPDATE', 'DELETE'):
                op.execute(f"CREATE TRIGGER IF NOT EXISTS immutable_{table}_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT, 'Append-only record'); END")
        elif connection.dialect.name == 'postgresql':
            op.execute(f'CREATE TRIGGER immutable_{table} BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION deny_financial_mutation()')


def downgrade():
    raise RuntimeError('Control/evidence migration requires an explicit archival migration for rollback')
