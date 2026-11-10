"""Local operator credential renewal; no remote unauthenticated identity endpoint."""
import argparse
import json
import secrets
from datetime import timedelta
from pathlib import Path
from sqlalchemy import select
from .database import SessionLocal,User,now
from .models_extended import TokenGrant
from .security import token_hash


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--name',required=True)
    parser.add_argument('--org-id',required=True)
    args=parser.parse_args()
    with SessionLocal() as db:
        user=db.scalar(select(User).where(User.name==args.name,User.org_id==args.org_id))
        if not user:
            parser.error('Identity not found in the requested organization')
        for old in db.scalars(select(TokenGrant).where(TokenGrant.user_id==user.id)):
            old.revoked=True
        token=secrets.token_urlsafe(48)
        db.add(TokenGrant(user_id=user.id,token_hash=token_hash(token),expires_at=now()+timedelta(hours=8)))
        path=Path('.local/credentials.json')
        values=json.loads(path.read_text()) if path.exists() else {}
        values[args.name]=token
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(values,indent=2),encoding='utf-8')
        db.commit()
    print('Eight-hour credential written to the private local credentials file.')


if __name__=='__main__':
    main()
