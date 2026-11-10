import os
from alembic import context
from sqlalchemy import create_engine
from app.database import Base,normalize_database_url

url = normalize_database_url(os.getenv('DATABASE_URL', context.config.get_main_option('sqlalchemy.url')))
with create_engine(url).connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()
