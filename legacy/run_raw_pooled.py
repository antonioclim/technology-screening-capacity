#!/usr/bin/env python3
"""Reproduce pooled capacity and deletion results from the pinned FAT ZIP.

Only the original microdata ZIP is a data input. Code and frozen protocols are
software inputs. Derived state summaries stay in the user-chosen local output.
No archived X04, X06, X07 or X10 table is required by this execution route.
"""
from __future__ import annotations
import argparse
import csv
from fractions import Fraction as F
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import sys

import numpy as np
import pandas as pd

RAW_SHA = '6d77d3ffb9dcef2ca4534e1c438ddd2e0b357eb852e6c5b48aa5fa6c3cbe2f0e'
MEMBER_SHA = 'f61a2c6e09f4763818ae1d4db8b330e97bffd8bb0824c2d833b79d728152bd17'
FROZEN_SHA = '0ac2f1d60dbafcdc5edd763e682759732f326cceb66639cdf50647d34987a402'
H1_SHA = 'f3d6536f0de1ccd09cb18f3e73a4a7071eeada16a3423cbfca0572285ae6fa72'
PRIMARY_FP = '59d49ff980b98de612b32d721ed35dc80a92fb3175be2e1ddfcf8d36168c6f76'
BROAD_FP = '49f35215e472132af24dcb2f80388ca2e23edb81613aaa11df8b7d9f7ad6f1c2'
QUANTILES = ('0.10', '0.15', '0.20', '0.25', '0.30')
BOUNDARIES = (('integrated_planning', 4, 'Integrated planning'),
              ('specialised_planning', 3, 'Specialised planning'),
              ('digitally_enabled_planning', 1, 'Digitally enabled planning'))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def load_module(path, name, expected_sha=None):
    path = Path(path)
    require(path.is_file(), 'Missing Python software input: ' + str(path))
    if expected_sha:
        require(digest(path) == expected_sha, 'Software SHA-256 mismatch: ' + path.name)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def write_csv(path, rows):
    require(bool(rows), 'Cannot write an empty derived table')
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def event_labels(frame, frozen, quantile):
    """Use frozen sorted sample, weights, floating threshold and inclusive ties."""
    labels = np.zeros(len(frame), dtype=bool)
    for _, indices in frame.groupby('country', sort=True).groups.items():
        pos = np.asarray(list(indices), dtype=int)
        values = frame.loc[pos, 'Y_PRIMARY_RAW'].to_numpy(float)
        weights = frame.loc[pos, 'W_PRIMARY_SOURCE_MEAN1'].to_numpy(float)
        threshold = frozen.weighted_quantile_threshold(values, weights, float(quantile))
        labels[pos] = values <= threshold
    return labels


def derive_pooled(frame, frozen):
    """Keep the frozen labels; use exact fractions for subsequent accounting."""
    weights = [F(str(v)) for v in frame['W_PRIMARY_SOURCE_MEAN1'].to_numpy(float)]
    state = frame['most_state'].to_numpy(int)
    total = sum(weights)
    mass = [sum((w for w, s in zip(weights, state) if s == k), F(0)) / total for k in range(1, 6)]
    x04, quantile_rows, primary_events, primary_labels = {}, [], None, None
    for q in QUANTILES:
        labels = event_labels(frame, frozen, q)
        events = [sum((w for w, s, e in zip(weights, state, labels) if s == k and e), F(0)) / total for k in range(1, 6)]
        prevalence = sum(events)
        if F(q) == F('.20'):
            primary_events, primary_labels = events, labels
        for cut in (1, 3, 4):
            selected, cases = sum(mass[:cut]), sum(events[:cut])
            row = {'low_performance_quantile': q, 'cut_state': cut + 1,
                   'target_share': selected, 'low_performance_share': prevalence,
                   'recall': cases / prevalence, 'positive_predictive_value': cases / selected}
            x04[F(q), cut] = row
            quantile_rows.append({k: (str(v) if isinstance(v, F) else v) for k, v in row.items()})
    state_rows = [{'state': k, 'n': int((state == k).sum()),
                   'n_cases': int(((state == k) & primary_labels).sum()),
                   'weighted_mass_fraction': str(mass[k - 1]),
                   'weighted_case_mass_fraction': str(primary_events[k - 1])} for k in range(1, 6)]
    return mass, primary_events, x04, state_rows, quantile_rows


