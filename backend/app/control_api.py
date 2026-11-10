"""Tenant-scoped configuration, evidence and asynchronous execution endpoints."""
import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException,File,Form,UploadFile
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session
from .database import Dataset, ExceptionRecord, Job, Match, Proposal, Transaction, User, get_db, now
from .models_extended import AccountingPolicy, FinancialAccount, AgentExecution, WorkflowCheckpoint, Task, MappingTemplate, TokenGrant, MatchDecision, MatchMembership, ImportedFile
from .policies import ensure_policy, DEFAULTS
from .models_extended import CaseState
from .security import current_user, require, token_hash

router=APIRouter(prefix='/api/v1')


@router.get('/users')
def tenant_users(db:Session=Depends(get_db),user:User=Depends(current_user)):
    return [{'id':u.id,'name':u.name,'role':u.role} for u in db.scalars(select(User).where(User.org_id==user.org_id))]


class AssignmentInput(BaseModel):
    assigned_user_id:str|None=None


@router.post('/exceptions/{identifier}/assign')
def assign_case(identifier:str,body:AssignmentInput,db:Session=Depends(get_db),user:User=Depends(current_user)):
    from .main import owned,audit,row
    require(user,'analyst','admin')
    exception=owned(db,ExceptionRecord,identifier,user)
    if body.assigned_user_id:
        assignee=db.scalar(select(User).where(User.id==body.assigned_user_id,User.org_id==user.org_id,User.role.in_(['analyst','admin'])))
        if assignee is None:
            raise HTTPException(404,'Investigator not found in this organization')
    case=db.get(CaseState,identifier)
    if case is None:
        case=CaseState(exception_id=identifier)
        db.add(case)
    case.assigned_user_id=body.assigned_user_id
    audit(db,user,'exception.assigned',identifier,body.model_dump())
    db.commit()
    return row(exception)


@router.post('/demo/{kind}',status_code=201)
def specialized_demo(kind:Literal['ap','ar','gateway','intercompany','gl'],db:Session=Depends(get_db),user:User=Depends(current_user)):
    from .synthetic_workflows import generate_workflow
    from .ingestion import ingest
    from .schemas import Rules
    from .main import row,run_job,audit
    require(user,'analyst','admin')
    source,target,support=generate_workflow(kind)
    a=ingest(db,user.org_id,f'Synthetic {kind} source',kind,source)
    b=ingest(db,user.org_id,f'Synthetic {kind} target',kind,target)
    supporting=[]
    if support:
        supporting=[ingest(db,user.org_id,'Synthetic purchase orders','purchase_orders',support).id]
    rules=Rules(supporting_dataset_ids=supporting,account_mapping={'SUB':'CONTROL'} if kind=='gl' else {})
    job=Job(org_id=user.org_id,source_id=a.id,target_id=b.id,kind=kind,rules=rules.model_dump(mode='json'))
    db.add(job)
    db.flush()
    audit(db,user,'demo.specialized_created',job.id,{'workflow':kind})
    run_job(db,job,user)
    db.commit()
    return row(job)


class PolicyInput(BaseModel):
    closed_through: str | None = None
    dual_approval_threshold: str = '10000'
    account_mapping: dict[str,str] = Field(default_factory=lambda:{'cash':'cash','fees':'fees'})
    bank_codes: dict[str,str] = Field(default_factory=lambda:DEFAULTS['bank_codes'].copy())
    retention_days: int = Field(default=2555,ge=1,le=36500)
    source_timezone: str = 'UTC'

    @field_validator('source_timezone')
    @classmethod
    def valid_timezone(cls,value):
        from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError('Unknown IANA timezone') from exc
        return value

    @field_validator('closed_through')
    @classmethod
    def iso_date(cls,value):
        if value:
            __import__('datetime').date.fromisoformat(value)
        return value

    @field_validator('dual_approval_threshold')
    @classmethod
    def positive_amount(cls,value):
        from .ingestion import money
        if money(value)<=0:
            raise ValueError('Approval threshold must be positive')
        return value


