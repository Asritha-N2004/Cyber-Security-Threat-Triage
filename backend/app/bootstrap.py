"""Create local identities. Tokens are written to a private ignored file, never logs."""
import json
import secrets
from pathlib import Path
from sqlalchemy import select
from .database import Organization, User, SessionLocal
from .security import token_hash
from .models_extended import TokenGrant
from .database import now
from datetime import timedelta


def main():
    path = Path('.local/credentials.json')
    if path.exists():
        credentials=json.loads(path.read_text())
        if 'administrator' not in credentials:
            with SessionLocal() as db:
                reference=credentials.get('analyst','')
                grant=db.scalar(select(TokenGrant).where(TokenGrant.token_hash==token_hash(reference)))
                analyst=db.get(User,grant.user_id) if grant else db.scalar(select(User).where(User.token_hash==token_hash(reference)))
                if analyst is None:
                    raise ValueError('Cannot identify the existing organization from local credentials')
                token=secrets.token_urlsafe(36)
                admin=User(org_id=analyst.org_id,name='administrator',role='admin',token_hash=token_hash(secrets.token_urlsafe(36)))
                db.add(admin)
                db.flush()
                db.add(TokenGrant(user_id=admin.id,token_hash=token_hash(token),expires_at=now()+timedelta(hours=8)))
                credentials['administrator']=token
                path.write_text(json.dumps(credentials,indent=2),encoding='utf-8')
                db.commit()
        print('Local credentials exist; an administrator identity is available.')
        return
    with SessionLocal() as db:
        org = Organization(name='Synthetic Research Organization')
        db.add(org)
        db.flush()
        credentials = {}
        for name, role in [('analyst', 'analyst'), ('checker', 'approver'), ('second-checker', 'approver'),('administrator','admin')]:
            token = secrets.token_urlsafe(36)
            user=User(org_id=org.id,name=name,role=role,token_hash=token_hash(secrets.token_urlsafe(36)))
            db.add(user)
            db.flush()
            db.add(TokenGrant(user_id=user.id,token_hash=token_hash(token),expires_at=now()+timedelta(hours=8)))
            credentials[name] = token
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(credentials, indent=2), encoding='utf-8')
        db.commit()
    print('Local identities created. Read backend/.local/credentials.json and paste a token into the app. Keep this file private.')


if __name__ == '__main__':
    main()
