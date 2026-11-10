"""Durable DB-backed task worker with atomic claim, leases and bounded retries."""
import argparse
import time
from datetime import timedelta
from sqlalchemy import or_, select, update
from .database import SessionLocal, User, now
from .models_extended import Task


def process_one(factory=SessionLocal,task_id=None):
    from .main import investigation,run
    with factory() as db:
        current=now()
        db.execute(update(Task).where(Task.status=='running',Task.lease_until<current,Task.attempts>=3)
            .values(status='failed',lease_until=None,result={'error':'WorkerLeaseExpired','manual_escalation':True}))
        db.commit()
        statement=select(Task).where(or_(Task.status=='queued',(Task.status=='running') & (Task.lease_until<current)),Task.attempts<3)
        if task_id is not None:
            statement=statement.where(Task.id==task_id)
        candidate=db.scalar(statement.order_by(Task.created_at).limit(1))
        if candidate is None:
            return None
        statement=update(Task).where(Task.id==candidate.id,Task.attempts==candidate.attempts,
            or_(Task.status=='queued',(Task.status=='running') & (Task.lease_until<current)))
        claimed=db.execute(statement.values(status='running',attempts=Task.attempts+1,lease_until=current+timedelta(minutes=15)))
        if claimed.rowcount!=1:
            db.rollback()
            return None
        identifier=candidate.id
        db.commit()
        task=db.get(Task,identifier)
        user=db.get(User,task.user_id)
        try:
            result=run(task.resource_id,db,user) if task.kind=='reconciliation' else investigation(task.resource_id,db,user)
            task=db.get(Task,identifier)
            task.status='completed'
            task.result={'resource_id':result['id']}
        except Exception as exc:
            db.rollback()
            task=db.get(Task,identifier)
            retryable=getattr(exc,'status_code',503)>=500
            task.status='queued' if retryable and task.attempts<3 else 'failed'
            task.result={'error':type(exc).__name__,'manual_escalation':task.status=='failed'}
        task.lease_until=None
        db.commit()
        return {'id':task.id,'status':task.status,'attempts':task.attempts}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--once',action='store_true')
    args=parser.parse_args()
    while True:
        result=process_one()
        if args.once:
            return
        if result is None:
            time.sleep(1)


if __name__=='__main__':
    main()
