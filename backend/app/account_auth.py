"""Simple account signup and revocable cookie sessions."""
import hashlib
import hmac
import secrets
from datetime import timedelta
from urllib.parse import urlsplit
from fastapi import APIRouter,Depends,HTTPException,Request,Response
from pydantic import BaseModel,Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .database import Organization,User,get_db,now
from .models_extended import LoginAccount,TokenGrant
from .security import token_hash

router=APIRouter(prefix='/api/v1/auth')
COOKIE='reconcile_session'
SESSION_SECONDS=7*24*3600


class Credentials(BaseModel):
    username:str=Field(min_length=1,max_length=80)
    password:str=Field(min_length=1,max_length=128)


def password_hash(password,salt=None):
    salt=salt or secrets.token_hex(16)
    digest=hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()
    return f'scrypt${salt}${digest}'


def verify_password(password,stored):
    _,salt,_=stored.split('$')
    return hmac.compare_digest(password_hash(password,salt),stored)


def check_origin(request):
    origin=request.headers.get('origin')
    if origin and urlsplit(origin).netloc!=request.url.netloc:
        # The local Vite development proxy uses a separate loopback port.
        if not (request.url.hostname in ('127.0.0.1','localhost') and origin in ('http://localhost:5173','http://127.0.0.1:5173')):
            raise HTTPException(403,'Please sign in from this website.')


def issue_session(request,response,db,user):
    token=secrets.token_urlsafe(48)
    db.add(TokenGrant(user_id=user.id,token_hash=token_hash(token),expires_at=now()+timedelta(seconds=SESSION_SECONDS)))
    db.commit()
    response.set_cookie(COOKIE,token,max_age=SESSION_SECONDS,httponly=True,secure=request.url.scheme=='https',samesite='lax',path='/')
    response.headers['Cache-Control']='no-store'
    return {'id':user.id,'name':user.name,'role':user.role}


@router.post('/register',status_code=201)
def register(body:Credentials,request:Request,response:Response,db:Session=Depends(get_db)):
    check_origin(request)
    username=body.username.strip()
    if not username:
        raise HTTPException(422,'Enter a username.')
    if len(body.password)<6:
        raise HTTPException(422,'Use at least 6 characters for your password.')
    account=LoginAccount(username_key=username.casefold(),password_hash=password_hash(body.password))
    org=Organization(name=f"{username}'s workspace")
    db.add(org)
    db.flush()
    user=User(org_id=org.id,name=username,role='admin',token_hash=token_hash(secrets.token_urlsafe(48)))
    db.add(user)
    db.flush()
    account.user_id=user.id
    db.add(account)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409,'That username is already taken. Try another.')
    return issue_session(request,response,db,user)


@router.post('/login')
def login(body:Credentials,request:Request,response:Response,db:Session=Depends(get_db)):
    check_origin(request)
    account=db.scalar(select(LoginAccount).where(LoginAccount.username_key==body.username.strip().casefold()))
    # Spend the same password-hashing work for unknown usernames.
    stored=account.password_hash if account else password_hash('unavailable-account','00'*16)
    valid=verify_password(body.password,stored)
    if not account or not valid:
        raise HTTPException(401,'Username or password is incorrect.')
    return issue_session(request,response,db,db.get(User,account.user_id))


@router.post('/logout')
def logout(request:Request,response:Response,db:Session=Depends(get_db)):
    check_origin(request)
    value=request.cookies.get(COOKIE)
    if value:
        grant=db.scalar(select(TokenGrant).where(TokenGrant.token_hash==token_hash(value)))
        if grant:
            grant.revoked=True
            db.commit()
    response.delete_cookie(COOKIE,path='/')
    return {'signed_out':True}
