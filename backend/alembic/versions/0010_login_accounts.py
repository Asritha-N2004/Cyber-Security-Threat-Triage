"""Username and password accounts with isolated workspaces."""
from alembic import op
from app.models_extended import LoginAccount

revision='0010'
down_revision='0009'


def upgrade():
    LoginAccount.__table__.create(op.get_bind(),checkfirst=True)


def downgrade():
    LoginAccount.__table__.drop(op.get_bind(),checkfirst=True)
