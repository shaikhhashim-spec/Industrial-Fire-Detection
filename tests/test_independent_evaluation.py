import json
import subprocess
import sys

import pytest

from src.ml.independent_evaluation import evaluate_independent


def prediction(event='A', label='industrial_heat', **overrides):
    return {'eventId': event, 'siteId': 'site-' + event, 'observedAt': '2026-10-03T00:00:00Z', 'label': label, **overrides}


def reference(event='A', label='industrial_heat', **overrides):
    return {**prediction(event, label), 'independentlyCorroborated': True,
            'referenceType': 'field_report', 'supportingSources': ['Field visit record 123'],
            'verifiedBy': 'independent-inspector', 'verifiedAt': '2026-10-04T00:00:00Z', **overrides}


def test_precision_recall_confusion_and_missing_prediction_false_negatives():
    predictions = [prediction('A'), prediction('B'), prediction('C', 'unresolved')]
    references = [reference('A'), reference('B', 'suspected_fire'), reference('C', 'suspected_fire'), reference('D', 'industrial_heat')]
    result = evaluate_independent(predictions, references)
    assert result['precision']['industrial_heat'] == .5
    assert result['recall']['industrial_heat'] == .5
    assert result['recall']['suspected_fire'] == 0
    assert result['confusion']['suspected_fire']['industrial_heat'] == 1
    assert result['confusion']['industrial_heat']['missing_prediction'] == 1
    assert len(result['errors']) == 3
    assert result['precision']['suspected_fire'] is None
    assert {row['label'] for row in result['insufficientLabels']} == {'agricultural_burning', 'false_positive'}
    assert 'accuracy' not in result and result['trained'] is False
    assert result['validIndependentHoldout'] is False
    assert 'unknown' in result['splitLeakage']['explanation']


@pytest.mark.parametrize('overrides,reason', [
    ({'independentlyCorroborated': False, 'status': 'reviewed'}, 'unverified_reference'),
    ({'independentlyCorroborated': 'true'}, 'unverified_reference'),
    ({'independentlyCorroborated': None}, 'unverified_reference'),
    ({'referenceType': 'rule_engine'}, 'non_independent_reference_type'),
    ({'referenceType': 'analyst_assessment'}, 'non_independent_reference_type'),
    ({'supportingSources': []}, 'missing_or_invalid_corroboration_sources'),
    ({'supportingSources': ['javascript:alert(1)']}, 'missing_or_invalid_corroboration_sources'),
    ({'verifiedBy': ''}, 'missing_independent_verifier'),
    ({'verifiedAt': '2026-10-02T00:00:00Z'}, 'verification_precedes_observation'),
    ({'verifiedAt': 'invalid'}, 'invalid_verification_time'),
    ({'label': 'unresolved'}, 'unresolved_or_invalid_reference_label'),
])
def test_unverified_or_nonindependent_references_are_explicitly_excluded(overrides, reason):
    result = evaluate_independent([prediction()], [reference(**overrides)])
    assert result['acceptedReferences'] == 0
    assert result['excludedReferences'] == [{'eventId': 'A', 'reason': reason}]
    assert result['unscoredPredictions'] == ['A']
    assert all(value is None for value in result['recall'].values())
    assert len(result['insufficientLabels']) == 4


def test_legacy_review_or_rule_label_cannot_supply_reference_truth():
    row = {**prediction(), 'status': 'reviewed', 'assessment': 'industrial_heat', 'supportingSources': ['report']}
    result = evaluate_independent([prediction()], [row])
    assert result['acceptedReferences'] == 0
    assert result['excludedReferences'][0]['reason'] == 'unverified_reference'


def test_site_event_and_temporal_leakage_reported_without_training():
    training = [prediction('A', observedAt='2026-10-01T00:00:00Z'),
                prediction('training', siteId='site-B', observedAt='2026-10-03T00:00:00Z')]
    result = evaluate_independent([prediction(), prediction('B')], [reference(), reference('B')], training_records=training)
    leakage = result['splitLeakage']
    assert leakage['siteOverlap'] == ['site-A', 'site-B']
    assert leakage['eventOverlap'] == ['A']
    assert leakage['temporalOverlap'] == ['A', 'B']
    assert leakage['detected'] and not result['validIndependentHoldout']
    assert result['trained'] is False


def test_separated_provenance_and_bad_provenance():
    train = [prediction('training', observedAt='2026-10-02T00:00:00Z')]
    result = evaluate_independent([prediction()], [reference()], training_records=train, minimum_labels=2)
    assert result['separationValidated']
    assert not result['validIndependentHoldout']
    assert not result['coverageSufficient']
    assert not result['splitLeakage']['detected']
    assert len(result['insufficientLabels']) == 4
    broken = evaluate_independent([prediction()], [reference()], training_records=[{'eventId': 'bad'}])
    assert broken['splitLeakage']['invalidTrainingRecords']
    assert not broken['validIndependentHoldout']


def test_empty_training_provenance_never_validates_ml_holdout():
    result = evaluate_independent([prediction()], [reference()], training_records=[])
    assert not result['splitLeakage']['checked']
    assert not result['separationValidated']
    assert not result['validIndependentHoldout']
    assert 'not applicable' in result['splitLeakage']['explanation']


def test_valid_holdout_requires_nonempty_provenance_and_all_class_support():
    labels = ['industrial_heat', 'suspected_fire', 'agricultural_burning', 'false_positive']
    predictions = [prediction(str(index), label) for index, label in enumerate(labels)]
    references = [reference(str(index), label) for index, label in enumerate(labels)]
    train = [prediction('train', observedAt='2026-09-01T00:00:00Z')]
    result = evaluate_independent(predictions, references, training_records=train)
    assert result['validIndependentHoldout'] and result['coverageSufficient']
    sparse = evaluate_independent(predictions, references, training_records=train, minimum_labels=2)
    assert sparse['separationValidated'] and not sparse['validIndependentHoldout']


def test_identity_mismatch_never_scores_matching_labels_as_correct():
    result = evaluate_independent([prediction(siteId='wrong-site')], [reference()])
    assert result['recall']['industrial_heat'] == 0
    assert result['errors'][0]['predicted'] == 'identity_mismatch'
    assert evaluate_independent([prediction(observedAt='2026-10-02T00:00:00Z')], [reference()])['errors']


def test_duplicate_ids_invalid_predictions_and_bound_inputs_rejected():
    for predictions, references in [([prediction(), prediction()], [reference()]),
                                    ([prediction()], [reference(), reference()]),
                                    ([prediction(label='verified')], [reference()]),
                                    ([prediction(observedAt='bad')], [reference()])]:
        with pytest.raises(ValueError):
            evaluate_independent(predictions, references)
    with pytest.raises(ValueError):
        evaluate_independent([], [], minimum_labels=0)


def test_offline_cli_outputs_report(tmp_path):
    path = tmp_path / 'evaluation.json'
    path.write_text(json.dumps({'predictions': [prediction()], 'references': [reference()]}), encoding='utf-8')
    run = subprocess.run([sys.executable, '-m', 'src.ml.independent_evaluation', str(path)], capture_output=True, text=True, check=True)
    result = json.loads(run.stdout)
    assert result['acceptedReferences'] == 1 and result['trained'] is False
