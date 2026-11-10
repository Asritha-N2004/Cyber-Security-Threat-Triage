from decimal import Decimal
from types import SimpleNamespace
import pytest
from app.ml import features, train_and_evaluate


def test_candidate_features_do_not_change_financial_inputs():
    a=SimpleNamespace(amount=Decimal('.30'),date='2026-01-01',reference='REF',description='PAYMENT',counterparty='ACME',currency='USD',account='CASH')
    b=SimpleNamespace(**(vars(a)|{'amount':Decimal('.31'),'currency':'EUR'}))
    assert features(a,b)[0] == .01
    assert features(a,b)[5] == 0
    assert a.amount == Decimal('.30')


@pytest.mark.parametrize('kind',['logistic','random_forest'])
def test_offline_ranker_holdout(kind):
    pytest.importorskip('sklearn')
    train_x=[[0,0,1,1,1,1,1],[100,20,0,0,0,0,0],[0,1,1,.9,1,1,1],[50,10,0,.1,0,1,0]]*10
    train_y=[1,0,1,0]*10
    model,metrics=train_and_evaluate(train_x,train_y,[[0,2,1,.95,1,1,1],[80,12,0,.2,0,0,1]],[1,0],kind)
    assert metrics['precision']==1 and metrics['recall']==1
    assert not metrics['calibrated']
