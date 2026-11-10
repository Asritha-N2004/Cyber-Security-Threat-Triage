"""Operator-configured read-only integrations. User data cannot choose arbitrary URLs or SQL."""
import json
import os
import urllib.request
from sqlalchemy import create_engine,text
from .ingestion import MAX_BYTES


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,request,fp,code,msg,headers,newurl):
        raise ValueError('Integration redirects are disabled')


def fetch_http():
    url=os.environ.get('FINANCIAL_SOURCE_URL','')
    if not url.startswith('https://'):
        raise ValueError('Operator must configure an HTTPS FINANCIAL_SOURCE_URL')
    headers={'Accept':'application/json'}
    token=os.environ.get('FINANCIAL_SOURCE_TOKEN')
    if token:
        headers['Authorization']='Bearer '+token
    opener=urllib.request.build_opener(NoRedirect())
    with opener.open(urllib.request.Request(url,headers=headers),timeout=15) as response:
        content=response.read(MAX_BYTES+1)
    if len(content)>MAX_BYTES:
        raise ValueError('Integration response exceeds 10 MB')
    rows=json.loads(content,parse_float=str,parse_constant=str)
    if not isinstance(rows,list) or not all(isinstance(row,dict) for row in rows):
        raise ValueError('Integration must return an array of record objects')
    return rows


def fetch_database():
    url=os.environ.get('FINANCIAL_SOURCE_DATABASE_URL')
    if not url:
        raise ValueError('Operator must configure FINANCIAL_SOURCE_DATABASE_URL')
    # Fixed canonical export view; no user-provided SQL or table names.
    source=create_engine(url)
    try:
        with source.connect() as connection:
            if source.dialect.name=='postgresql':
                connection.execute(text('SET TRANSACTION READ ONLY'))
            elif source.dialect.name=='sqlite':
                connection.execute(text('PRAGMA query_only=ON'))
            else:
                raise ValueError('Read-only imports support PostgreSQL and SQLite')
            return [dict(row) for row in connection.execute(text('SELECT * FROM reconciliation_export LIMIT 10001')).mappings()]
    finally:
        source.dispose()
