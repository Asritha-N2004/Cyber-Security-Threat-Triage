"""Anonymous hosted demos use a signed, HttpOnly cookie and an isolated tenant.

This mode is explicit and never points a public visitor at local/private records.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from sqlalchemy import select
from .database import Organization,User

COOKIE='reconcile_demo'
LIFETIME=86400


def enabled():
    return os.getenv('HOSTED_DEMO_MODE','false').lower()=='true'


def signing_key():
    value=os.getenv('HOSTED_DEMO_SECRET','')
    if len(value)<32:
        raise ValueError('Hosted demo requires a configured signing secret of at least 32 characters')
    return value.encode()


def decode_cookie(value):
    if not value:
        return None
    try:
        encoded,signature=value.split('.',1)
        expected=hmac.new(signing_key(),encoded.encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature,expected):
            return None
        data=json.loads(base64.urlsafe_b64decode(encoded+'='*(-len(encoded)%4)))
        return data['org'] if int(data['exp'])>time.time() else None
    except (ValueError,KeyError,TypeError):
        return None


def users_for_request(request,db,create=False,response=None):
    org_id=decode_cookie(request.cookies.get(COOKIE))
    users=list(db.scalars(select(User).where(User.org_id==org_id).order_by(User.name))) if org_id else []
    if not users and create:
        signing_key()  # Fail before creating records when deployment is misconfigured.
        organization=Organization(name='Private synthetic demo workspace')
        db.add(organization)
        db.flush()
        for name,role in [('analyst','analyst'),('checker','approver'),('second-checker','approver'),('administrator','admin')]:
            db.add(User(org_id=organization.id,name=name,role=role,token_hash=hashlib.sha256(secrets.token_bytes(48)).hexdigest()))
        db.flush()
        org_id=organization.id
        users=list(db.scalars(select(User).where(User.org_id==org_id).order_by(User.name)))
        encoded=base64.urlsafe_b64encode(json.dumps({'org':org_id,'exp':int(time.time())+LIFETIME},separators=(',',':')).encode()).decode().rstrip('=')
        signature=hmac.new(signing_key(),encoded.encode(),hashlib.sha256).hexdigest()
        response.set_cookie(COOKIE,encoded+'.'+signature,httponly=True,secure=True,samesite='lax',max_age=LIFETIME,path='/')
        db.commit()
    return users
