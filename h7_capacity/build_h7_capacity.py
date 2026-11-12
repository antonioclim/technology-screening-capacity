#!/usr/bin/env python3
"""Build a retrospective allocation diagnostic from the pinned H7 aggregate CSV."""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from decimal import Decimal, localcontext
from fractions import Fraction
from hashlib import sha256
from itertools import combinations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INPUT_SHA256 = 'f3dcd98ad052d42281bf25ee8c992cf46abf213a48e8de5ccceda93fc4466f86'
FAMILIES = ('logistic', 'tree')
QUOTAS = tuple(Fraction(value) for value in ('0.2', '0.35', '0.5', '0.75'))
POLICIES = ('B', 'Band_0.1', 'Band_0.25', 'Band_0.5', 'Full', 'Selected')
TOLERANCE = Fraction('5e-12')


@dataclass(frozen=True)
class Policy:
    theta_weight: Fraction
    theta_firm: Fraction
    anchored_pp: Fraction
    raw_pp: Fraction
    baseline_inverse: Fraction
    equivalent_quota: Fraction
    yield_per_100: Fraction


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def decimal_text(value: Fraction) -> str:
    with localcontext() as context:
        context.prec = 40
        decimal = Decimal(value.numerator) / Decimal(value.denominator)
        return format(decimal, 'f')


def load_input(path: Path) -> dict[tuple[str, Fraction, str], Policy]:
    require(sha256(path.read_bytes()).hexdigest() == INPUT_SHA256, 'H7 input hash differs')
    expected = {(family, quota, policy) for family in FAMILIES for quota in QUOTAS
                for policy in (*POLICIES, 'SectorFixed')}
    policies = {}
    with path.open(newline='', encoding='utf-8') as handle:
        for row in csv.DictReader(handle):
            family, quota, name = row['family'], Fraction(row['quota']), row['policy']
            key = family, quota, name
            require(key in expected and key not in policies, f'Unexpected or duplicate row: {key}')
            require(int(row['country_n']) == 11, f'Unexpected country count: {key}')
            policy = Policy(*(Fraction(row[key]) for key in (
                'query_weight_fraction_mean', 'query_firm_fraction_mean',
                'anchored_B_capacity_difference_pp_mean', 'raw_B_capacity_difference_pp_mean',
                'B_inverse_at_B_cases_mean', 'B_inverse_at_policy_cases_mean',
                'cases_per_100_expected_contacts_mean')))
            require(0 <= policy.theta_weight <= 1 and 0 <= policy.theta_firm <= 1,
                    f'Query share outside [0, 1]: {key}')
            require(abs(policy.raw_pp - 100 * (policy.equivalent_quota - quota)) <= TOLERANCE,
                    f'Raw capacity differs from quota identity: {key}')
            require(abs(policy.anchored_pp - 100 * (policy.equivalent_quota - policy.baseline_inverse))
                    <= TOLERANCE, f'Anchored capacity differs from inverse identity: {key}')
            policies[key] = policy
    require(set(policies) == expected, 'H7 does not contain the complete policy grid')
    for family in FAMILIES:
        for quota in QUOTAS:
            baseline, full = (policies[family, quota, name] for name in ('B', 'Full'))
            require(baseline.theta_weight == baseline.theta_firm == baseline.anchored_pp == 0,
                    f'Unexpected B endpoint: {family}, {quota}')
            require(full.theta_weight == full.theta_firm == 1, f'Unexpected Full endpoint: {family}, {quota}')
            require(all(policies[family, quota, name].baseline_inverse == baseline.baseline_inverse
                        for name in (*POLICIES, 'SectorFixed')), f'Baseline inverse differs within: {family}, {quota}')
    return policies


def minimum_envelope_gap(menu: dict[str, Policy], share: str) -> tuple[Fraction, Fraction, list[str]]:
    """Minimise max(U_rival)−U_Selected for r>=0, with r in penalty-percent units."""
    selected = menu['Selected']
    target_theta = getattr(selected, share)
    rival = {name: (getattr(policy, share), policy.anchored_pp) for name, policy in menu.items()
             if name != 'Selected'}
    require(rival['B'] == (0, 0) and target_theta > 0, 'Expected growing gap at large r')
    knots = {Fraction(0)}
    for (theta_i, capacity_i), (theta_j, capacity_j) in combinations(rival.values(), 2):
        if theta_i != theta_j:
            intersection = (capacity_i - capacity_j) / (theta_i - theta_j)
            if intersection > 0:
                knots.add(intersection)
    best_gap = None
    best_ratio = Fraction(0)
    winners = []
    for ratio in sorted(knots):
        scores = {name: capacity - ratio * theta for name, (theta, capacity) in rival.items()}
        maximum = max(scores.values())
        gap = maximum - (selected.anchored_pp - ratio * target_theta)
        if best_gap is None or gap < best_gap:
            best_gap = gap
            best_ratio = ratio
            winners = [name for name, score in scores.items() if score == maximum]
    if best_gap is None:
        raise RuntimeError('No envelope knots evaluated')
    return best_gap, best_ratio, winners


