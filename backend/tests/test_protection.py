import base64
import os
import pytest
from app.protection import protect,unprotect,masked
from app.ingestion import normalize


def test_authenticated_file_encryption_and_masking(monkeypatch):
    monkeypatch.setenv('FILE_ENCRYPTION_KEY',base64.b64encode(os.urandom(32)).decode())
    encrypted=protect(b'sensitive raw financial upload')
    assert b'sensitive' not in encrypted
    assert unprotect(encrypted)==b'sensitive raw financial upload'
    monkeypatch.delenv('FILE_ENCRYPTION_KEY')
    with pytest.raises(ValueError):
        unprotect(encrypted)
    assert masked({'account':'12345678','counterparty':'Acme','original':{'secret':'x'}})=={'account':'***5678','counterparty':'***Acme'}


def test_urlsafe_encryption_encoding_preserves_key(monkeypatch):
    material=b'\xff'*32
    monkeypatch.setenv('FILE_ENCRYPTION_KEY',base64.urlsafe_b64encode(material).decode())
    encrypted=protect(b'synthetic demo upload')
    monkeypatch.setenv('FILE_ENCRYPTION_KEY',base64.b64encode(material).decode())
    assert unprotect(encrypted)==b'synthetic demo upload'


def test_iso_registry_precision_and_timezone_normalization():
    base={'transaction_id':'1','account':'cash','date':'2026-01-01T00:30:00+05:30','currency':'NOK','amount':'1.23'}
    assert normalize(base,{})['date']=='2025-12-31'
    assert normalize(base|{'currency':'KWD','amount':'1.234'},{})['amount']==__import__('decimal').Decimal('1.234')
    with pytest.raises(ValueError):
        normalize(base|{'currency':'JPY','amount':'1.1'}, {})
