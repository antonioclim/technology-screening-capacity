#!/usr/bin/env python3
"""Independently check the derived H7 table, upper envelopes and artwork."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import re
from xml.etree import ElementTree as XML
from zipfile import ZipFile

from PIL import Image

ROOT = Path(__file__).resolve().parent
PIN = 'f3dcd98ad052d42281bf25ee8c992cf46abf213a48e8de5ccceda93fc4466f86'
PLOT_NS = {'svg': 'http://www.w3.org/2000/svg'}
DRAW_NS = {'draw': 'urn:oasis:names:tc:opendocument:xmlns:drawing:1.0',
           'text': 'urn:oasis:names:tc:opendocument:xmlns:text:1.0'}
MENU = ('B', 'Band_0.1', 'Band_0.25', 'Band_0.5', 'Full', 'Selected')


def check(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline='', encoding='utf-8') as handle:
        return list(csv.DictReader(handle))


def close(observed: str, expected: Fraction) -> bool:
    return abs(Fraction(observed) - expected) <= Fraction('1e-36')


def upper_hull_gap(points: dict[str, tuple[Fraction, Fraction]]) -> Fraction:
    """Use the concave hull in (theta, capacity), independently of line enumeration."""
    selected_theta, selected_capacity = points['Selected']
    highest_at_share = {}
    for name, (share, capacity) in points.items():
        if name != 'Selected' and (share not in highest_at_share or capacity > highest_at_share[share]):
            highest_at_share[share] = capacity
    hull = []
    for point in sorted(highest_at_share.items()):
        while len(hull) >= 2:
            a, b = hull[-2:]
            slope_rises = (b[1] - a[1]) * (point[0] - b[0]) <= (point[1] - b[1]) * (b[0] - a[0])
            if not slope_rises:
                break
            hull.pop()
        hull.append(point)
    check(hull[0] == (0, 0) and selected_theta > 0, 'Unbounded tail needs the zero-query endpoint')
    slopes = {(b[1] - a[1]) / (b[0] - a[0]) for a, b in zip(hull, hull[1:])}
    candidates = {Fraction(0)} | {slope for slope in slopes if slope > 0}
    return min(max(capacity - ratio * theta for theta, capacity in hull)
               - selected_capacity + ratio * selected_theta for ratio in candidates)


def compare_tables(source: Path, derived: Path) -> dict:
    check(sha256(source.read_bytes()).hexdigest() == PIN, 'Source pin mismatch')
    input_rows = read_csv(source)
    data = {(row['family'], Fraction(row['quota']), row['policy']): row for row in input_rows}
    rows = read_csv(derived / 'H7_capacity_secant_comparisons.csv')
    figure_rows = read_csv(derived / 'H7_capacity_policy_menu_q50.csv')
    check(len(data) == len(input_rows) == 56 and len(rows) == 8 and len(figure_rows) == 12,
          'Wrong row count')
    positive = {'weight': [], 'firm': []}
    gaps = []
    seen = set()
    anchored_column = 'anchored_B_capacity_difference_pp_mean'
    raw_column = 'raw_B_capacity_difference_pp_mean'
    for row in rows:
        learner, quota = row['learner'], Fraction(row['contact_quota_percent']) / 100
        check((learner, quota) not in seen, f'Duplicate comparison: {learner}, {quota}')
        seen.add((learner, quota))
        full = data[learner, quota, 'Full']
        selected = data[learner, quota, 'Selected']
        for label, comparison in (('full', full), ('selected', selected)):
            for suffix, column in (('raw', raw_column), ('anchored', anchored_column)):
                check(Fraction(row[f'{label}_{suffix}_capacity_pp']) == Fraction(comparison[column]),
                      f'Capacity transcription: {learner}, {quota}, {label}, {suffix}')
        for unit in ('weight', 'firm'):
            share_column = f'query_{unit}_fraction_mean'
            points = {name: (Fraction(data[learner, quota, name][share_column]),
                             Fraction(data[learner, quota, name][anchored_column])) for name in MENU}
            theta, selected_capacity = points['Selected']
            _, full_capacity = points['Full']
            margin = selected_capacity - theta * full_capacity
            check(close(row[f'selected_secant_margin_{unit}_pp'], margin), 'Secant margin differs')
            check(close(row[f'selected_secant_slope_{unit}_pp_per_unit_share'], selected_capacity / theta),
                  'Secant slope differs')
            lower = max(Fraction(0), (full_capacity - selected_capacity) / (1 - theta))
            check(close(row[f'selected_strict_win_interval_{unit}_lower_penalty_percent'], lower)
                  and close(row[f'selected_strict_win_interval_{unit}_upper_penalty_percent'], selected_capacity / theta),
                  'Strict endpoint interval bounds differ')
            wins = selected_capacity > 0 and margin > 0
            check((row[f'selected_strict_win_interval_{unit}_nonempty'] == 'True') == wins,
                  'Strict endpoint interval verdict differs')
            if wins:
                positive[unit].append((learner, int(100 * quota)))
            gap = upper_hull_gap(points)
            check(close(row[f'selected_min_gap_to_menu_{unit}_pp'], gap), 'Hull gap differs')
            check(gap > 0, 'Selected reaches the upper menu envelope')
            penalty = Fraction(row[f'selected_min_gap_to_menu_{unit}_at_penalty_percent'])
            rivals = {name: a - penalty * t for name, (t, a) in points.items() if name != 'Selected'}
            best = max(rivals.values())
            check(abs(best - selected_capacity + penalty * theta - gap) <= Fraction('1e-36'),
                  'Reported penalty does not attain the minimum gap')
            leading = {name for name, score in rivals.items() if best - score <= Fraction('1e-36')}
            check(leading == set(row[f'selected_min_gap_to_menu_{unit}_leading_policies'].split('|')),
                  'Reported leading policies differ')
            gaps.append(gap)
    check(positive == {unit: [('logistic', 20), ('tree', 35)] for unit in ('weight', 'firm')},
          'Endpoint comparator verdicts differ')
    expected = {(row['family'], row['policy']) for row in input_rows
                if Fraction(row['quota']) == Fraction(1, 2) and row['policy'] in MENU}
    seen = set()
    for row in figure_rows:
        learner, name = row['learner'], row['policy']
        check((learner, name) not in seen, 'Duplicate q50 menu entry')
        seen.add((learner, name))
        record = data[learner, Fraction(1, 2), name]
        check(Fraction(row['query_weight_percent']) == 100 * Fraction(record['query_weight_fraction_mean']),
              'Figure query coordinate differs')
        check(Fraction(row['anchored_capacity_pp']) == Fraction(record[anchored_column]),
              'Figure capacity coordinate differs')
    check(expected == seen, 'Figure menu coverage differs')
    logistic = {row['policy']: row for row in figure_rows if row['learner'] == 'logistic'}
    band, selected = (logistic[name] for name in ('Band_0.5', 'Selected'))
    check(all(Fraction(band[k]) < Fraction(selected[k]) for k in ('query_weight_fraction', 'query_firm_fraction'))
          and Fraction(band['anchored_capacity_pp']) > Fraction(selected['anchored_capacity_pp'])
          and Fraction(band['yield_cases_per_100_expected_weighted_contacts'])
          > Fraction(selected['yield_cases_per_100_expected_weighted_contacts']),
          'The fixed 50% band does not Pareto-dominate Selected in the q50 logistic means')
    return {'input_rows': len(data), 'comparison_rows': len(rows), 'figure_rows': len(figure_rows),
            'endpoint_strict_win_windows': positive, 'independent_upper_hull_comparisons': len(gaps),
            'positive_gap_range_pp': [float(min(gaps)), float(max(gaps))],
            'q50_logistic_fixed_band_dominates_selected': True}


def verify_artwork(derived: Path) -> dict:
    svg_path = derived / 'Figure_3_capacity_q50.svg'
    svg = XML.parse(svg_path).getroot()
    labels = Counter(''.join(e.itertext()) for e in svg.findall('.//svg:text', PLOT_NS))
    figure_rows = read_csv(derived / 'H7_capacity_policy_menu_q50.csv')
    panel_coordinate_checks = 0
    for axis_index, learner in enumerate(('logistic', 'tree'), 1):
        axis = svg.find(f".//svg:g[@id='axes_{axis_index}']", PLOT_NS)
        check(axis is not None, f'Missing SVG axes {axis_index}')
        objects = axis.findall("svg:g", PLOT_NS)
        markers = [group.find('.//svg:use', PLOT_NS) for group in objects
                   if group.get('id', '').startswith('PathCollection_')]
        check(len(markers) == 6 and all(marker is not None for marker in markers), 'Missing SVG policy markers')
        chords = [path for path in axis.findall('.//svg:path', PLOT_NS)
                  if 'stroke: #62676d' in path.get('style', '')]
        check(len(chords) == 1 and 'stroke-dasharray:' in chords[0].get('style', ''),
              'Expected one dashed endpoint segment per panel')
        chord_points = [float(n) for n in re.findall(r'-?\d+(?:\.\d+)?', chords[0].get('d', ''))]
        points = [(float(marker.get('x')), float(marker.get('y'))) for marker in markers]
        (x0, y0), (xf, yf) = points[0], points[4]
        check(chord_points == [x0, y0, xf, yf], 'Chord does not meet B and full-query marker centres')
        values = [row for row in figure_rows if row['learner'] == learner]
        full_capacity = float(values[4]['anchored_capacity_pp'])
        for row, (x, y) in zip(values, points):
            expected_x = x0 + (xf - x0) * float(row['query_weight_fraction'])
            expected_y = y0 + (yf - y0) * float(row['anchored_capacity_pp']) / full_capacity
            check(abs(x - expected_x) <= 2e-6 and abs(y - expected_y) <= 2e-6,
                  f'Policy marker differs: {learner}, {row["policy"]}')
            panel_coordinate_checks += 1
    with ZipFile(derived / 'Figure_3_capacity_q50.odg') as package:
        check(package.testzip() is None, 'ODG archive CRC failure')
        check(package.read('mimetype') == b'application/vnd.oasis.opendocument.graphics', 'Incorrect ODG MIME')
        odg = XML.fromstring(package.read('content.xml'))
        check(not odg.findall('.//draw:image', DRAW_NS) and not odg.findall('.//draw:object', DRAW_NS),
              'Expected editable native vectors and text')
        native_paths = odg.findall('.//draw:path', DRAW_NS)
        native_text = Counter(''.join(e.itertext()) for e in odg.findall('.//text:p', DRAW_NS))
        check(native_text == labels, 'ODG and SVG editable text differ')
        check(len(native_paths) > 12, 'Expected native Draw vector objects')
    with Image.open(derived / 'Figure_3_capacity_q50.png') as preview:
        preview.verify()
    with Image.open(derived / 'Figure_3_capacity_q50.png') as preview:
        size = preview.size
        check(size == (2610, 1242), 'Unexpected preview pixel size')
    pdf = (derived / 'Figure_3_capacity_q50.pdf').read_bytes()
    check(pdf.startswith(b'%PDF-') and b'/Type /Page' in pdf, 'Missing PDF page')
    return {'svg_coordinate_checks': panel_coordinate_checks, 'endpoint_chords_checked': 2,
            'native_odg_texts': sum(native_text.values()), 'native_odg_paths': len(native_paths),
            'native_odg_embedded_images': 0, 'png_pixel_size': size,
            'file_sha256': {path.name: sha256(path.read_bytes()).hexdigest()
                            for path in sorted(derived.iterdir()) if path.is_file()}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT / 'input/equal_country_policy_summaries.csv')
    parser.add_argument('--derived', type=Path, default=ROOT / 'derived')
    parser.add_argument('--report', type=Path, default=ROOT / 'H7_capacity_QA.json')
    args = parser.parse_args()
    report = {'status': 'PASS', 'scope': 'Archive aggregate arithmetic and figure authoring',
              'input_sha256': PIN, 'table_checks': compare_tables(args.input, args.derived),
              'artwork_checks': verify_artwork(args.derived), 'models_fitted': 0,
              'microdata_accessed': False}
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items() if key != 'artwork_checks'}, indent=2))


if __name__ == '__main__':
    main()
