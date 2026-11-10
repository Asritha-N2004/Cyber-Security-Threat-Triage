"""Versioned ranking from reviewed pairs; deterministic match constraints remain authoritative."""
import pickle
from uuid import uuid4
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from .database import Match,Transaction,User,get_db
from .models_extended import MatchDecision,ModelArtifact
from .security import current_user,require
from .ml import features,train_and_evaluate

router=APIRouter(prefix='/api/v1/ml')


class TrainInput(BaseModel):
    train_job_ids:list[str]=Field(min_length=1)
    test_job_ids:list[str]=Field(min_length=1)
    kind:Literal['logistic','random_forest']='logistic'


def labeled_pairs(db,job_ids,user):
    from .main import owned
    from .database import Job
    vectors,labels,identifiers=[],[],set()
    for job_id in job_ids:
        owned(db,Job,job_id,user)
        for match in db.scalars(select(Match).where(Match.job_id==job_id)):
            decision=db.scalar(select(MatchDecision).where(MatchDecision.match_id==match.id).order_by(MatchDecision.created_at.desc()))
            if not decision or len(match.evidence['source_ids'])!=1 or len(match.evidence['target_ids'])!=1:
                continue
            left=db.get(Transaction,match.evidence['source_ids'][0])
            right=db.get(Transaction,match.evidence['target_ids'][0])
            identifiers.update([left.id,right.id])
            vectors.append(features(left,right))
            labels.append(int(decision.decision=='accept'))
    return vectors,labels,identifiers


@router.post('/train',status_code=201)
def train(body:TrainInput,db:Session=Depends(get_db),user:User=Depends(current_user)):
    from .main import audit,row
    require(user,'analyst','admin')
    if set(body.train_job_ids)&set(body.test_job_ids):
        raise HTTPException(422,'Training and test reconciliation runs must be disjoint')
    train_x,train_y,train_ids=labeled_pairs(db,body.train_job_ids,user)
    test_x,test_y,test_ids=labeled_pairs(db,body.test_job_ids,user)
    if train_ids&test_ids:
        raise HTTPException(422,'Source record leakage between training and test sets')
    if len(train_x)<4 or set(train_y)!={0,1} or not test_x:
        raise HTTPException(422,'Need at least four reviewed training pairs with both outcomes and a nonempty held-out run')
    try:
        model,metrics=train_and_evaluate(train_x,train_y,test_x,test_y,body.kind)
    except ImportError as exc:
        raise HTTPException(503,'Install requirements-research.txt to enable ML training') from exc
    version=str(uuid4())
    metrics|={'training_pairs':len(train_x),'heldout_pairs':len(test_x),'train_job_ids':body.train_job_ids,'test_job_ids':body.test_job_ids,'feedback_source':'audited human reviews'}
    artifact=ModelArtifact(org_id=user.org_id,version=version,kind=body.kind,artifact=pickle.dumps(model),metrics=metrics)
    db.add(artifact)
    db.flush()
    audit(db,user,'ml.trained',artifact.id,{'version':version,'kind':body.kind})
    db.commit()
    result=row(artifact)
    result.pop('artifact')
    return result


@router.get('/models')
def models(db:Session=Depends(get_db),user:User=Depends(current_user)):
    return [{'id':m.id,'version':m.version,'kind':m.kind,'metrics':m.metrics,'created_at':m.created_at}
        for m in db.scalars(select(ModelArtifact).where(ModelArtifact.org_id==user.org_id).order_by(ModelArtifact.created_at.desc()))]


class RankInput(BaseModel):
    source_transaction_id:str
    target_transaction_ids:list[str]=Field(min_length=1,max_length=100)


@router.post('/models/{identifier}/rank')
def rank(identifier:str,body:RankInput,db:Session=Depends(get_db),user:User=Depends(current_user)):
    from .database import Dataset
    from .reconciliation_engine.transaction_matcher import compatible
    from .schemas import Rules
    artifact=db.scalar(select(ModelArtifact).where(ModelArtifact.id==identifier,ModelArtifact.org_id==user.org_id))
    if artifact is None:
        raise HTTPException(404,'Model not found')
    def transaction(tid):
        value=db.scalar(select(Transaction).join(Dataset).where(Transaction.id==tid,Dataset.org_id==user.org_id))
        if value is None:
            raise HTTPException(404,'Record not found')
        return value
    source=transaction(body.source_transaction_id)
    candidates=[transaction(tid) for tid in body.target_transaction_ids]
    # Only server-produced artifacts can be loaded; there is no serialized-model upload API.
    model=pickle.loads(artifact.artifact)
    scores=model.predict_proba([features(source,t) for t in candidates])[:,1]
    ranked=[{'transaction_id':t.id,'ranking_score':float(score),'calibrated_probability':False,
        'deterministic_eligible':compatible(source,t,Rules()) and source.amount==t.amount,'match_accepted':False}
        for t,score in zip(candidates,scores)]
    return {'version':artifact.version,'candidates':sorted(ranked,key=lambda r:r['ranking_score'],reverse=True)}
