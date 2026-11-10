"""Atomic shared fixed-window limit for multi-process deployments."""
import hashlib
import time
from sqlalchemy import delete
from .models_extended import RateCounter


def consume(db,host,limit,current=None):
    current=time.time() if current is None else current
    window=int(current//60)
    key=hashlib.sha256(host.encode()).hexdigest()+':'+str(window)
    if db.bind.dialect.name=='postgresql':
        from sqlalchemy.dialects.postgresql import insert
    elif db.bind.dialect.name=='sqlite':
        from sqlalchemy.dialects.sqlite import insert
    else:
        raise ValueError('Shared limiter supports PostgreSQL and SQLite')
    query=insert(RateCounter).values(key=key,window=window,count=1).on_conflict_do_update(index_elements=['key'],set_={'count':RateCounter.count+1}).returning(RateCounter.count)
    count=db.scalar(query)
    db.execute(delete(RateCounter).where(RateCounter.window<window-2))
    db.commit()
    return count<=limit
