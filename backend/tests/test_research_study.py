import importlib.util
from pathlib import Path


def test_six_arm_study_has_measured_metrics_and_no_fabricated_acceptance():
    path=Path(__file__).resolve().parents[2]/'evaluation'/'study.py'
    spec=importlib.util.spec_from_file_location('study',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result=module.study(seeds=(42,),count=12)
    assert len(result['arms'])==6
    for arm in result['arms'].values():
        run=arm['runs'][0]
        assert run['human_acceptance_rate'] is None
        assert 0<=run['exception_classification_accuracy']<=1
        assert run['real_resolution_rate']==0
    assert result['arms']['B_fuzzy']['mean_match_recall']>result['arms']['A_rules']['mean_match_recall']