def derive_deletion(frame, frozen):
    """Retain R3's source omission, reweighting and confusion semantics."""
    values = {name: [] for name, _, _ in BOUNDARIES}
    for omitted in sorted(frame.country.unique()):
        sub = frame.loc[frame.country.ne(omitted)].copy().reset_index(drop=True)
        sub['W_PRIMARY_SOURCE_MEAN1'] = sub.base_wt.astype(float) / sub.groupby('country').base_wt.transform('mean')
        truth = event_labels(sub, frozen, '.20')
        weights = sub.W_PRIMARY_SOURCE_MEAN1.to_numpy(float)
        for name, _, _ in BOUNDARIES:
            values[name].append(frozen.classification_metrics(truth, sub[name].eq(0).to_numpy(), weights))
    rows, corners = [], {}
    for name, _, label in BOUNDARIES:
        entries = values[name]
        row = {'extension_id': 'X10_RAW_RECONSTRUCTION', 'boundary': name,
               'label': label, 'omissions': len(entries)}
        for metric in ('target_share', 'recall', 'specificity', 'balanced_error_rate'):
            array = [item[metric] for item in entries]
            for suffix, value in (('min', min(array)), ('median', float(np.median(array))), ('max', max(array))):
                row[metric + '_' + suffix] = value
        rows.append(row)
        corners[name] = ((F(str(row['target_share_max'])), F(str(row['recall_min']))),
                         (F(str(row['target_share_min'])), F(str(row['recall_max']))))
    return rows, corners


