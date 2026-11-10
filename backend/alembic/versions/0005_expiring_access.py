"""Convert existing bootstrap access to eight-hour expiring grants."""
from datetime import datetime,timedelta,timezone
from uuid import uuid4
from sqlalchemy import select
from alembic import op
from app.database import User
from app.models_extended import TokenGrant

revision='0005'
down_revision='0004'


def upgrade():
    connection=op.get_bind()
    for user in connection.execute(select(User.id,User.token_hash)).mappings():
        existing=connection.execute(select(TokenGrant.id).where(TokenGrant.token_hash==user['token_hash'])).first()
        if not existing:
            connection.execute(TokenGrant.__table__.insert().values(id=str(uuid4()),user_id=user['id'],token_hash=user['token_hash'],
                expires_at=datetime.now(timezone.utc)+timedelta(hours=8),revoked=False))


def downgrade():
    raise RuntimeError('Do not restore indefinite credentials; issue fresh expiring access instead')
