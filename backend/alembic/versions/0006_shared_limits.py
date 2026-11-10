from alembic import op
from app.models_extended import RateCounter
revision='0006'
down_revision='0005'


def upgrade():
    RateCounter.__table__.create(op.get_bind(),checkfirst=True)


def downgrade():
    RateCounter.__table__.drop(op.get_bind())