def build_tables(policies: dict[tuple[str, Fraction, str], Policy]) -> tuple[list[dict], list[dict]]:
    comparisons = []
    fifty_menu = []
    for family in FAMILIES:
        for quota in QUOTAS:
            menu = {name: policies[family, quota, name] for name in POLICIES}
            full, selected = (menu[name] for name in ('Full', 'Selected'))
            row = {'learner': family, 'contact_quota_percent': 100 * quota, 'country_n': 11,
                   'baseline_inverse_at_own_case_mass_percent': 100 * full.baseline_inverse,
                   'full_baseline_equivalent_quota_percent': 100 * full.equivalent_quota,
                   'full_raw_capacity_pp': full.raw_pp, 'full_anchored_capacity_pp': full.anchored_pp,
                   'selected_baseline_equivalent_quota_percent': 100 * selected.equivalent_quota,
                   'selected_raw_capacity_pp': selected.raw_pp, 'selected_anchored_capacity_pp': selected.anchored_pp}
            for name, share in (('weight', 'theta_weight'), ('firm', 'theta_firm')):
                theta = getattr(selected, share)
                require(0 < theta < 1, f'Selected query share is not interior: {family}, {quota}, {name}')
                slope = selected.anchored_pp / theta
                low = max(Fraction(0), (full.anchored_pp - selected.anchored_pp) / (1 - theta))
                margin = selected.anchored_pp - theta * full.anchored_pp
                gap, ratio, winners = minimum_envelope_gap(menu, share)
                row.update({f'selected_query_{name}_fraction': theta,
                            f'selected_secant_slope_{name}_pp_per_unit_share': slope,
                            f'selected_secant_margin_{name}_pp': margin,
                            f'selected_strict_win_interval_{name}_lower_penalty_percent': low,
                            f'selected_strict_win_interval_{name}_upper_penalty_percent': slope,
                            f'selected_strict_win_interval_{name}_nonempty': low < slope,
                            f'selected_min_gap_to_menu_{name}_pp': gap,
                            f'selected_min_gap_to_menu_{name}_at_penalty_percent': ratio,
                            f'selected_min_gap_to_menu_{name}_leading_policies': '|'.join(winners)})
            comparisons.append(row)
            if quota == Fraction(1, 2):
                for name, policy in menu.items():
                    fifty_menu.append({'learner': family, 'contact_quota_percent': 100 * quota,
                                       'policy': name, 'country_n': 11,
                                       'query_weight_fraction': policy.theta_weight,
                                       'query_firm_fraction': policy.theta_firm,
                                       'query_weight_percent': 100 * policy.theta_weight,
                                       'query_firm_percent': 100 * policy.theta_firm,
                                       'yield_cases_per_100_expected_weighted_contacts': policy.yield_per_100,
                                       'baseline_equivalent_quota_percent': 100 * policy.equivalent_quota,
                                       'raw_capacity_pp': policy.raw_pp,
                                       'anchored_capacity_pp': policy.anchored_pp,
                                       'margin_from_weighted_B_Full_chord_pp': (
                                           policy.anchored_pp - policy.theta_weight * full.anchored_pp),
                                       'margin_from_firm_count_B_Full_chord_pp': (
                                           policy.anchored_pp - policy.theta_firm * full.anchored_pp)})
    return comparisons, fifty_menu


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({name: decimal_text(value) if isinstance(value, Fraction) else value
                             for name, value in row.items()})


