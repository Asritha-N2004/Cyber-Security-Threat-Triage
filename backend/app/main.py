import csv
import io
import json
import os
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from decimal import Decimal

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import Adjustment, Audit, Dataset, ExceptionRecord, Job, Match, Proposal, Reflection, Transaction, User, engine, get_db
from .ingestion import MAX_BYTES, ingest, read_file,CURRENCY_PRECISION
from .orchestration import investigate
from .providers import get_provider
from .reconciliation_engine import reconcile
from .reconciliation_engine.workflows import reconcile_workflow
from .models_extended import MatchMembership, AgentExecution, WorkflowCheckpoint, ImportedFile, CanonicalRecord
from .policies import policy_context, period_findings
from .schemas import Correction, JobInput, ManualInput, Rules
from .security import current_user, require,local_demo_request,local_demo_users,default_demo_user
from .synthetic import generate
from .validation import validate_correction

write_lock = threading.RLock()


@asynccontextmanager
async def lifespan(app):
    if not inspect(engine).has_table('organizations'):
        raise RuntimeError('Database not initialized. Run: python -m alembic upgrade head')
    yield


app = FastAPI(title='Reconcile / Financial Control Workspace', version='0.1.0', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=os.getenv('CORS_ORIGINS', 'http://localhost:5173').split(','),
    allow_methods=['GET', 'POST'], allow_headers=['Authorization', 'Content-Type', 'Idempotency-Key','X-Local-Demo-User'])
requests_by_key = defaultdict(deque)


@app.middleware('http')
async def limits(request: Request, call_next):
    length=request.headers.get('content-length')
    if length and (not length.isdigit() or int(length)>11*1024*1024):
        return JSONResponse(status_code=413,content={'detail':'Request body exceeds 11 MB'})
    # Local single-process limiter; production must enforce shared limits at gateway.
    key = request.client.host if request.client else 'unknown'
    if os.getenv('RATE_LIMIT_BACKEND','memory')=='database':
        from .rate_limit import consume
        from .database import SessionLocal
        from starlette.concurrency import run_in_threadpool
        def consume_shared():
            with SessionLocal() as session:
                return consume(session,key,int(os.getenv('RATE_LIMIT_PER_MINUTE','240')))
        if not await run_in_threadpool(consume_shared):
            return JSONResponse(status_code=429,content={'detail':'Shared rate limit exceeded'})
    current = time.monotonic()
    window = requests_by_key[key]
    while window and window[0] < current - 60:
        window.popleft()
    if os.getenv('RATE_LIMIT_BACKEND','memory')!='database' and len(window) >= int(os.getenv('RATE_LIMIT_PER_MINUTE', '240')):
        return JSONResponse(status_code=429, content={'detail': 'Rate limit exceeded'})
    window.append(current)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.exception_handler(ValueError)
async def value_error(request, exc):
    return JSONResponse(status_code=422, content={'detail': str(exc)})


@app.exception_handler(IntegrityError)
async def conflict(request, exc):
    return JSONResponse(status_code=409, content={'detail': 'Operation conflicts with an existing record'})


def row(model):
    if model is None:
        return None
    result={column.key: str(value) if isinstance(value := getattr(model, column.key), Decimal) else value
        for column in model.__table__.columns}
    if isinstance(model,ExceptionRecord):
        from .models_extended import CaseState
        from sqlalchemy.orm import object_session
        session=object_session(model)
        case=session.get(CaseState,model.id) if session else None
        assignee=session.get(User,case.assigned_user_id) if case and case.assigned_user_id else None
        result|={'assigned_user_id':case.assigned_user_id if case else None,'assigned_investigator':assignee.name if assignee else None,
            'resolved_at':case.resolved_at if case else None,'root_cause':model.analysis.get('cause')}
    return result


def audit(db, user, action, resource_id, detail=None):
    db.add(Audit(org_id=user.org_id, user_id=user.id, action=action, resource_id=resource_id, detail=detail or {}))