class AccountInput(BaseModel):
    code: str = Field(min_length=1,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
    name: str = Field(min_length=1,max_length=120)
    currency: str = '*'
    active: bool = True


class MappingInput(BaseModel):
    name: str = Field(min_length=1,max_length=120)
    mapping: dict[str,str]


class TaskInput(BaseModel):
    kind: Literal['reconciliation','investigation']
    resource_id: str


@router.post('/integrations/{kind}/import',status_code=201)
def import_integration(kind:Literal['http','database'],body:MappingInput,db:Session=Depends(get_db),user:User=Depends(current_user)):
    from .connectors import fetch_http,fetch_database
    from .ingestion import ingest
    from .main import audit,row
    require(user,'admin')
    try:
        records=fetch_http() if kind=='http' else fetch_database()
    except ValueError:
        raise
    except Exception as exc:
        raise HTTPException(502,'Configured financial source could not be retrieved') from exc
    dataset=ingest(db,user.org_id,body.name,kind,records,body.mapping)
    audit(db,user,'integration.imported',dataset.id,{'adapter':kind})
    db.commit()
    return row(dataset)


@router.post('/data/preview')
def preview(body:dict,db:Session=Depends(get_db),user:User=Depends(current_user)):
    from .ingestion import normalize,canonical_fields
    require(user,'analyst','admin')
    records=body.get('records',[])
    mapping=body.get('mapping',{})
    if not isinstance(records,list) or len(records)>20 or not isinstance(mapping,dict):
        raise HTTPException(422,'Preview accepts at most twenty records and a column mapping')
    results=[]
    default_timezone=ensure_policy(db,user.org_id).settings.get('source_timezone','UTC')
    for index,record in enumerate(records):
        try:
            normalized=normalize(record,mapping,default_timezone)
            results.append({'row':index+1,'normalized':{k:str(v) for k,v in normalized.items()},'canonical':canonical_fields(record,mapping,normalized,default_timezone),'valid':True})
        except (ValueError,TypeError,KeyError) as exc:
            results.append({'row':index+1,'valid':False,'error':str(exc)})
    return {'preview':results,'persisted':False}


@router.post('/data/upload/preview')
def preview_file(file:UploadFile=File(...),mapping:str=Form('{}'),db:Session=Depends(get_db),user:User=Depends(current_user)):
    import json
    from .ingestion import MAX_BYTES,read_file
    field_map=json.loads(mapping)
    if not isinstance(field_map,dict) or not all(isinstance(k,str) and isinstance(v,str) for k,v in field_map.items()):
        raise HTTPException(422,'Mapping must be an object of column names')
    records=read_file(file.filename or '',file.file.read(MAX_BYTES+1))
    return preview({'records':records[:20],'mapping':field_map},db,user)|{'total_records':len(records)}


@router.get('/data/datasets/{identifier}/original')
def original_file(identifier:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    from .main import owned,audit
    from .protection import unprotect
    from fastapi.responses import Response
    owned(db,Dataset,identifier,user)
    original=db.scalar(select(ImportedFile).where(ImportedFile.dataset_id==identifier))
    if original is None:
        raise HTTPException(404,'No original binary file for this dataset')
    audit(db,user,'source.downloaded',identifier,{'sha256':original.sha256})
    db.commit()
    return Response(unprotect(original.content),media_type='application/octet-stream',headers={'Content-Disposition':'attachment; filename=original-upload','X-Source-SHA256':original.sha256})


@router.get('/data/datasets/{identifier}/masked-transactions')
def masked_transactions(identifier:str,offset:int=0,limit:int=100,db:Session=Depends(get_db),user:User=Depends(current_user)):
    from .main import owned,row
    from .protection import masked
    owned(db,Dataset,identifier,user)
    return [masked(row(record)) for record in db.scalars(select(Transaction).where(Transaction.dataset_id==identifier).offset(max(0,offset)).limit(min(max(1,limit),200)))]


def export_report(title,columns,records,result,format):
    from fastapi.responses import Response
    if format=='json':
        return result
    if format=='pdf':
        from .reporting import generic_report
        return Response(generic_report(title,columns,records),media_type='application/pdf',headers={'Content-Disposition':'attachment; filename=report.pdf'})
    if format=='csv':
        import csv,io
        output=io.StringIO()
        writer=csv.writer(output)
        writer.writerow(columns)
        for record in records:
            cells=[str(record.get(column,'')) for column in columns]
            writer.writerow(["'"+cell if cell.startswith(('=','+','-','@')) else cell for cell in cells])
        return Response(output.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename=report.csv'})
    raise HTTPException(422,'Supported formats: json, csv, pdf')


@router.get('/reports/aging')
def aging_report(format:str='json',db:Session=Depends(get_db),user:User=Depends(current_user)):
    from .main import row
    exceptions=list(db.scalars(select(ExceptionRecord).join(Job).where(Job.org_id==user.org_id,ExceptionRecord.status!='resolved')))
    current=now()
    buckets={'0-7':0,'8-30':0,'31-60':0,'61+':0}
    records=[]
    for exception in exceptions:
        days=(current-exception.created_at.replace(tzinfo=timezone.utc)).days
        bucket='0-7' if days<=7 else '8-30' if days<=30 else '31-60' if days<=60 else '61+'
        buckets[bucket]+=1
        records.append(row(exception)|{'age_days':days,'aging_bucket':bucket})
    return export_report('Exception aging',['id','category','amount','currency','age_days','status'],records,
        {'buckets':buckets,'records':records,'as_of':current.isoformat()},format)


@router.get('/reports/corrections')
def correction_report(format:str='json',db:Session=Depends(get_db),user:User=Depends(current_user)):
    from .main import row
    proposals=list(db.scalars(select(Proposal).join(ExceptionRecord).join(Job).where(Job.org_id==user.org_id)))
    result={'records':[row(p) for p in proposals],'pending':sum(p.status=='validated' for p in proposals),
        'executed_simulations':sum(p.status=='executed' for p in proposals),'reversals':sum(p.status=='reversed' for p in proposals)}
    records=[{'id':p.id,'exception_id':p.exception_id,'status':p.status,'action':p.content['action'],'amount':p.content['financial_impact'],'currency':p.content['currency']} for p in proposals]
    return export_report('Correction summary',['id','status','action','amount','currency'],records,result,format)


@router.get('/reports/audit')
def audit_report(format:str='json',db:Session=Depends(get_db),user:User=Depends(current_user)):
    from .database import Audit
    from .main import row
    records=[row(a) for a in db.scalars(select(Audit).where(Audit.org_id==user.org_id).order_by(Audit.created_at))]
    return export_report('Financial audit history',['action','user_id','resource_id','created_at'],records,{'records':records},format)


class VerificationInput(BaseModel):
    verified_job_id:str
    evidence_transaction_ids:list[str]=Field(min_length=1)
    reason:str=Field(min_length=12,max_length=1000)


@router.post('/exceptions/{identifier}/verify-resolution')
def verify_resolution(identifier:str,body:VerificationInput,db:Session=Depends(get_db),user:User=Depends(current_user)):
    from .main import owned,row,audit,write_lock
    require(user,'approver','admin')
    with write_lock:
        exception=owned(db,ExceptionRecord,identifier,user,lock=True)
        original=owned(db,Job,exception.job_id,user)
        verification=owned(db,Job,body.verified_job_id,user)
        if verification.id==original.id or verification.status!='completed' or verification.kind!=original.kind:
            raise HTTPException(409,'A separate completed reconciliation of the same workflow is required')
        pairs=list(db.scalars(select(Match).where(Match.job_id==verification.id)))
        matches=[m for m in pairs if set(body.evidence_transaction_ids)==set(m.evidence['source_ids']+m.evidence['target_ids'])]
        if len(matches)!=1:
            raise HTTPException(409,'Verification evidence must belong to exactly one accepted deterministic match')
        evidence=list(db.scalars(select(Transaction).where(Transaction.id.in_(body.evidence_transaction_ids))))
        original_records=list(db.scalars(select(Transaction).where(Transaction.id.in_(exception.evidence['transaction_ids']))))
        source_anchors={r.id for r in original_records if r.dataset_id==original.source_id}
        target_anchors={r.id for r in original_records if r.dataset_id==original.target_id}
        if source_anchors:
            anchored=verification.source_id==original.source_id and source_anchors<=set(matches[0].evidence['source_ids'])
        else:
            anchored=bool(target_anchors) and verification.target_id==original.target_id and target_anchors<=set(matches[0].evidence['target_ids'])
        if not anchored:
            raise HTTPException(409,'Verification must preserve the original immutable source or target anchor')
        references={r.reference for r in original_records if r.reference}
        if not references or not references.intersection(r.reference for r in evidence) or any(r.currency!=exception.currency for r in evidence):
            raise HTTPException(409,'Verification must trace the original references and currency')
        rejected=db.scalar(select(MatchDecision).where(MatchDecision.match_id==matches[0].id).order_by(MatchDecision.created_at.desc()))
        if rejected and rejected.decision=='reject':
            raise HTTPException(409,'Rejected matches cannot verify resolution')
        exception.status='resolved'
        case=db.get(CaseState,identifier)
        if case is None:
            case=CaseState(exception_id=identifier)
            db.add(case)
        case.resolved_at=now()
        audit(db,user,'exception.verified_resolved',exception.id,body.model_dump())
        db.commit()
        return row(exception)


@router.get('/settings/policy')
def read_policy(db:Session=Depends(get_db),user:User=Depends(current_user)):
    from .main import row
    policy=ensure_policy(db,user.org_id)
    db.commit()
    return row(policy)


@router.post('/settings/policy')
def update_policy(body:PolicyInput,db:Session=Depends(get_db),user:User=Depends(current_user)):
    from .main import row,audit,write_lock
    require(user,'admin')
    with write_lock:
        policy=ensure_policy(db,user.org_id)
        previous=policy.settings
        valid_accounts={a.code for a in db.scalars(select(FinancialAccount).where(FinancialAccount.org_id==user.org_id,FinancialAccount.active.is_(True)))}
        if not {'cash','fees'}<=set(body.account_mapping) or not set(body.account_mapping.values())<=valid_accounts:
            raise HTTPException(422,'Policy mappings must reference active tenant accounts and include cash and fees')
        policy.settings=body.model_dump()
        policy.version+=1
        audit(db,user,'policy.updated',user.org_id,{'before':previous,'after':policy.settings,'version':policy.version})
        db.commit()
        return row(policy)


@router.get('/settings/accounts')
def accounts(db:Session=Depends(get_db),user:User=Depends(current_user)):
    from .main import row
    ensure_policy(db,user.org_id)
    db.commit()
    return [row(a) for a in db.scalars(select(FinancialAccount).where(FinancialAccount.org_id==user.org_id))]


@router.post('/settings/accounts')
def update_account(body:AccountInput,db:Session=Depends(get_db),user:User=Depends(current_user)):
    from .main import row,audit,write_lock
    from .ingestion import CURRENCY_PRECISION
    require(user,'admin')
    if body.currency!='*' and body.currency not in CURRENCY_PRECISION:
        raise HTTPException(422,'Unsupported account currency')
    with write_lock:
        policy=ensure_policy(db,user.org_id)
        account=db.scalar(select(FinancialAccount).where(FinancialAccount.org_id==user.org_id,FinancialAccount.code==body.code))
        if account:
            account.name,account.currency,account.active=body.name,body.currency,body.active
        else:
            account=FinancialAccount(org_id=user.org_id,**body.model_dump())
            db.add(account)
        policy.version+=1
        db.flush()
        audit(db,user,'account.configured',account.id,body.model_dump())
        db.commit()
        return row(account)


@router.get('/data/mappings')
def mappings(db:Session=Depends(get_db),user:User=Depends(current_user)):
    from .main import row
    return [row(m) for m in db.scalars(select(MappingTemplate).where(MappingTemplate.org_id==user.org_id))]


@router.post('/data/mappings',status_code=201)
def save_mapping(body:MappingInput,db:Session=Depends(get_db),user:User=Depends(current_user)):
    from .main import row,audit
    require(user,'analyst','admin')
    record=MappingTemplate(org_id=user.org_id,**body.model_dump())
    db.add(record)
    db.flush()
    audit(db,user,'mapping.created',record.id)
    db.commit()
    return row(record)


@router.get('/exceptions/{identifier}/agents')
def agents(identifier:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    from .main import owned,row
    owned(db,ExceptionRecord,identifier,user)
    return [row(a) for a in db.scalars(select(AgentExecution).where(AgentExecution.exception_id==identifier).order_by(AgentExecution.created_at))]


@router.get('/exceptions/{identifier}/checkpoints')
def checkpoints(identifier:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    from .main import owned
    owned(db,ExceptionRecord,identifier,user)
    # Raw checkpoint context is intentionally omitted from this inspection API.
    return [{'id':c.id,'node':c.node,'run_id':c.run_id,'iteration':c.state['iteration'],'created_at':c.created_at,'next_node':c.state.get('next_node')}
        for c in db.scalars(select(WorkflowCheckpoint).where(WorkflowCheckpoint.exception_id==identifier).order_by(WorkflowCheckpoint.created_at))]


@router.post('/tasks',status_code=202)
def enqueue(body:TaskInput,db:Session=Depends(get_db),user:User=Depends(current_user)):
    from .main import owned,row,audit
    require(user,'analyst','admin')
    owned(db,Job if body.kind=='reconciliation' else ExceptionRecord,body.resource_id,user)
    existing=db.scalar(select(Task).where(Task.org_id==user.org_id,Task.kind==body.kind,Task.resource_id==body.resource_id,Task.status.in_(['queued','running'])))
    if existing:
        return row(existing)
    task=Task(org_id=user.org_id,user_id=user.id,kind=body.kind,resource_id=body.resource_id)
    db.add(task)
    db.flush()
    audit(db,user,'task.queued',task.id,{'kind':body.kind})
    db.commit()
    from .hosted_demo import enabled
    if enabled() or os.getenv('VERCEL')=='1':
        # Serverless demos finish durable work inside the invocation lifetime.
        # Normal installations retain their independent leased task worker.
        from sqlalchemy.orm import sessionmaker
        from .worker import process_one
        factory=sessionmaker(db.get_bind(),expire_on_commit=False)
        for _ in range(3):
            result=process_one(factory,task_id=task.id)
            if not result or result['status']!='queued':
                break
        db.refresh(task)
    return row(task)


@router.get('/tasks/{identifier}')
def task_status(identifier:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    from .main import row
    task=db.scalar(select(Task).where(Task.id==identifier,Task.org_id==user.org_id))
    if task is None:
        raise HTTPException(404,'Task not found')
    return row(task)


@router.post('/auth/rotate')
def rotate(db:Session=Depends(get_db),user:User=Depends(current_user)):
    from .main import audit
    # Rotation revokes all prior grants and the bootstrap token atomically.
    for token in db.scalars(select(TokenGrant).where(TokenGrant.user_id==user.id,TokenGrant.revoked.is_(False))):
        token.revoked=True
    token=secrets.token_urlsafe(48)
    user.token_hash=token_hash(secrets.token_urlsafe(48))
    expires=now()+timedelta(hours=8)
    db.add(TokenGrant(user_id=user.id,token_hash=token_hash(token),expires_at=expires))
    audit(db,user,'identity.rotated',user.id)
    db.commit()
    return {'access_token':token,'expires_at':expires,'token_type':'bearer'}


class ReviewInput(BaseModel):
    decision: Literal['accept','reject']
    reason: str = Field(min_length=8,max_length=1000)


@router.post('/matches/{identifier}/review')
def review_match(identifier:str,body:ReviewInput,db:Session=Depends(get_db),user:User=Depends(current_user)):
    from .main import owned,row,audit,write_lock
    require(user,'analyst','admin')
    with write_lock:
        match=db.get(Match,identifier)
        if match is None:
            raise HTTPException(404,'Match not found')
        job=owned(db,Job,match.job_id,user,lock=True)
        previous=db.scalar(select(MatchDecision).where(MatchDecision.match_id==identifier).order_by(MatchDecision.created_at.desc()))
        if previous and previous.decision==body.decision:
            return row(previous)
        decision=MatchDecision(match_id=identifier,user_id=user.id,**body.model_dump())
        db.add(decision)
        if body.decision=='reject':
            from sqlalchemy import delete
            db.execute(delete(MatchMembership).where(MatchMembership.match_id==identifier))
            records=list(db.scalars(select(Transaction).where(Transaction.id.in_(match.evidence['source_ids']+match.evidence['target_ids']))))
            existing_exception=next((e for e in db.scalars(select(ExceptionRecord).where(ExceptionRecord.job_id==job.id,ExceptionRecord.category=='manual_match_rejection')) if e.evidence.get('match_id')==identifier),None)
            if existing_exception is None:
                db.add(ExceptionRecord(job_id=job.id,category='manual_match_rejection',severity='medium',amount=abs(records[0].amount),currency=records[0].currency,
                    evidence={'transaction_ids':[r.id for r in records],'match_id':match.id,'reason':body.reason}))
        else:
            for side in ('source','target'):
                for tid in match.evidence[side+'_ids']:
                    existing_member=db.scalar(select(MatchMembership).where(MatchMembership.job_id==job.id,MatchMembership.transaction_id==tid))
                    if existing_member and existing_member.match_id!=identifier:
                        raise HTTPException(409,'Transaction was assigned to another match')
                    if existing_member is None:
                        db.add(MatchMembership(job_id=job.id,match_id=identifier,transaction_id=tid,side=side))
        db.flush()
        matched=len(list(db.scalars(select(MatchMembership).where(MatchMembership.job_id==job.id))))
        job.result=job.result|{'matched_records':matched,'unmatched_records':job.result['total_records']-matched,
            'exception_count':len(list(db.scalars(select(ExceptionRecord.id).where(ExceptionRecord.job_id==job.id))))}
        audit(db,user,'match.reviewed',identifier,body.model_dump())
        db.flush()
        db.commit()
        return row(decision)


class ManualMatchInput(BaseModel):
    source_ids:list[str]=Field(min_length=1,max_length=6)
    target_ids:list[str]=Field(min_length=1,max_length=6)
    reason:str=Field(min_length=12,max_length=1000)


@router.post('/reconciliation/{identifier}/manual-match',status_code=201)
def manual_match(identifier:str,body:ManualMatchInput,db:Session=Depends(get_db),user:User=Depends(current_user)):
    from decimal import Decimal
    from .main import owned,row,audit,write_lock
    from .schemas import Rules
    from .reconciliation_engine.transaction_matcher import compatible
    require(user,'analyst','admin')
    with write_lock:
        job=owned(db,Job,identifier,user,lock=True)
        if job.kind!='bank' or job.status!='completed' or len(body.source_ids)>1 and len(body.target_ids)>1:
            raise HTTPException(409,'Manual matches support completed bank jobs with one-to-one, split or aggregate evidence')
        ids=body.source_ids+body.target_ids
        if len(set(ids))!=len(ids):
            raise HTTPException(422,'Transaction identifiers must be unique')
        records=list(db.scalars(select(Transaction).where(Transaction.id.in_(ids))))
        left=[r for r in records if r.id in body.source_ids and r.dataset_id==job.source_id]
        right=[r for r in records if r.id in body.target_ids and r.dataset_id==job.target_id]
        if len(left)!=len(body.source_ids) or len(right)!=len(body.target_ids):
            raise HTTPException(404,'Record not found in the specified reconciliation side')
        rules=Rules.model_validate(job.rules)
        difference=sum((r.amount for r in left),Decimal(0))-sum((r.amount for r in right),Decimal(0))
        if abs(difference)>rules.amount_tolerance or any(not compatible(a,b,rules) for a in left for b in right):
            raise HTTPException(409,'Manual review cannot bypass amount, currency, account, direction or date constraints')
        if db.scalar(select(MatchMembership.id).where(MatchMembership.job_id==job.id,MatchMembership.transaction_id.in_(ids))):
            raise HTTPException(409,'A transaction is already matched')
        match=Match(job_id=job.id,kind='manual_review',evidence={'source_ids':body.source_ids,'target_ids':body.target_ids,'amount_difference':str(difference),'reason':body.reason,'rule_version':'manual-v1'})
        db.add(match)
        db.flush()
        for side,identifiers in (('source',body.source_ids),('target',body.target_ids)):
            for tid in identifiers:
                db.add(MatchMembership(job_id=job.id,match_id=match.id,transaction_id=tid,side=side))
        db.add(MatchDecision(match_id=match.id,user_id=user.id,decision='accept',reason=body.reason))
        db.flush()
        matched=len(list(db.scalars(select(MatchMembership).where(MatchMembership.job_id==job.id))))
        job.result=job.result|{'matched_records':matched,'unmatched_records':job.result['total_records']-matched}
        audit(db,user,'match.manually_created',match.id,{'reason':body.reason,'job_id':job.id})
        db.commit()
        return row(match)
