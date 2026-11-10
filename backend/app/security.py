import hashlib
import os
from fastapi import Depends, HTTPException,Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session
from .database import User, get_db
from .models_extended import TokenGrant
from datetime import datetime, timezone

bearer = HTTPBearer(auto_error=False)


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def local_demo_request(request:Request):
    if os.getenv('LOCAL_DEMO_MODE','false').lower()!='true' or not request.client:
        return False
    if request.client.host not in ('127.0.0.1','::1') or request.url.hostname not in ('127.0.0.1','localhost','::1'):
        return False
    origin=request.headers.get('origin')
    return not origin or origin in {f'http://{host}:{port}' for host in ('127.0.0.1','localhost','[::1]') for port in (5173,8000)}


def local_demo_users(db):
    org_id=os.getenv('LOCAL_DEMO_ORG_ID')
    if not org_id:
        raise HTTPException(503,'Local demo organization is not configured')
    return list(db.scalars(select(User).where(User.org_id==org_id).order_by(User.name)))


def default_demo_user(users):
    return next((u for u in users if u.name=='analyst'),users[0] if users else None)


def current_user(request:Request,credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)):
    session=request.cookies.get('reconcile_session')
    if session:
        grant=db.scalar(select(TokenGrant).where(TokenGrant.token_hash==token_hash(session),TokenGrant.revoked.is_(False)))
        if grant is None or grant.expires_at.replace(tzinfo=timezone.utc)<=datetime.now(timezone.utc):
            raise HTTPException(401,'Your session has expired. Please sign in again.')
        return db.get(User,grant.user_id)
    from .hosted_demo import enabled,users_for_request
    account_mode=os.getenv('ACCOUNT_LOGIN_MODE','false').lower()=='true'
    if enabled() and not account_mode:
        users=users_for_request(request,db)
        selected=request.headers.get('x-local-demo-user')
        user=next((u for u in users if u.id==selected),None) if selected else default_demo_user(users)
        if user is None:
            raise HTTPException(401,'Demo session is unavailable. Reload the dashboard to start a private demo workspace.')
        return user
    if local_demo_request(request) and not account_mode:
        users=local_demo_users(db)
        selected=request.headers.get('x-local-demo-user')
        user=next((u for u in users if u.id==selected),None) if selected else default_demo_user(users)
        if user is None:
            raise HTTPException(404,'Local demo identity is unavailable')
        return user
    if credentials is None:
        raise HTTPException(401, 'Bearer token required')
    user = db.scalar(select(User).where(User.token_hash == token_hash(credentials.credentials))) if os.getenv('ALLOW_LEGACY_TOKENS','false').lower()=='true' else None
    if user is None:
        grant=db.scalar(select(TokenGrant).where(TokenGrant.token_hash==token_hash(credentials.credentials),TokenGrant.revoked.is_(False)))
        if grant is None or grant.expires_at.replace(tzinfo=timezone.utc)<=datetime.now(timezone.utc):
            raise HTTPException(401, 'Invalid or expired token')
        user=db.get(User,grant.user_id)
    return user


def require(user, *roles):
    if user.role not in roles:
        raise HTTPException(403, 'Role not authorized')
