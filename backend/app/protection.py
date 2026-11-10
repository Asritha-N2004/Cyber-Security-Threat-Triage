"""Optional authenticated encryption for retained files and masking helpers."""
import base64
import os


def key_material(value):
    # Accept standard and URL-safe encodings without changing key bytes.
    material=base64.b64decode(value,altchars=b'-_',validate=True)
    if len(material)!=32:
        raise ValueError('FILE_ENCRYPTION_KEY must encode exactly 32 bytes')
    return material


def protect(content):
    key=os.getenv('FILE_ENCRYPTION_KEY')
    if not key:
        if os.getenv('REQUIRE_FILE_ENCRYPTION','false').lower()=='true':
            raise ValueError('File encryption key is required by deployment policy')
        return content
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    material=key_material(key)
    nonce=os.urandom(12)
    return b'RCENC1'+nonce+AESGCM(material).encrypt(nonce,content,b'reconcile-import-v1')


def unprotect(content):
    if not content.startswith(b'RCENC1'):
        return content
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    key=os.getenv('FILE_ENCRYPTION_KEY')
    if not key:
        raise ValueError('File encryption key is unavailable')
    return AESGCM(key_material(key)).decrypt(content[6:18],content[18:],b'reconcile-import-v1')


def masked(record):
    result=dict(record)
    for key in ('account','counterparty'):
        value=str(result.get(key,''))
        result[key]='***'+value[-4:] if value else ''
    result.pop('original',None)
    result.pop('normalization',None)
    return result