def plot_figure(rows: list[dict], output: Path) -> None:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.ticker import MultipleLocator

    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 9,
                         'pdf.fonttype': 42, 'svg.fonttype': 'none',
                         'svg.hashsalt': 'papere-h7-capacity-q50',
                         'axes.spines.top': False, 'axes.spines.right': False})
    labels = ('Baseline B', '10% band', '25% band', '50% band', 'Full query', 'Nested-selected')
    shapes = ('o', '^', 's', 'D', 'o', '*')
    fills = ('#ffffff', '#6aa8a2', '#3d8f87', '#16776d', '#174977', '#e9ab47')
    edges = ('#333333', '#28645e', '#28645e', '#28645e', '#174977', '#62450f')
    sizes = (36, 44, 42, 49, 55, 136)
    markers = dict(zip(POLICIES, zip(labels, shapes, fills, edges, sizes)))
    figure, axes = plt.subplots(1, 2, figsize=(7.25, 3.45), sharey=True)
    figure.subplots_adjust(left=0.118, right=0.989, top=0.891, bottom=0.316, wspace=0.19)
    legend = []
    chord_color = '#62676d'
    for axis, family, title in zip(axes, FAMILIES, ('(a) Logistic regression', '(b) Fixed depth-3 tree')):
        points = [row for row in rows if row['learner'] == family]
        full = next(row for row in points if row['policy'] == 'Full')
        axis.plot([0, 100], [0, float(full['anchored_capacity_pp'])], color=chord_color,
                  linestyle=(0, (4, 3)), linewidth=0.95, zorder=2)
        for row in points:
            label, shape, fill, edge, size = markers[row['policy']]
            axis.scatter(float(row['query_weight_percent']), float(row['anchored_capacity_pp']),
                         s=size, marker=shape, facecolor=fill, edgecolor=edge,
                         linewidth=0.8, zorder=4 if row['policy'] == 'Selected' else 3)
            if family == 'logistic':
                legend.append(Line2D([], [], linestyle='none', marker=shape, markerfacecolor=fill,
                                     markeredgecolor=edge, markersize=size ** 0.5, label=label))
        axis.set_title(title, loc='left', fontsize=10.2, fontweight='semibold', pad=8)
        axis.set_xlim(-5, 105)
        axis.set_ylim(-0.29, 5.19)
        axis.set_xticks([0, 25, 50, 75, 100])
        axis.yaxis.set_major_locator(MultipleLocator(1))
        axis.grid(axis='y', color='#dde2e5', linewidth=0.65, zorder=0)
        axis.set_axisbelow(True)
        axis.spines[['left', 'bottom']].set_color('#51565b')
        axis.spines[['left', 'bottom']].set_linewidth(0.7)
        axis.tick_params(length=3, width=0.6, color='#555b60')
    axes[0].set_ylabel('Anchored capacity equivalent\n(percentage points)', labelpad=8)
    axes[1].tick_params(axis='y', left=False)
    figure.supxlabel('Realised query share (% of eligible survey-weighted mass)', y=0.208, fontsize=9.3)
    legend.append(Line2D([], [], color=chord_color, linestyle=(0, (4, 3)),
                         linewidth=0.95, label='B–Full chord'))
    figure.legend(handles=legend, loc='lower center', bbox_to_anchor=(0.53, 0.026),
                  ncol=4, columnspacing=1.25, handletextpad=0.55, frameon=False, fontsize=8.8)
    title = 'Anchored baseline capacity equivalents at a 50% contact quota'
    figure.savefig(output.with_suffix('.pdf'), metadata={'Title': title, 'Author': 'Antonio Clim',
                                                        'Subject': 'Retrospective H7 aggregate comparison'})
    figure.savefig(output.with_suffix('.svg'), metadata={'Title': title, 'Creator': 'Matplotlib'})
    figure.savefig(output.with_suffix('.png'), dpi=360, metadata={'Title': title, 'Author': 'Antonio Clim'})
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT / 'input/equal_country_policy_summaries.csv')
    parser.add_argument('--output', type=Path, default=ROOT / 'derived')
    parser.add_argument('--skip-odg', action='store_true', help='Skip native Draw vector export')
    arguments = parser.parse_args()
    policies = load_input(arguments.input)
    comparisons, fifty_menu = build_tables(policies)
    arguments.output.mkdir(exist_ok=True, parents=True)
    write_csv(arguments.output / 'H7_capacity_secant_comparisons.csv', comparisons)
    write_csv(arguments.output / 'H7_capacity_policy_menu_q50.csv', fifty_menu)
    figure = arguments.output / 'Figure_3_capacity_q50'
    plot_figure(fifty_menu, figure)
    if not arguments.skip_odg:
        from svg_to_native_odg import Converter
        receipt = Converter(figure.with_suffix('.svg')).save(figure.with_suffix('.odg'))
        (arguments.output / 'H7_capacity_ODG_build.json').write_text(
            json.dumps({key: value for key, value in receipt.items() if key != 'objects_detail'},
                       ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Read {len(policies)} H7 policy rows. Wrote {len(comparisons)} comparisons and {len(fifty_menu)} figure points.')


if __name__ == '__main__':
    main()