def owned(db, model, identifier, user, lock=False):
    if model in (Dataset, Job):
        statement = select(model).where(model.id == identifier, model.org_id == user.org_id)
    elif model == ExceptionRecord:
        statement = select(model).join(Job).where(model.id == identifier, Job.org_id == user.org_id)
    elif model == Proposal:
        statement = select(model).join(ExceptionRecord).join(Job).where(model.id == identifier, Job.org_id == user.org_id)
    else:
        raise ValueError('Unsupported ownership scope')
    if lock:
        statement = statement.with_for_update()
    record = db.scalar(statement)
    if record is None:
        raise HTTPException(404, 'Record not found')
    return record


def context_for(db, exception):
    job = db.get(Job, exception.job_id)
    policy = policy_context(db, job.org_id)
    identifiers=list(dict.fromkeys(exception.evidence['transaction_ids']+exception.evidence.get('candidate_ids',[])))
    scope={job.source_id,job.target_id,*job.rules.get('supporting_dataset_ids',[])}
    records = list(db.scalars(select(Transaction).where(Transaction.id.in_(identifiers),Transaction.dataset_id.in_(scope))))
    if {r.id for r in records}!=set(identifiers):
        raise ValueError('Exception evidence cannot be traced to the reconciliation datasets')
    order={identifier:index for index,identifier in enumerate(identifiers)}
    records.sort(key=lambda record:order[record.id])
    fee = (exception.category == 'unmatched_source' and len(records) == 1
        and policy['bank_codes'].get(str(records[0].original.get('transaction_type','')).upper()) == 'bank_charge' and records[0].amount < 0
        and records[0].currency in CURRENCY_PRECISION)
    import datetime
    return {'transaction_ids': identifiers, 'category': exception.category,
        'amount': str(exception.amount), 'currency': exception.currency, 'supported_bank_fee': fee,
        'high_value': exception.amount >= Decimal(policy['dual_approval_threshold']),
        'workflow': job.kind, 'records': [{**row(r), 'canonical': row(db.get(CanonicalRecord,r.id))} for r in records],
        'quality_reports': [db.get(Dataset, dataset_id).quality for dataset_id in (job.source_id, job.target_id)],
        'matching_evidence': exception.evidence, 'posting_date': datetime.datetime.now(datetime.timezone.utc).date().isoformat(), **policy}


