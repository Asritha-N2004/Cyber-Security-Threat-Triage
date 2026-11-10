import csv
import io
import json
import re
import zipfile
import os
import pycountry
from babel.numbers import get_currency_precision
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from decimal import Decimal, InvalidOperation
from openpyxl import load_workbook
from sqlalchemy.orm import Session
from .database import Dataset, Transaction, now
from .models_extended import CanonicalRecord

# Versioned package ISO registry; test/no-currency codes are deliberately excluded.
CURRENCY_PRECISION = {c.alpha_3:get_currency_precision(c.alpha_3) for c in pycountry.currencies if c.alpha_3 not in ('XXX','XTS')}
for currency,precision in json.loads(os.getenv('CURRENCY_PRECISION_OVERRIDES','{}')).items():
    if currency not in CURRENCY_PRECISION or type(precision) is not int or not 0<=precision<=6:
        raise ValueError('Currency precision overrides require registered ISO codes and 0–6 decimals')
    CURRENCY_PRECISION[currency]=precision
MAX_BYTES = 10 * 1024 * 1024


def money(value):
    if isinstance(value, bool):
        raise ValueError('Boolean is not money')
    try:
        result = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise ValueError('Invalid monetary value')
    if not result.is_finite() or abs(result) >= Decimal('100000000000000000'):
        raise ValueError('Monetary value out of range')
    return result


def normalized_text(value):
    return re.sub(r'\s+', ' ', str(value or '').strip()).upper()


def parse_date(value,source_timezone='UTC'):
    if isinstance(value, datetime):
        parsed=value
    elif isinstance(value,str) and ('T' in value or ' ' in value.strip()):
        parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
    else:
        return value.isoformat() if isinstance(value,date) else date.fromisoformat(str(value)).isoformat()
    if parsed.tzinfo is None:
        zone=ZoneInfo(source_timezone)
        if parsed.replace(tzinfo=zone,fold=0).utcoffset()!=parsed.replace(tzinfo=zone,fold=1).utcoffset():
            raise ValueError('Ambiguous or nonexistent local timestamp requires an explicit UTC offset')
        parsed=parsed.replace(tzinfo=zone)
    return parsed.astimezone(timezone.utc).date().isoformat()


def canonical_fields(raw, mapping, normalized,default_timezone='UTC'):
    record={mapping.get(k,k):v for k,v in raw.items()}
    fields={k:str(v) if isinstance(v,(date,datetime,Decimal)) else v for k,v in record.items()}
    for key in ('value_date','posting_date'):
        fields[key]=parse_date(record.get(key) or normalized['date'])
    source_timezone=str(record.get('timezone') or default_timezone)
    zone=ZoneInfo(source_timezone)
    timestamp=record.get('transaction_timestamp')
    if timestamp:
        parse_date(str(timestamp),source_timezone)
        parsed=datetime.fromisoformat(str(timestamp).replace('Z','+00:00'))
        if parsed.tzinfo is None:
            parsed=parsed.replace(tzinfo=zone)
        fields['transaction_timestamp_utc']=parsed.astimezone(timezone.utc).isoformat()
    fields['timezone']=source_timezone
    fields['source_system']=str(record.get('source_system') or '')
    fields['transaction_status']=str(record.get('transaction_status') or 'posted')
    fields['reconciliation_status']='unreconciled'
    fields['signed_amount']=str(normalized['amount'])
    fields['debit']=str(max(-normalized['amount'],Decimal(0)))
    fields['credit']=str(max(normalized['amount'],Decimal(0)))
    return fields


def read_file(filename, content):
    if len(content) > MAX_BYTES:
        raise ValueError('File exceeds 10 MB')
    ext = filename.rsplit('.', 1)[-1].lower()
    if ext == 'csv':
        reader = csv.DictReader(io.StringIO(content.decode('utf-8-sig')))
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError('CSV requires unique column headers')
        rows = list(reader)
        if any(None in record for record in rows):
            raise ValueError('CSV row contains more values than column headers')
        return rows
    if ext == 'json':
        rows = json.loads(content, parse_float=str, parse_constant=str)
        if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
            raise ValueError('JSON must be an array of objects')
        return rows
    if ext == 'xlsx':
        if not zipfile.is_zipfile(io.BytesIO(content)):
            raise ValueError('Invalid XLSX container')
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            if sum(i.file_size for i in archive.infolist()) > 50 * 1024 * 1024:
                raise ValueError('Expanded workbook exceeds 50 MB')
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=False)
        try:
            rows = workbook.active.iter_rows(values_only=True)
            headers = next(rows)
            if len(set(headers)) != len(headers):
                raise ValueError('Duplicate workbook headers')
            return [dict(zip(headers, row)) for row in rows if any(v is not None for v in row)]
        finally:
            workbook.close()
    raise ValueError('Supported formats: CSV, XLSX, JSON')


