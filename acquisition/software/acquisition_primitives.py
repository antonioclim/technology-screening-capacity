"""Allocation primitives for the locked H7 retrospective acquisition experiment.

These are numerical procedures, not new mathematical results. Quotas concern
expected survey-weighted contacts. Exact score ties share a common contact
probability; no identifier or outcome is used to split a tie.
"""
from __future__ import annotations

import math
import numpy as np


class _CompensatedPrefix:
    """Constant-storage Neumaier prefix accumulation in fixed score order."""
    __slots__ = ('value', 'correction')

    def __init__(self):
        self.value = 0.
        self.correction = 0.

    def total(self):
        return math.fsum((self.value, self.correction))

    def add(self, value):
        updated = self.value + value
        if abs(self.value) >= abs(value):
            self.correction += (self.value - updated) + value
        else:
            self.correction += (value - updated) + self.value
        self.value = updated
        return self.total()


def _inputs(scores, weights, quota=None):
    s = np.asarray(scores, dtype=float)
    w = np.asarray(weights, dtype=float)
    if s.ndim != 1 or not len(s) or w.shape != s.shape:
        raise ValueError('Scores and weights require nonempty matching vectors')
    if not np.isfinite(s).all() or not np.isfinite(w).all() or np.any(w <= 0):
        raise ValueError('Finite scores and positive finite weights required')
    if quota is not None and (not math.isfinite(quota) or not 0 <= quota <= 1):
        raise ValueError('Quota must lie in [0, 1]')
    return s, w


def _blocks(scores):
    order = np.argsort(-scores, kind='stable')
    ordered = scores[order]
    starts = np.r_[0, np.flatnonzero(ordered[1:] != ordered[:-1]) + 1]
    stops = np.r_[starts[1:], len(scores)]
    return [order[a:b] for a, b in zip(starts, stops)]


def _allocate_mass(scores, weights, contact_mass):
    total = math.fsum(weights)
    if contact_mass == 0:
        return np.zeros(len(scores), dtype=float)
    if contact_mass == total:
        return np.ones(len(scores), dtype=float)
    probabilities = np.zeros(len(scores), dtype=float)
    remaining = contact_mass
    for indices in _blocks(scores):
        mass = math.fsum(weights[indices])
        probability = min(1., max(0., remaining / mass))
        probabilities[indices] = probability
        remaining -= probability * mass
    observed = math.fsum(weights * probabilities)
    if abs(observed - contact_mass) > 1e-10 * max(1., total):
        raise ArithmeticError('Expected contact mass accounting failed')
    return probabilities


def allocate(scores, weights, quota):
    """Rank descending and fill an expected weighted quota, preserving ties."""
    s, w = _inputs(scores, weights, quota)
    return _allocate_mass(s, w, quota * math.fsum(w))


def band_mask(baseline_scores, weights, quota, fraction):
    """Query whole B-score blocks intersecting a prespecified mass interval.

    The interval is [q(1-r), q+(1-q)r] in descending weighted-rank space.
    Its nominal width is r. Ties can make actual query mass larger. The zero
    and full fractions are exact endpoints, including away from q=0.5.
    """
    s, w = _inputs(baseline_scores, weights, quota)
    if not math.isfinite(fraction) or not 0 <= fraction <= 1:
        raise ValueError('Acquisition fraction must lie in [0, 1]')
    if fraction == 0:
        return np.zeros(len(s), dtype=bool)
    if fraction == 1:
        return np.ones(len(s), dtype=bool)
    total = math.fsum(w)
    lower = quota * (1. - fraction) * total
    upper = (quota + (1. - quota) * fraction) * total
    mask = np.zeros(len(s), dtype=bool)
    prefix = _CompensatedPrefix()
    for indices in _blocks(s):
        left = prefix.total()
        mass = math.fsum(w[indices])
        right = prefix.add(mass)
        # Strict overlap excludes a score block touching only an endpoint.
        if max(left, lower) < min(right, upper):
            mask[indices] = True
    return mask


