"""Backfill normalized membership for matches created before the control extension."""
from uuid import uuid4
from sqlalchemy import select
from alembic import op
from app.database import Match
from app.models_extended import MatchMembership,MatchDecision

revision='0007'
down_revision='0006'


def upgrade():
    connection=op.get_bind()
    for match in connection.execute(select(Match.__table__)).mappings():
        decision=connection.execute(select(MatchDecision.decision).where(MatchDecision.match_id==match['id']).order_by(MatchDecision.created_at.desc())).scalar()
        if decision=='reject':
            continue
        for side in ('source','target'):
            for tid in match['evidence'][side+'_ids']:
                existing=connection.execute(select(MatchMembership.match_id).where(MatchMembership.job_id==match['job_id'],MatchMembership.transaction_id==tid)).scalar()
                if existing and existing!=match['id']:
                    raise RuntimeError('Historical match membership conflict requires financial review')
                if not existing:
                    connection.execute(MatchMembership.__table__.insert().values(id=str(uuid4()),job_id=match['job_id'],match_id=match['id'],transaction_id=tid,side=side))


def downgrade():
    pass