@app.get('/api/v1/health')
def health(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {'status': 'ok', 'mode': os.getenv('EXECUTION_MODE', 'recommendation'), 'provider': os.getenv('LLM_PROVIDER', 'mock')}


@app.get('/api/v1/me')
def me(user: User = Depends(current_user)):
    return {'id': user.id, 'name': user.name, 'role': user.role, 'org_id': user.org_id}


@app.get('/api/v1/auth/mode')
def auth_mode(request:Request,response:Response,db:Session=Depends(get_db)):
    if os.getenv('ACCOUNT_LOGIN_MODE','false').lower()=='true':
        return {'mode':'account','users':[],'default_user_id':None}
    from .hosted_demo import enabled,users_for_request
    if enabled():
        users=users_for_request(request,db,create=True,response=response)
        selected=default_demo_user(users)
        return {'mode':'hosted_demo','users':[{'id':u.id,'name':u.name,'role':u.role} for u in users],
            'default_user_id':selected.id if selected else None}
    if not local_demo_request(request):
        return {'mode':'token','users':[],'default_user_id':None}
    users=local_demo_users(db)
    selected=default_demo_user(users)
    return {'mode':'local_demo','users':[{'id':u.id,'name':u.name,'role':u.role} for u in users],
        'default_user_id':selected.id if selected else None}


@app.post('/api/v1/data/records', status_code=201)
def manual(body: ManualInput, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require(user, 'analyst', 'admin')
    dataset = ingest(db, user.org_id, body.name, body.source, body.records, body.mapping)
    audit(db, user, 'data.imported', dataset.id, {'accepted': dataset.quality['accepted'], 'rejected': dataset.quality['rejected']})
    db.commit()
    return row(dataset)


@app.post('/api/v1/data/upload', status_code=201)
def upload(file: UploadFile = File(...), source: str = Form(...), mapping: str = Form('{}'),
    db: Session = Depends(get_db), user: User = Depends(current_user)):
    require(user, 'analyst', 'admin')
    content = file.file.read(MAX_BYTES + 1)
    try:
        field_map = json.loads(mapping)
        if not isinstance(field_map, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in field_map.items()):
            raise ValueError('Mapping must be a JSON object of source-to-canonical column names')
        records = read_file(file.filename or '', content)
    except (UnicodeError, json.JSONDecodeError, OSError) as exc:
        raise HTTPException(422, 'Invalid file encoding or structure') from exc
    dataset = ingest(db, user.org_id, (file.filename or 'Upload').replace('\\', '/').split('/')[-1], source, records, field_map)
    import hashlib
    from .protection import protect
    db.add(ImportedFile(dataset_id=dataset.id, filename=dataset.name, content=protect(content), sha256=hashlib.sha256(content).hexdigest()))
    audit(db, user, 'data.imported', dataset.id, {'accepted': dataset.quality['accepted'], 'rejected': dataset.quality['rejected']})
    db.commit()
    return row(dataset)


@app.get('/api/v1/data/datasets')
def datasets(offset: int = 0, limit: int = 100, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return [row(d) for d in db.scalars(select(Dataset).where(Dataset.org_id == user.org_id).order_by(Dataset.created_at.desc()).offset(max(0, offset)).limit(min(max(1, limit), 200)))]


@app.get('/api/v1/data/datasets/{identifier}')
def dataset(identifier: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return row(owned(db, Dataset, identifier, user))


@app.get('/api/v1/data/datasets/{identifier}/quality')
def quality(identifier: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return owned(db, Dataset, identifier, user).quality


@app.get('/api/v1/data/datasets/{identifier}/transactions')
def transactions(identifier: str, offset: int = 0, limit: int = 100, db: Session = Depends(get_db), user: User = Depends(current_user)):
    owned(db, Dataset, identifier, user)
    return [row(t) for t in db.scalars(select(Transaction).where(Transaction.dataset_id == identifier).offset(max(0, offset)).limit(min(max(1, limit), 200)))]


@app.post('/api/v1/reconciliation', status_code=201)
def create_job(body: JobInput, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require(user, 'analyst', 'admin')
    if body.source_id == body.target_id:
        raise HTTPException(422, 'Source and target must be distinct datasets')
    if len(set(body.rules.supporting_dataset_ids)) != len(body.rules.supporting_dataset_ids) or set(body.rules.supporting_dataset_ids) & {body.source_id,body.target_id}:
        raise HTTPException(422,'Supporting datasets must be distinct from source and target')
    for identifier in (body.source_id, body.target_id, *body.rules.supporting_dataset_ids):
        d = owned(db, Dataset, identifier, user)
        if not d.quality['accepted']:
            raise HTTPException(422, 'Cannot reconcile empty dataset')
    job = Job(org_id=user.org_id, source_id=body.source_id, target_id=body.target_id, kind=body.kind, rules=body.rules.model_dump(mode='json'))
    db.add(job)
    db.flush()
    audit(db, user, 'reconciliation.created', job.id)
    db.commit()
    return row(job)


def run_job(db, job, user):
    if job.status == 'completed':
        return job
    a = list(db.scalars(select(Transaction).where(Transaction.dataset_id == job.source_id)))
    b = list(db.scalars(select(Transaction).where(Transaction.dataset_id == job.target_id)))
    rules = Rules.model_validate(job.rules)
    support = list(db.scalars(select(Transaction).where(Transaction.dataset_id.in_(rules.supporting_dataset_ids)))) if rules.supporting_dataset_ids else []
    result = reconcile_workflow(a, b, rules, job.kind, support)
    for match in result.pop('matches'):
        stored_match = Match(job_id=job.id, kind=match['kind'], evidence=match)
        db.add(stored_match)
        db.flush()
        for side in ('source','target'):
            for tid in match[side+'_ids']:
                db.add(MatchMembership(job_id=job.id, match_id=stored_match.id, transaction_id=tid, side=side))
    exceptions = result.pop('exceptions')
    for exception in exceptions:
        db.add(ExceptionRecord(job_id=job.id, **exception))
    job.result = result | {'exception_count': len(exceptions)}
    job.status = 'completed'
    audit(db, user, 'reconciliation.completed', job.id, job.result)
    db.flush()
    return job


@app.post('/api/v1/reconciliation/{identifier}/run')
def run(identifier: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require(user, 'analyst', 'admin')
    with write_lock:
        job = owned(db, Job, identifier, user, lock=True)
        run_job(db, job, user)
        db.commit()
        return row(job)


@app.get('/api/v1/reconciliation')
def jobs(offset: int = 0, limit: int = 100, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return [row(j) for j in db.scalars(select(Job).where(Job.org_id == user.org_id).order_by(Job.created_at.desc()).offset(max(0, offset)).limit(min(max(1, limit), 200)))]


@app.get('/api/v1/reconciliation/{identifier}')
def job_details(identifier: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return row(owned(db, Job, identifier, user))


@app.get('/api/v1/reconciliation/{identifier}/matches')
def matches(identifier: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    owned(db, Job, identifier, user)
    from .models_extended import MatchDecision
    results=[]
    for match in db.scalars(select(Match).where(Match.job_id==identifier)):
        decision=db.scalar(select(MatchDecision).where(MatchDecision.match_id==match.id).order_by(MatchDecision.created_at.desc()))
        results.append(row(match)|{'review_status':decision.decision if decision else 'deterministic'})
    return results


@app.get('/api/v1/reconciliation/{identifier}/exceptions')
def job_exceptions(identifier: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    owned(db, Job, identifier, user)
    return [row(e) for e in db.scalars(select(ExceptionRecord).where(ExceptionRecord.job_id == identifier))]


@app.get('/api/v1/exceptions')
def exceptions(offset: int = 0, limit: int = 100, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return [row(e) for e in db.scalars(select(ExceptionRecord).join(Job).where(Job.org_id == user.org_id).order_by(ExceptionRecord.created_at.desc()).offset(max(0, offset)).limit(min(max(1, limit), 200)))]


@app.get('/api/v1/exceptions/{identifier}')
def exception_details(identifier: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    e = owned(db, ExceptionRecord, identifier, user)
    records = list(db.scalars(select(Transaction).where(Transaction.id.in_(e.evidence['transaction_ids']))))
    p = db.scalar(select(Proposal).where(Proposal.exception_id == identifier))
    return row(e) | {'records': [row(t) for t in records], 'proposal': row(p)}


@app.post('/api/v1/exceptions/{identifier}/investigate')
@app.post('/api/v1/exceptions/{identifier}/corrections/propose')
def investigation(identifier: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require(user, 'analyst', 'admin')
    with write_lock:
        e = owned(db, ExceptionRecord, identifier, user, lock=True)
        existing = db.scalar(select(Proposal).where(Proposal.exception_id == identifier))
        if existing:
            return row(existing)
        from uuid import uuid4
        run_id=str(uuid4())
        context=context_for(db,e)
        db.commit()
        def save_checkpoint(node,state):
            db.add(WorkflowCheckpoint(exception_id=e.id,run_id=run_id,node=node,state=state))
            if state['executions'] and state['executions'][-1]['node']==node:
                event=state['executions'][-1]
                db.add(AgentExecution(exception_id=e.id,run_id=run_id,agent=event['agent'],iteration=event['iteration'],
                    output=event['output'],duration_ms=event['duration_ms']))
            db.commit()
        previous_checkpoint=db.scalar(select(WorkflowCheckpoint).where(WorkflowCheckpoint.exception_id==identifier).order_by(WorkflowCheckpoint.created_at.desc()))
        resume=previous_checkpoint.state if previous_checkpoint and previous_checkpoint.state.get('context')==context else None
        state, analysis = investigate(context, get_provider(), int(os.getenv('MAX_CORRECTION_ITERATIONS', '3')),checkpoint=save_checkpoint,resume=resume)
        e.analysis = analysis
        for item in state['history']:
            db.add(Reflection(exception_id=e.id, iteration=item['iteration'], detail=item))
        if state['failure']:
            e.status = 'escalated'
            audit(db, user, 'investigation.failed', e.id)
            db.commit()
            raise HTTPException(503, state['failure'])
        p = Proposal(exception_id=e.id, maker_id=user.id, content=state['proposal'], validation=state['validation'], status='validated' if state['validation']['passed'] else 'escalated')
        db.add(p)
        e.status = 'investigated' if state['validation']['passed'] else 'escalated'
        db.flush()
        audit(db, user, 'investigation.completed', e.id, {'proposal_id': p.id, 'iterations': state['iteration'], 'provider': get_provider().name})
        db.commit()
        return row(p)


@app.get('/api/v1/exceptions/{identifier}/analysis')
def analysis(identifier: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return owned(db, ExceptionRecord, identifier, user).analysis


@app.get('/api/v1/exceptions/{identifier}/reflections')
def reflections(identifier: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    owned(db, ExceptionRecord, identifier, user)
    return [row(r) for r in db.scalars(select(Reflection).where(Reflection.exception_id == identifier).order_by(Reflection.iteration))]


@app.get('/api/v1/corrections')
def corrections(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return [row(p) for p in db.scalars(select(Proposal).join(ExceptionRecord).join(Job).where(Job.org_id == user.org_id).limit(200))]


@app.post('/api/v1/corrections/{identifier}/validate')
def validate(identifier: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require(user, 'analyst', 'approver', 'admin')
    with write_lock:
        p = owned(db, Proposal, identifier, user, lock=True)
        e = owned(db, ExceptionRecord, p.exception_id, user)
        p.validation = validate_correction(Correction.model_validate(p.content), context_for(db, e)).model_dump()
        audit(db, user, 'correction.validated', p.id, p.validation)
        db.commit()
        return row(p)


@app.post('/api/v1/corrections/{identifier}/approve')
def approve(identifier: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require(user, 'approver', 'admin')
    with write_lock:
        p = owned(db, Proposal, identifier, user, lock=True)
        e = owned(db, ExceptionRecord, p.exception_id, user)
        if p.maker_id == user.id:
            raise HTTPException(403, 'Maker cannot approve their own proposal')
        if p.status not in ('validated', 'approved') or p.content['action'] == 'manual_review':
            raise HTTPException(409, 'Proposal is not eligible for approval')
        result = validate_correction(Correction.model_validate(p.content), context_for(db, e))
        if not result.passed:
            raise HTTPException(409, 'Independent validation failed')
        if user.id not in p.approvals:
            p.approvals = p.approvals + [user.id]
            audit(db, user, 'correction.approved', p.id)
        needed = 2 if context_for(db, e)['high_value'] else 1
        if len(p.approvals) >= needed:
            p.status = 'approved'
        db.commit()
        return row(p)


@app.post('/api/v1/corrections/{identifier}/reject')
def reject(identifier: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require(user, 'approver', 'admin')
    with write_lock:
        p = owned(db, Proposal, identifier, user, lock=True)
        if p.status in ('executed', 'reversed'):
            raise HTTPException(409, 'Executed proposal requires reversal')
        p.status = 'rejected'
        audit(db, user, 'correction.rejected', p.id)
        db.commit()
        return row(p)


@app.post('/api/v1/corrections/{identifier}/execute')
def execute(identifier: str, idempotency_key: str = Header(..., min_length=8, max_length=120), db: Session = Depends(get_db), user: User = Depends(current_user)):
    require(user, 'approver', 'admin')
    if os.getenv('EXECUTION_MODE', 'recommendation') != 'simulation':
        raise HTTPException(403, 'Recommendation-only mode; enable simulation explicitly')
    with write_lock:
        p = owned(db, Proposal, identifier, user, lock=True)
        operation_key = f'{user.org_id}:{idempotency_key}'
        previous = db.scalar(select(Adjustment).where(Adjustment.operation_key == operation_key))
        if previous:
            if previous.proposal_id != p.id or previous.reversal_of:
                raise HTTPException(409, 'Idempotency key belongs to another operation')
            return row(previous)
        if p.status != 'approved':
            raise HTTPException(409, 'Proposal must have all required approvals')
        e = owned(db, ExceptionRecord, p.exception_id, user)
        context = context_for(db, e)
        correction = Correction.model_validate(p.content)
        validation = validate_correction(correction, context)
        required = 2 if context['high_value'] else 1
        if not validation.passed or correction.action != 'draft_journal' or len(set(p.approvals)) < required or p.maker_id in p.approvals:
            raise HTTPException(409, 'Financial controls failed')
        adjustment = Adjustment(proposal_id=p.id, operation_key=operation_key, entries=[line|{'posting_date':p.content['posting_date'],'currency':p.content['currency']} for line in p.content['lines']])
        db.add(adjustment)
        p.status = 'executed'
        e.status = 'simulated_adjustment'  # Never claim bank/ERP records have changed.
        db.flush()
        audit(db, user, 'adjustment.simulated', adjustment.id, {'proposal_id': p.id})
        db.commit()
        return row(adjustment)


@app.post('/api/v1/corrections/{identifier}/reverse')
def reverse(identifier: str, idempotency_key: str = Header(..., min_length=8, max_length=120), db: Session = Depends(get_db), user: User = Depends(current_user)):
    require(user, 'approver', 'admin')
    if os.getenv('EXECUTION_MODE', 'recommendation') != 'simulation':
        raise HTTPException(403, 'Simulation mode required')
    with write_lock:
        p = owned(db, Proposal, identifier, user, lock=True)
        operation_key = f'{user.org_id}:{idempotency_key}'
        existing = db.scalar(select(Adjustment).where(Adjustment.operation_key == operation_key))
        if existing:
            if existing.proposal_id != p.id or not existing.reversal_of:
                raise HTTPException(409, 'Idempotency key belongs to another operation')
            return row(existing)
        if p.status != 'executed' or user.id == p.maker_id:
            raise HTTPException(409, 'Only checker can reverse an executed adjustment')
        import datetime
        reversal_date=datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        period_errors=period_findings(reversal_date,policy_context(db,user.org_id))
        if period_errors:
            raise HTTPException(409,'Reversal date is in a closed accounting period')
        original = db.scalar(select(Adjustment).where(Adjustment.proposal_id == p.id, Adjustment.reversal_of.is_(None)))
        lines = [line | {'debit': line['credit'], 'credit': line['debit'],'posting_date':reversal_date} for line in original.entries]
        reversal = Adjustment(proposal_id=p.id, operation_key=operation_key, entries=lines, reversal_of=original.id)
        db.add(reversal)
        p.status = 'reversed'
        reopened=owned(db,ExceptionRecord,p.exception_id,user)
        reopened.status='open'
        from .models_extended import CaseState
        case=db.get(CaseState,reopened.id)
        if case:
            case.resolved_at=None
        db.flush()
        audit(db, user, 'adjustment.reversed', reversal.id, {'reversal_of': original.id})
        db.commit()
        return row(reversal)


@app.get('/api/v1/audit')
def audit_history(offset: int = 0, limit: int = 100, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return [row(a) for a in db.scalars(select(Audit).where(Audit.org_id == user.org_id).order_by(Audit.created_at.desc()).offset(max(0, offset)).limit(min(max(1, limit), 200)))]


@app.get('/api/v1/reports/performance')
def performance(db: Session = Depends(get_db), user: User = Depends(current_user)):
    js = list(db.scalars(select(Job).where(Job.org_id == user.org_id)))
    es = list(db.scalars(select(ExceptionRecord).join(Job).where(Job.org_id == user.org_id)))
    ps = list(db.scalars(select(Proposal).join(ExceptionRecord).join(Job).where(Job.org_id == user.org_id)))
    discrepancy = {}
    for e in es:
        discrepancy[e.currency] = str(Decimal(discrepancy.get(e.currency, '0')) + e.amount)
    return {'total_reconciliations': len(js), 'completed': sum(j.status == 'completed' for j in js),
        'matched_records': sum(j.result.get('matched_records', 0) for j in js),
        'unmatched_records': sum(j.result.get('unmatched_records', 0) for j in js),
        'open_exceptions': sum(e.status != 'resolved' for e in es), 'resolved_exceptions': sum(e.status == 'resolved' for e in es),
        'pending_approvals': sum(p.status == 'validated' and p.content['action'] == 'draft_journal' for p in ps),
        'exception_exposure_by_currency': discrepancy,
        'trend': [{'date': str(j.created_at)[:10], 'matched': j.result.get('matched_records', 0), 'unmatched': j.result.get('unmatched_records', 0)} for j in sorted(js, key=lambda j: j.created_at)]}


@app.get('/api/v1/reports/exceptions')
def exception_report(db: Session = Depends(get_db), user: User = Depends(current_user)):
    es = list(db.scalars(select(ExceptionRecord).join(Job).where(Job.org_id == user.org_id)))
    categories = {}
    for e in es:
        categories[e.category] = categories.get(e.category, 0) + 1
    return {'categories': categories, 'total': len(es)}


@app.get('/api/v1/reports/reconciliation/{identifier}')
def report(identifier: str, format: str = 'json', db: Session = Depends(get_db), user: User = Depends(current_user)):
    job = owned(db, Job, identifier, user)
    es = list(db.scalars(select(ExceptionRecord).where(ExceptionRecord.job_id == identifier)))
    if format == 'csv':
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['exception_id', 'category', 'amount', 'currency', 'status'])
        for e in es:
            writer.writerow([e.id, e.category, str(e.amount), e.currency, e.status])
        return Response(output.getvalue(), media_type='text/csv', headers={'Content-Disposition': 'attachment; filename=reconciliation.csv'})
    if format not in ('json','pdf'):
        raise HTTPException(422, 'Supported report formats: json, csv, pdf')
    adjustments = list(db.scalars(select(Adjustment).join(Proposal).join(ExceptionRecord).where(ExceptionRecord.job_id == identifier)))
    simulated_cash = {}
    for adjustment in adjustments:
        proposal = db.get(Proposal, adjustment.proposal_id)
        currency = proposal.content['currency']
        delta = sum((Decimal(line['debit']) - Decimal(line['credit']) for line in adjustment.entries if line['account'] == proposal.content.get('cash_account','cash')), Decimal(0))
        simulated_cash[currency] = simulated_cash.get(currency, Decimal(0)) + delta
    adjusted = {}
    for currency, totals in job.result.get('totals_by_currency', {}).items():
        ledger = Decimal(totals['target']) + simulated_cash.get(currency, Decimal(0))
        adjusted[currency] = {'simulated_cash_adjustment': str(simulated_cash.get(currency, Decimal(0))),
            'simulated_target_total': str(ledger), 'simulated_difference': str(Decimal(totals['source']) - ledger)}
    result={'job': row(job), 'exceptions': [row(e) for e in es], 'adjustments': [row(a) for a in adjustments],
        'simulation_by_currency': adjusted, 'note': 'Original source totals remain immutable. Simulated cash balances are independently recalculated; no ERP posting or automatic exception resolution occurs.'}
    from .financial_reports import accounting_statement
    source=list(db.scalars(select(Transaction).where(Transaction.dataset_id==job.source_id)))
    target=list(db.scalars(select(Transaction).where(Transaction.dataset_id==job.target_id)))
    result['accounting_statement']=accounting_statement(job.kind,source,target)
    if format=='pdf':
        from .reporting import render_pdf
        return Response(render_pdf(result),media_type='application/pdf',headers={'Content-Disposition':'attachment; filename=reconciliation.pdf'})
    return result


@app.post('/api/v1/demo', status_code=201)
def demo(db: Session = Depends(get_db), user: User = Depends(current_user)):
    require(user, 'analyst', 'admin')
    bank, ledger = generate()
    a = ingest(db, user.org_id, 'Synthetic bank / January', 'bank', bank)
    b = ingest(db, user.org_id, 'Synthetic ledger / January', 'ledger', ledger)
    job = Job(org_id=user.org_id, source_id=a.id, target_id=b.id, kind='bank', rules=Rules().model_dump(mode='json'))
    db.add(job)
    db.flush()
    audit(db, user, 'demo.synthetic_imported', job.id)
    run_job(db, job, user)
    db.commit()
    return row(job)


from .control_api import router as control_router
app.include_router(control_router)
from .ml_api import router as ml_router
app.include_router(ml_router)
from .account_auth import router as account_router
app.include_router(account_router)
