"""Offline scoring against explicitly independently corroborated references.

No model is trained. Corroboration is a provenance assertion supplied by a curator;
source strings are validated, never fetched or treated as proof by themselves.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.review_schema import ASSESSMENTS, iso_time, safe_source

LABELS = tuple(label for label in ASSESSMENTS if label != 'unresolved')
REFERENCE_TYPES = {'field_report', 'independent_imagery', 'official_incident_record'}


def _identity(row):
    if not isinstance(row, dict):
        raise ValueError('Expected record object')
    for key in ('eventId', 'siteId'):
        if not isinstance(row.get(key), str) or not row[key].strip() or len(row[key]) > 200:
            raise ValueError('Expected bounded eventId and siteId')
    iso_time(row.get('observedAt'))
    return row['eventId']


def _reference_reason(row):
    if row.get('independentlyCorroborated') is not True:
        return 'unverified_reference'
    if row.get('referenceType') not in REFERENCE_TYPES:
        return 'non_independent_reference_type'
    if row.get('label') not in LABELS:
        return 'unresolved_or_invalid_reference_label'
    sources = row.get('supportingSources')
    if not isinstance(sources, list) or not 1 <= len(sources) <= 8 or not all(map(safe_source, sources)):
        return 'missing_or_invalid_corroboration_sources'
    if not isinstance(row.get('verifiedBy'), str) or not row['verifiedBy'].strip() or len(row['verifiedBy']) > 200:
        return 'missing_independent_verifier'
    try:
        if iso_time(row.get('verifiedAt')) < iso_time(row['observedAt']):
            return 'verification_precedes_observation'
    except (ValueError, TypeError):
        return 'invalid_verification_time'
    return None


def evaluate_independent(predictions, references, *, training_records=None, minimum_labels=1):
    """Score fixed predictions and report omitted references and split leakage.

    training_records describes the supplied predictor's training observations;
    it is never used to train. Missing predictions count as false negatives.
    """
    if type(minimum_labels) is not int or minimum_labels < 1:
        raise ValueError('minimum_labels must be a positive integer')
    for rows in (predictions, references, training_records if training_records is not None else []):
        if not isinstance(rows, list) or len(rows) > 100000:
            raise ValueError('Expected arrays of at most 100,000 records')
    predicted = {}
    for row in predictions:
        key = _identity(row)
        if key in predicted:
            raise ValueError('Duplicate prediction eventId')
        if row.get('label') not in ASSESSMENTS:
            raise ValueError('Invalid prediction label')
        predicted[key] = row
    accepted, excluded, seen = {}, [], set()
    for row in references:
        key = _identity(row)
        if key in seen:
            raise ValueError('Duplicate reference eventId')
        seen.add(key)
        reason = _reference_reason(row)
        if reason:
            excluded.append({'eventId': key, 'reason': reason})
        else:
            accepted[key] = row

    leakage = {'checked': bool(training_records), 'siteOverlap': [], 'eventOverlap': [],
               'temporalOverlap': [], 'invalidTrainingRecords': []}
    if training_records is not None:
        train_sites, train_events, times = set(), set(), []
        for index, row in enumerate(training_records):
            try:
                key = _identity(row)
                train_events.add(key); train_sites.add(row['siteId']); times.append(iso_time(row['observedAt']))
            except (ValueError, TypeError) as error:
                leakage['invalidTrainingRecords'].append({'index': index, 'error': str(error)})
        leakage['siteOverlap'] = sorted(train_sites & {r['siteId'] for r in accepted.values()})
        leakage['eventOverlap'] = sorted(train_events & accepted.keys())
        if times:
            cutoff = max(times)
            leakage['temporalOverlap'] = sorted(key for key, row in accepted.items() if iso_time(row['observedAt']) <= cutoff)
    leakage['detected'] = any(leakage[key] for key in ('siteOverlap', 'eventOverlap', 'temporalOverlap', 'invalidTrainingRecords'))
    leakage['explanation'] = ('No model is trained. Supplied training provenance is checked for shared events/sites and evaluation observations at or before the latest training observation.'
                              if training_records else
                              'No model is trained. No nonempty training provenance supplied; ML temporal/site separation is unknown. For an untrained heuristic, a training holdout is not applicable and is not validated.')

    columns = (*LABELS, 'unresolved', 'missing_prediction', 'identity_mismatch')
    matrix = {label: {column: 0 for column in columns} for label in LABELS}
    errors = []
    for key, reference in accepted.items():
        prediction = predicted.get(key)
        actual = reference['label']
        predicted_label = prediction['label'] if prediction else 'missing_prediction'
        if prediction and (prediction['siteId'] != reference['siteId'] or
                           iso_time(prediction['observedAt']) != iso_time(reference['observedAt'])):
            predicted_label = 'identity_mismatch'
        matrix[actual][predicted_label] += 1
        if predicted_label != actual:
            errors.append({'eventId': key, 'siteId': reference['siteId'], 'expected': actual, 'predicted': predicted_label})
    metrics, insufficient = {}, []
    for label in LABELS:
        tp = matrix[label][label]
        support = sum(matrix[label].values())
        prediction_count = sum(matrix[actual][label] for actual in LABELS)
        metrics[label] = {'precision': tp / prediction_count if prediction_count else None,
                          'recall': tp / support if support else None, 'support': support}
        if support < minimum_labels:
            insufficient.append({'label': label, 'support': support, 'required': minimum_labels})
    return {'evaluation': 'independent_reference_predictions', 'trained': False,
            'acceptedReferences': len(accepted), 'excludedReferences': excluded,
            'unscoredPredictions': sorted(predicted.keys() - accepted.keys()),
            'precision': {label: value['precision'] for label, value in metrics.items()},
            'recall': {label: value['recall'] for label, value in metrics.items()},
            'perClass': metrics, 'confusion': matrix, 'errors': errors,
            'insufficientLabels': insufficient, 'splitLeakage': leakage,
            'separationValidated': bool(accepted) and leakage['checked'] and not leakage['detected'],
            'coverageSufficient': not insufficient,
            'validIndependentHoldout': bool(accepted) and leakage['checked'] and not leakage['detected'] and not insufficient,
            'caveat': 'Only explicit independent corroboration assertions are scored. The utility cannot authenticate supplied evidence. Reviewed status, analyst annotations and rule agreement are not verified truth. Metrics cover accepted references only; absent classes have undefined recall.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path, help='JSON with predictions, references and optional trainingRecords')
    parser.add_argument('--minimum-labels', type=int, default=1)
    args = parser.parse_args()
    try:
        data = json.loads(args.input.read_text(encoding='utf-8'))
        result = evaluate_independent(data['predictions'], data['references'],
                                      training_records=data.get('trainingRecords'), minimum_labels=args.minimum_labels)
    except (ValueError, TypeError, KeyError, OSError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