def run(microdata, frozen_module, protocol, capacity_core, deletion_core, output):
    output = Path(output)
    require(not output.exists() or (output.is_dir() and not any(output.iterdir())),
            'Output must be a new or empty local directory')
    require(digest(microdata) == RAW_SHA, 'Microdata container SHA-256 mismatch')
    require(digest(protocol) == H1_SHA, 'H1 source/sample protocol SHA-256 mismatch')
    h1 = json.loads(Path(protocol).read_text())
    frozen = load_module(frozen_module, 'papere_pooled_raw_frozen', FROZEN_SHA)
    core = load_module(capacity_core, 'papere_pooled_raw_capacity')
    deletion = load_module(deletion_core, 'papere_pooled_raw_deletion')
    require(frozen.EXPECTED_CONTAINER_SHA256 == RAW_SHA and frozen.EXPECTED_MEMBER_SHA256 == MEMBER_SHA,
            'Frozen raw identity constants disagree')
    raw = frozen.load_real_microdata(Path(microdata))
    prepared = frozen.prepare_full_frame(raw)
    primary = frozen.build_sample(prepared, 'PRIMARY_S60_N200')
    broad = frozen.build_sample(prepared, 'BROAD_AVAILABLE_N20')
    require(len(primary) == 14412 and frozen.sample_fingerprint(primary) == PRIMARY_FP,
            'Primary sample identity mismatch')
    require(len(broad) == 14818 and frozen.sample_fingerprint(broad) == BROAD_FP,
            'Broad sample identity mismatch')
    require(set(primary.country) == set(h1['primary_sources']), 'Primary source list mismatch')
    require(set(broad.country) == set(h1['primary_sources'] + h1['excluded_primary_targets']),
            'Broad source list mismatch')
    primary = frozen.add_outcomes_and_weights(primary)
    mass, events, x04, state_rows, quantile_rows = derive_pooled(primary, frozen)
    deletion_rows, corners = derive_deletion(primary, frozen)
    provenance = {
        'microdata_accessed': True, 'raw_container_sha256': RAW_SHA,
        'raw_member': frozen.EXPECTED_MEMBER, 'raw_member_sha256': MEMBER_SHA,
        'primary_sample_fingerprint': PRIMARY_FP, 'broad_sample_fingerprint': BROAD_FP,
        'primary_n': len(primary), 'broad_n': len(broad),
        'input_sha256': {Path(microdata).name: RAW_SHA},
        'software_sha256': {'frozen_e4': digest(frozen_module), 'capacity_core': digest(capacity_core),
                            'deletion_core': digest(deletion_core), 'raw_adapter': digest(__file__)},
        'source_protocol_sha256': H1_SHA,
        'data_route': 'Direct pinned raw ZIP; no archived aggregate CSV is read',
        'quantiles': list(QUANTILES), 'weights': 'base_wt normalised to mean one within each eligible source',
        'event_rule': 'Frozen stable ascending weighted threshold, first cumulative mass reaching q, inclusive ties',
        'allocation': 'One quota on the pooled eligible population; distinct from per-source transfer quotas',
        'runtime': {'python': platform.python_version(), 'numpy': np.__version__, 'pandas': pd.__version__},
    }
    output.mkdir(parents=True, exist_ok=True)
    derived = output / 'locally_derived_inputs'
    derived.mkdir()
    write_csv(derived / 'pooled_state_events.csv', state_rows)
    write_csv(derived / 'pooled_event_quantile_classification.csv', quantile_rows)
    write_csv(derived / 'source_deletion_ranges.csv', deletion_rows)
    core.analyse(mass, events, x04, output / 'capacity', provenance)
    summary = json.loads((output / 'capacity/result_summary.json').read_text())
    grid_points = summary['coverage_grid_points']
    expected_rows = {'capacity_curves.csv': 16 * grid_points, 'illustrative_quotas.csv': 24,
                     'best_binary_intervals.csv': 4, 'adjacent_merges.csv': 4,
                     'compression_profiles.csv': 16, 'list_composition.csv': 120,
                     'list_composition_distance.csv': 24, 'outcome_sensitivity.csv': 5 * grid_points}
    for name, count in expected_rows.items():
        with (output / 'capacity' / name).open(newline='', encoding='utf-8') as handle:
            require(len(list(csv.DictReader(handle))) == count, 'Incomplete output readback: ' + name)
    quota_rows, comparisons = deletion.compute(corners)
    deletion.qa(corners, comparisons)
    deletion_out = output / 'deletion'
    deletion_out.mkdir()
    write_csv(deletion_out / 'X10_FIXED_CAPACITY_RECALL_BOUNDS.csv', quota_rows)
    deletion_receipt = {
        'scope': 'Conservative deterministic recall bounds for raw-reconstructed retained mixtures',
        'microdata_accessed': True, 'retained_mixtures': 12, 'provenance': provenance,
        'comparisons': comparisons,
        'qa': {'status': 'PASS', 'quota_grid_points_for_corner_dominance': 101,
               'parameter_grid_per_corner_check': [6, 6], 'quota_grid_points_for_strict_intervals': 1001},
        'unresolved': 'Outside strict intervals the independent ranges do not establish ordering',
    }
    (deletion_out / 'X10_FIXED_CAPACITY_QA.json').write_text(json.dumps(deletion_receipt, indent=2) + '\n')
    (output / 'RAW_POOLED_RECEIPT.json').write_text(json.dumps({'status': 'PASS', **provenance,
        'derived_input_sha256': {p.name: digest(p) for p in sorted(derived.glob('*.csv'))},
        'capacity_output_files': sorted(p.name for p in (output / 'capacity').iterdir()),
        'capacity_csv_row_counts': expected_rows,
        'deletion_qa': 'PASS',
        'redistribution': 'Outputs are generated locally. This run grants no data redistribution rights.'}, indent=2) + '\n')
    # Finish local writes before returning; the caller can independently hash and
    # verify the directory again after a filesystem copy or archive round trip.
    for path in output.rglob('*'):
        if path.is_file():
            with path.open('rb') as handle:
                os.fsync(handle.fileno())
    return provenance


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--microdata', type=Path, required=True)
    p.add_argument('--frozen-module', type=Path, required=True)
    p.add_argument('--protocol', type=Path, required=True)
    p.add_argument('--capacity-core', type=Path, default=Path(__file__).with_name('pooled_capacity_core.py'))
    p.add_argument('--deletion-core', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    run(a.microdata, a.frozen_module, a.protocol, a.capacity_core, a.deletion_core, a.output)
    print(json.dumps({'status': 'PASS', 'output': str(a.output), 'microdata_accessed': True}))


if __name__ == '__main__':
    main()
