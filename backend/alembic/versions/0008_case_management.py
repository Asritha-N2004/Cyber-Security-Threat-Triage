from alembic import op
from app.models_extended import CaseState
revision='0008'
down_revision='0007'


def upgrade():
    CaseState.__table__.create(op.get_bind(),checkfirst=True)


def downgrade():
    CaseState.__table__.drop(op.get_bind())