def normalize(raw, mapping,default_timezone='UTC'):
    record = {mapping.get(k, k): v for k, v in raw.items()}
    for field in ('transaction_id', 'date', 'currency', 'account'):
        if not str(record.get(field) or '').strip():
            raise ValueError(f'Missing required field: {field}')
    currency = normalized_text(record['currency'])
    if currency not in CURRENCY_PRECISION:
        raise ValueError(f'Unsupported currency: {currency}')
    if record.get('amount') not in (None, ''):
        amount = money(record['amount'])
        if any(record.get(k) not in (None, '') for k in ('debit', 'credit')):
            debit, credit = money(record.get('debit') or 0), money(record.get('credit') or 0)
            if min(debit, credit) < 0 or (debit and credit) or credit - debit != amount:
                raise ValueError('Signed amount conflicts with debit/credit')
    else:
        if all(record.get(k) in (None, '') for k in ('debit', 'credit')):
            raise ValueError('Amount or debit/credit required')
        debit, credit = money(record.get('debit') or 0), money(record.get('credit') or 0)
        if min(debit, credit) < 0 or (debit and credit):
            raise ValueError('Debit/credit direction invalid')
        amount = credit - debit
    quantum = Decimal(1).scaleb(-CURRENCY_PRECISION[currency])
    if amount != amount.quantize(quantum):
        raise ValueError('Excess currency precision; no silent rounding permitted')
    return {
        'external_id': str(record['transaction_id']).strip(), 'amount': amount,
        'currency': currency, 'account': normalized_text(record['account']),
        'date': parse_date(record['date'],str(record.get('timezone') or default_timezone)),
        'reference': normalized_text(record.get('reference') or record.get('payment_reference')),
        'description': normalized_text(record.get('description')),
        'counterparty': normalized_text(record.get('counterparty')),
    }


def ingest(db: Session, org_id, name, source, rows, mapping=None):
    if not rows or len(rows) > 10000:
        raise ValueError('Dataset must contain 1–10000 records')
    from .policies import ensure_policy
    default_timezone=ensure_policy(db,org_id).settings.get('source_timezone','UTC')
    dataset = Dataset(org_id=org_id, name=name[:120], source=source[:120], quality={})
    db.add(dataset)
    db.flush()
    errors, seen, accepted = [], set(), 0
    for index, raw in enumerate(rows, 2):
        original = json.loads(json.dumps(raw, default=str))
        try:
            normalized = normalize(raw, mapping or {},default_timezone)
            canonical = canonical_fields(raw,mapping or {},normalized,default_timezone)
            if not canonical['source_system']:
                canonical['source_system']=source
            if normalized['external_id'] in seen:
                raise ValueError('Duplicate transaction ID in dataset')
            seen.add(normalized['external_id'])
            transaction=Transaction(dataset_id=dataset.id, **normalized, original=original,
                normalization={'version': 'canonical-v1', 'timestamp': now().isoformat(),
                    'rule': 'ISO date; upper-case text; signed credit-minus-debit; exact currency precision',
                    'currency_precision':CURRENCY_PRECISION[normalized['currency']],
                    'source_timezone':default_timezone,
                    'normalized': {k: str(v) for k, v in normalized.items()}, 'mapping': mapping or {}, 'business': canonical})
            db.add(transaction)
            db.flush()
            db.add(CanonicalRecord(transaction_id=transaction.id,fields=canonical,transformations=[
                {'field':key,'original':str(raw.get(next((column for column,target in (mapping or {}).items() if target==key),key),'')),
                    'normalized':str(value),'rule':'canonical-v2','timestamp':now().isoformat(),'version':2} for key,value in ({**normalized,**canonical}).items()]))
            accepted += 1
        except (ValueError, TypeError, InvalidOperation, ZoneInfoNotFoundError) as exc:
            errors.append({'row': index, 'error': str(exc), 'original': original})
    dataset.quality = {'total': len(rows), 'accepted': accepted, 'rejected': len(errors),
        'score': round(accepted / len(rows) * 100, 2), 'errors': errors}
    db.flush()
    return dataset
