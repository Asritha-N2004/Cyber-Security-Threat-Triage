import csv
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.synthetic import generate

destination=Path(__file__).resolve().parents[1]/'data'/'synthetic'
destination.mkdir(exist_ok=True,parents=True)
bank,ledger=generate()
for name,records in [('bank',bank),('ledger',ledger)]:
    keys=sorted(set().union(*(r.keys() for r in records)))
    with (destination/f'synthetic_{name}.csv').open('w',newline='',encoding='utf-8') as file:
        writer=csv.DictWriter(file,fieldnames=keys)
        writer.writeheader()
        writer.writerows(records)
(destination/'ground_truth.json').write_text(json.dumps({'synthetic':True,'seed':42,'exceptions':{'B0001':'amount_mismatch','B0002':'currency_mismatch','B0003':'timing_difference','B0004':'account_mismatch','B0005':'unmatched_source','FEE':'unmatched_source','MISSING':'unmatched_source'},'split':{'SETTLE':['SPLIT-0','SPLIT-1']}},indent=2))
print('Generated labeled synthetic CSV fixtures; ground truth is stored separately.')
