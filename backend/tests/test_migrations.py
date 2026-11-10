import os
from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError


def test_migrations_and_database_immutability(tmp_path, monkeypatch):
    url = f'sqlite:///{tmp_path / "migrated.db"}'
    monkeypatch.setenv('DATABASE_URL',url)
    command.upgrade(Config('alembic.ini'),'head')
    engine=create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO organizations (id,name) VALUES ('org','Test')"))
        connection.execute(text("INSERT INTO users (id,org_id,name,role,token_hash) VALUES ('user','org','Test','analyst','hash')"))
        connection.execute(text("INSERT INTO audit_logs (id,org_id,user_id,action,resource_id,detail,created_at) VALUES ('audit','org','user','test','resource','{}','2026-01-01')"))
    with engine.begin() as connection:
        with pytest.raises(IntegrityError,match='Append-only'):
            connection.execute(text("DELETE FROM audit_logs WHERE id='audit'"))
    engine.dispose()