def selective_allocate(baseline_scores, rich_scores, weights, quota, queried):
    """Keep B outside the queried pool and rerank only the pool with rich scores.

    The pool receives exactly its B expected contact mass. Rich values outside
    the queried pool are ignored and may be NaN. No-query returns exact B;
    full-query returns the exact rich-score allocation at the same quota.
    """
    s, w = _inputs(baseline_scores, weights, quota)
    rich = np.asarray(rich_scores, dtype=float)
    mask = np.asarray(queried)
    if rich.shape != s.shape or mask.shape != s.shape or mask.dtype.kind != 'b':
        raise ValueError('Rich scores and boolean query mask must match B')
    result = allocate(s, w, quota)
    if not mask.any():
        return result
    if not np.isfinite(rich[mask]).all():
        raise ValueError('Queried rich scores must be finite')
    if mask.all():
        return allocate(rich, w, quota)
    contact_mass = math.fsum(w[mask] * result[mask])
    result[mask] = _allocate_mass(rich[mask], w[mask], contact_mass)
    return result


def sector_fixed_allocate(baseline_scores, rich_scores, weights, quota, sectors):
    """Hold each sector's B contact mass fixed and rerank within sector."""
    s, w = _inputs(baseline_scores, weights, quota)
    rich = np.asarray(rich_scores, dtype=float)
    groups = np.asarray(sectors, dtype=str)
    if rich.shape != s.shape or groups.shape != s.shape or not np.isfinite(rich).all():
        raise ValueError('Finite rich scores and matching sector vector required')
    base = allocate(s, w, quota)
    result = base.copy()
    for sector in sorted(set(groups)):
        mask = groups == sector
        contact_mass = math.fsum(w[mask] * base[mask])
        result[mask] = _allocate_mass(rich[mask], w[mask], contact_mass)
    return result


def capacity_equivalent(baseline_scores, weights, events, target_cases):
    """Smallest B quota reaching a target expected case mass.

    This empirical diagnostic explicitly uses evaluation outcomes. It is not
    an outcome-free deployable policy. Interpolation within an exact-score
    block uses its common fractional contact probability. For a plateau,
    the leftmost quota is returned. Case-mass boundary comparisons allow
    64 * machine epsilon * max(1, total case mass) to absorb floating-point regrouping;
    score equality is always exact. This numerical tolerance is not a
    scientific equivalence margin. Apply the same inverse to B and rich
    case masses when reporting an anchored capacity contrast.
    """
    s, w = _inputs(baseline_scores, weights)
    y = np.asarray(events, dtype=float)
    if y.shape != s.shape or not np.isfinite(y).all() or not np.isin(y, [0., 1.]).all():
        raise ValueError('Events must be a matching finite binary vector')
    if not math.isfinite(target_cases) or target_cases < 0:
        raise ValueError('Target case mass must be finite and nonnegative')
    total_cases = math.fsum(w * y)
    boundary_tolerance = 64. * np.finfo(float).eps * max(1., total_cases)
    if target_cases > total_cases:
        if target_cases - total_cases > boundary_tolerance:
            raise ValueError('Target exceeds available case mass')
        target_cases = total_cases
    if target_cases == 0:
        return 0.
    total_weight = math.fsum(w)
    weight_prefix = _CompensatedPrefix()
    case_prefix = _CompensatedPrefix()
    for indices in _blocks(s):
        before_weight = weight_prefix.total()
        before_cases = case_prefix.total()
        mass = math.fsum(w[indices])
        cases = math.fsum(w[indices] * y[indices])
        weight_prefix.add(mass)
        cumulative_cases = case_prefix.add(cases)
        # A goal computed by fsum over individual cases can exceed the same
        # boundary summed by score block by one ULP. Without this tolerance,
        # the inverse can jump over a long zero-case plateau.
        close_to_boundary = abs(target_cases - cumulative_cases) <= boundary_tolerance
        if cases > 0 and (target_cases <= cumulative_cases or close_to_boundary):
            if close_to_boundary:
                return min(1., max(0., weight_prefix.total() / total_weight))
            fraction = min(1., max(0., (target_cases - before_cases) / cases))
            return min(1., max(0., (before_weight + fraction * mass) / total_weight))
    raise ArithmeticError('Feasible target was not reached by the inverse curve')
