#!/usr/bin/env python3
"""Execute the frozen Paper E E4 analysis.

This program is distributed without microdata. It refuses a real-data run unless
an explicit post-freeze authorisation token and the exact E3 protocol hash are
provided. All outputs are aggregate; no establishment identifiers, row-level
predictions, residuals or microdata extracts are written.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd
from scipy import stats

AUTHORISATION_TOKEN = "E4_AUTHORISED_AFTER_E3_FREEZE"
EXPECTED_CONTAINER_SHA256 = "6d77d3ffb9dcef2ca4534e1c438ddd2e0b357eb852e6c5b48aa5fa6c3cbe2f0e"
EXPECTED_MEMBER_SHA256 = "f61a2c6e09f4763818ae1d4db8b330e97bffd8bb0824c2d833b79d728152bd17"
EXPECTED_MEMBER = "fat0_raw_data_qje.csv"
EXPECTED_E2_CONTRACT_SHA256 = "7a2ac874b1bd12fcebf102b602f81ff6d7471595f46dd68f2230ed9ed5073cb7"
EXPECTED_PRIMARY_MEMBERSHIP_SHA256 = "59d49ff980b98de612b32d721ed35dc80a92fb3175be2e1ddfcf8d36168c6f76"
EXPECTED_PRIMARY_N = 14412
MIN_DISCLOSURE_CELL = 20
BASE_SEED = 20260828

MOST_FIELDS = [f"ib9b{i}" for i in range(1, 6)]
BOUNDARIES = [
    "integrated_planning",
    "specialised_planning",
    "digitally_enabled_planning",
]
PRIMARY_SOURCES = [
    "Bangladesh", "Brazil", "Croatia", "Ethiopia", "Georgia", "Ghana",
    "India", "India_Wave2_New", "Kenya", "Korea", "Senegal", "Vietnam",
]
STRICT_SOURCES = [
    "Bangladesh", "Croatia", "Ethiopia", "Georgia", "Ghana", "India",
    "India_Wave2_New", "Kenya", "Korea", "Vietnam",
]
BROAD_SOURCES = [
    "Bangladesh", "Brazil", "BurkinaFaso", "Cambodia", "Croatia", "Ethiopia",
    "Georgia", "Ghana", "India", "India_Wave2_New", "Kenya", "Korea",
    "Senegal", "Vietnam",
]
EXPECTED_SECTOR_CODES = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "101", "102"]
REQUIRED_FIELDS = [
    "firmid", "country", "region_id", "a5a", "s4", "s7", "a3b", "a6",
    "a7a", "a7b", "a7c", "a7d", "e1", "e1a", "e1b", "e1c", "e1d",
    "e6a", "base_wt", *MOST_FIELDS,
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = []
        seen: set[str] = set()
        for row in rows:
            for key in row:
                if key not in seen:
                    seen.add(key)
                    fieldnames.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def normalise_code(value: Any) -> str:
    if pd.isna(value):
        return "UNKNOWN"
    try:
        x = float(value)
        if x.is_integer():
            return str(int(x))
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def reporting_country(source: str) -> str:
    return {
        "India_Wave2_New": "India",
        "BurkinaFaso": "Burkina Faso",
        "Korea": "Republic of Korea",
        "Vietnam": "Viet Nam",
    }.get(source, source)


def sample_fingerprint(frame: pd.DataFrame) -> str:
    lines = [
        f"{row.country}|{int(row.firmid)}"
        for row in frame[["country", "firmid"]].sort_values(["country", "firmid"]).itertuples(index=False)
    ]
    return sha256_bytes(("\n".join(lines) + "\n").encode("utf-8"))


def holm_adjust(pvalues: Sequence[float]) -> list[float]:
    p = np.asarray(pvalues, dtype=float)
    m = len(p)
    order = np.argsort(p)
    adjusted = np.empty(m, dtype=float)
    running = 0.0
    for rank, idx in enumerate(order):
        value = min(1.0, (m - rank) * p[idx])
        running = max(running, value)
        adjusted[idx] = running
    return adjusted.tolist()


def bh_adjust(pvalues: Sequence[float]) -> list[float]:
    p = np.asarray(pvalues, dtype=float)
    m = len(p)
    order = np.argsort(p)
    adjusted = np.empty(m, dtype=float)
    running = 1.0
    for reverse_rank, idx in enumerate(order[::-1], start=1):
        rank = m - reverse_rank + 1
        value = min(1.0, p[idx] * m / rank)
        running = min(running, value)
        adjusted[idx] = running
    return adjusted.tolist()


def safe_exp_percent(beta: float) -> float:
    if beta > 700:
        return float("inf")
    return 100.0 * math.expm1(beta)


def weighted_mean(x: np.ndarray, w: np.ndarray) -> float:
    return float(np.sum(w * x) / np.sum(w))


def weighted_rmse(y: np.ndarray, pred: np.ndarray, w: np.ndarray) -> float:
    return math.sqrt(weighted_mean((y - pred) ** 2, w))


def weighted_mae(y: np.ndarray, pred: np.ndarray, w: np.ndarray) -> float:
    return weighted_mean(np.abs(y - pred), w)


def weighted_quantile_threshold(values: np.ndarray, weights: np.ndarray, q: float) -> float:
    order = np.argsort(values, kind="mergesort")
    v = values[order]
    w = weights[order]
    c = np.cumsum(w)
    target = q * c[-1]
    idx = int(np.searchsorted(c, target, side="left"))
    return float(v[min(idx, len(v) - 1)])


def load_protocol(protocol_path: Path, expected_hash: str | None = None) -> tuple[dict[str, Any], str]:
    raw = protocol_path.read_bytes()
    actual = sha256_bytes(raw)
    if expected_hash and actual != expected_hash:
        raise RuntimeError(f"E3 protocol hash mismatch: actual={actual}, expected={expected_hash}")
    protocol = json.loads(raw.decode("utf-8"))
    if protocol.get("status") != "FROZEN_E3_PREANALYSIS_PROTOCOL":
        raise RuntimeError("Protocol is not in frozen E3 state")
    if protocol.get("immutable_e2_contract_sha256") != EXPECTED_E2_CONTRACT_SHA256:
        raise RuntimeError("Protocol does not bind the expected E2 contract")
    return protocol, actual


def load_real_microdata(path: Path) -> pd.DataFrame:
    if sha256_file(path) != EXPECTED_CONTAINER_SHA256:
        raise RuntimeError("Microdata container SHA-256 mismatch")
    with zipfile.ZipFile(path) as zf:
        bad = zf.testzip()
        if bad:
            raise RuntimeError(f"Microdata ZIP CRC failure at {bad}")
        if EXPECTED_MEMBER not in zf.namelist():
            raise RuntimeError(f"Expected pooled member not found: {EXPECTED_MEMBER}")
        raw = zf.read(EXPECTED_MEMBER)
    if sha256_bytes(raw) != EXPECTED_MEMBER_SHA256:
        raise RuntimeError("Pooled member SHA-256 mismatch")
    header = pd.read_csv(pd.io.common.BytesIO(raw), nrows=0).columns.tolist()
    missing = sorted(set(REQUIRED_FIELDS) - set(header))
    if missing:
        raise RuntimeError(f"Required fields absent: {missing}")
    frame = pd.read_csv(pd.io.common.BytesIO(raw), usecols=REQUIRED_FIELDS, low_memory=False)
    if len(frame) != 21055 or len(header) != 723:
        raise RuntimeError(f"Unexpected microdata shape: rows={len(frame)}, columns={len(header)}")
    if frame["firmid"].duplicated().any():
        raise RuntimeError("firmid is not unique")
    return frame


def prepare_full_frame(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    most = d[MOST_FIELDS]
    binary = most.isin([0, 1]).all(axis=1)
    onehot = binary & most.sum(axis=1).eq(1)
    state = pd.Series(np.nan, index=d.index, dtype=float)
    state.loc[onehot] = np.argmax(most.loc[onehot].to_numpy(), axis=1) + 1
    d["most_onehot"] = onehot
    d["most_state"] = state
    d["integrated_planning"] = d["most_state"].eq(5).astype(int)
    d["specialised_planning"] = d["most_state"].isin([4, 5]).astype(int)
    d["digitally_enabled_planning"] = d["most_state"].isin([2, 3, 4, 5]).astype(int)
    d["reporting_country"] = d["country"].map(reporting_country)
    return d


def build_sample(df: pd.DataFrame, sample_id: str) -> pd.DataFrame:
    source_sets = {
        "PRIMARY_S60_N200": PRIMARY_SOURCES,
        "STRICT_S80_N200": STRICT_SOURCES,
        "BROAD_AVAILABLE_N20": BROAD_SOURCES,
    }
    if sample_id in source_sets:
        sources = source_sets[sample_id]
        mask = (
            df["country"].isin(sources)
            & df["e6a"].gt(0)
            & df["s7"].gt(0)
            & df["base_wt"].gt(0)
            & df["most_onehot"]
        )
        out = df.loc[mask].copy()
    elif sample_id == "PRIMARY_S7_GE5":
        out = build_sample(df, "PRIMARY_S60_N200")
        out = out.loc[out["s7"].ge(5)].copy()
    elif sample_id == "MATCHED_E1_DENOMINATOR":
        out = build_sample(df, "PRIMARY_S60_N200")
        out = out.loc[pd.to_numeric(out["e1"], errors="coerce").gt(0)].copy()
    elif sample_id == "MATCHED_COMPONENT_DENOMINATOR":
        out = build_sample(df, "PRIMARY_S60_N200")
        comps = out[["e1a", "e1b", "e1c", "e1d"]].apply(pd.to_numeric, errors="coerce")
        valid = comps.notna().all(axis=1) & comps.sum(axis=1).gt(0)
        out = out.loc[valid].copy()
        out["component_employment"] = comps.loc[valid].sum(axis=1)
    else:
        raise ValueError(f"Unknown sample_id: {sample_id}")
    return out.sort_values(["country", "firmid"]).reset_index(drop=True)


def add_outcomes_and_weights(frame: pd.DataFrame, primary_reference: pd.DataFrame | None = None) -> pd.DataFrame:
    d = frame.copy()
    d["Y_PRIMARY_RAW"] = np.log(d["e6a"].astype(float) / d["s7"].astype(float))
    d["W_SENS_RAW"] = d["base_wt"].astype(float)
    d["W_PRIMARY_SOURCE_MEAN1"] = d["W_SENS_RAW"] / d.groupby("country")["W_SENS_RAW"].transform("mean")
    d["W_SENS_UNWEIGHTED"] = 1.0
    n = len(d)
    s = d["country"].nunique()
    c = d["reporting_country"].nunique()
    d["W_SENS_EQUAL_SOURCE"] = d["W_SENS_RAW"] / d.groupby("country")["W_SENS_RAW"].transform("sum") * (n / s)
    d["W_SENS_EQUAL_REPORTING_COUNTRY"] = (
        d["W_SENS_RAW"] / d.groupby("reporting_country")["W_SENS_RAW"].transform("sum") * (n / c)
    )
    q99 = d.groupby("country")["W_SENS_RAW"].transform(lambda x: x.quantile(0.99, interpolation="linear"))
    cap = np.minimum(d["W_SENS_RAW"], q99)
    d["W_SENS_SOURCE_MEAN1_CAP99"] = cap / cap.groupby(d["country"]).transform("mean")

    ref = primary_reference if primary_reference is not None else d
    if "Y_PRIMARY_RAW" not in ref:
        ref = ref.copy()
        ref["Y_PRIMARY_RAW"] = np.log(ref["e6a"].astype(float) / ref["s7"].astype(float))
    means = ref.groupby("country")["Y_PRIMARY_RAW"].mean()
    sds = ref.groupby("country")["Y_PRIMARY_RAW"].std(ddof=1)
    q01 = ref.groupby("country")["Y_PRIMARY_RAW"].quantile(0.01, interpolation="linear")
    q99y = ref.groupby("country")["Y_PRIMARY_RAW"].quantile(0.99, interpolation="linear")
    d["Y_ROBUST_Z_SOURCE"] = (d["Y_PRIMARY_RAW"] - d["country"].map(means)) / d["country"].map(sds)
    d["Y_ROBUST_WINSOR_1_99"] = np.maximum(
        d["country"].map(q01).to_numpy(),
        np.minimum(d["Y_PRIMARY_RAW"].to_numpy(), d["country"].map(q99y).to_numpy()),
    )
    if "e1" in d:
        e1 = pd.to_numeric(d["e1"], errors="coerce")
        d["Y_SENS_E1"] = np.where(e1.gt(0), np.log(d["e6a"].astype(float) / e1), np.nan)
    if "component_employment" in d:
        d["Y_SENS_COMPONENT"] = np.log(d["e6a"].astype(float) / d["component_employment"].astype(float))
    return d


def _valid_year(series: pd.Series) -> pd.Series:
    x = pd.to_numeric(series, errors="coerce")
    return x.where(x.between(1800, 2023))


def _manager_bin(series: pd.Series) -> pd.Series:
    x = pd.to_numeric(series, errors="coerce")
    out = pd.Series("UNKNOWN", index=series.index, dtype=object)
    valid = x.between(0, 80)
    out.loc[valid & x.lt(5)] = "0_4"
    out.loc[valid & x.between(5, 9)] = "5_9"
    out.loc[valid & x.between(10, 19)] = "10_19"
    out.loc[valid & x.between(20, 29)] = "20_29"
    out.loc[valid & x.ge(30)] = "30_PLUS"
    return out


def control_codings(frame: pd.DataFrame, fitted: dict[str, Any] | None = None) -> tuple[pd.DataFrame, dict[str, Any]]:
    d = frame.copy()
    out = pd.DataFrame(index=d.index)
    out["source"] = d["country"].astype(str)
    out["source_region"] = d["country"].astype(str) + "::" + d["region_id"].map(normalise_code)
    sector = d["a5a"].map(normalise_code)
    out["sector"] = sector.where(sector.isin(EXPECTED_SECTOR_CODES), "UNKNOWN")
    s4 = d["s4"].map(normalise_code)
    out["multi_establishment"] = s4.where(s4.isin(["0", "1"]), "UNKNOWN")
    a3b = pd.to_numeric(d["a3b"], errors="coerce")
    foreign = pd.Series("UNKNOWN", index=d.index, dtype=object)
    foreign.loc[a3b.eq(0)] = "DOMESTIC"
    foreign.loc[a3b.gt(0) & a3b.le(100)] = "ANY_FOREIGN"
    out["foreign_owner"] = foreign

    ln_s7 = np.log(pd.to_numeric(d["s7"], errors="coerce").astype(float))
    if fitted is None:
        ln_means = ln_s7.groupby(d["country"]).mean().to_dict()
    else:
        ln_means = fitted["ln_s7_source_means"]
    out["ln_s7_c_source"] = ln_s7 - d["country"].map(ln_means).astype(float)

    a6 = _valid_year(d["a6"])
    if fitted is None:
        year_medians = a6.groupby(d["country"]).median().to_dict()
    else:
        year_medians = fitted["a6_source_medians"]
    med = d["country"].map(year_medians).astype(float)
    out["a6_missing_invalid"] = a6.isna().astype(float)
    out["a6_decades_c_source_median"] = (a6.fillna(med) - med) / 10.0

    out["manager_experience_bin"] = _manager_bin(d["a7a"])
    a7b = d["a7b"].map(normalise_code)
    out["manager_sex"] = a7b.where(a7b.isin(["1", "2"]), "UNKNOWN")
    a7c = d["a7c"].map(normalise_code)
    out["manager_education"] = a7c.where(a7c.isin(["1", "2", "3", "4", "5", "6"]), "UNKNOWN")
    a7d = d["a7d"].map(normalise_code)
    out["manager_studied_abroad"] = a7d.where(a7d.isin(["1", "2"]), "UNKNOWN")

    if fitted is None:
        fitted = {
            "ln_s7_source_means": {str(k): float(v) for k, v in ln_means.items()},
            "a6_source_medians": {str(k): float(v) for k, v in year_medians.items()},
        }
    return out, fitted


def _dummy_block(series: pd.Series, prefix: str, fitted_levels: list[str] | None = None) -> tuple[pd.DataFrame, list[str]]:
    s = series.astype(str)
    levels = fitted_levels if fitted_levels is not None else sorted(s.unique().tolist())
    if not levels:
        raise RuntimeError(f"No levels for {prefix}")
    cat = pd.Categorical(s, categories=levels)
    block = pd.get_dummies(cat, prefix=prefix, dtype=float)
    reference = levels[0]
    ref_col = f"{prefix}_{reference}"
    if ref_col in block:
        block = block.drop(columns=[ref_col])
    block.index = series.index
    return block, levels


def fit_encoder(frame: pd.DataFrame, model_id: str) -> dict[str, Any]:
    c, numeric = control_codings(frame)
    categories: dict[str, list[str]] = {}
    cat_names: list[tuple[str, str]] = []
    if model_id in {"M0", "M1", "M1_NO_SIZE"}:
        cat_names.append(("source", "source"))
    elif model_id == "M2":
        cat_names.append(("source_region", "source_region"))
    else:
        raise ValueError(model_id)
    if model_id in {"M1", "M1_NO_SIZE", "M2"}:
        cat_names.extend([
            ("sector", "sector"),
            ("multi_establishment", "multi_establishment"),
            ("foreign_owner", "foreign_owner"),
        ])
    if model_id == "M2":
        cat_names.extend([
            ("manager_experience_bin", "manager_experience_bin"),
            ("manager_sex", "manager_sex"),
            ("manager_education", "manager_education"),
            ("manager_studied_abroad", "manager_studied_abroad"),
        ])
    for col, prefix in cat_names:
        _, levels = _dummy_block(c[col], prefix)
        categories[col] = levels
    return {"model_id": model_id, "numeric": numeric, "categories": categories}


def design_matrix(
    frame: pd.DataFrame,
    model_id: str,
    encoder: dict[str, Any] | None = None,
    adoption: str | None = None,
    moderator: str | None = None,
) -> tuple[np.ndarray, list[str], dict[str, Any], list[str]]:
    if encoder is None:
        encoder = fit_encoder(frame, model_id)
    c, _ = control_codings(frame, fitted=encoder["numeric"])
    blocks: list[pd.DataFrame] = [pd.DataFrame({"intercept": np.ones(len(frame))}, index=frame.index)]
    names: list[str] = ["intercept"]

    cat_order: list[tuple[str, str]] = []
    if model_id in {"M0", "M1", "M1_NO_SIZE"}:
        cat_order.append(("source", "source"))
    else:
        cat_order.append(("source_region", "source_region"))
    if model_id in {"M1", "M1_NO_SIZE", "M2"}:
        cat_order.extend([
            ("sector", "sector"),
            ("multi_establishment", "multi_establishment"),
            ("foreign_owner", "foreign_owner"),
        ])
    for col, prefix in cat_order:
        block, _ = _dummy_block(c[col], prefix, encoder["categories"][col])
        blocks.append(block)
        names.extend(block.columns.tolist())

    if model_id in {"M1", "M2"}:
        blocks.append(pd.DataFrame({"ln_s7_c_source": c["ln_s7_c_source"].astype(float)}, index=frame.index))
        names.append("ln_s7_c_source")
    if model_id in {"M1", "M1_NO_SIZE", "M2"}:
        numeric = pd.DataFrame({
            "a6_decades_c_source_median": c["a6_decades_c_source_median"].astype(float),
            "a6_missing_invalid": c["a6_missing_invalid"].astype(float),
        }, index=frame.index)
        blocks.append(numeric)
        names.extend(numeric.columns.tolist())
    if model_id == "M2":
        for col, prefix in [
            ("manager_experience_bin", "manager_experience_bin"),
            ("manager_sex", "manager_sex"),
            ("manager_education", "manager_education"),
            ("manager_studied_abroad", "manager_studied_abroad"),
        ]:
            block, _ = _dummy_block(c[col], prefix, encoder["categories"][col])
            blocks.append(block)
            names.extend(block.columns.tolist())

    interaction_names: list[str] = []
    if moderator:
        if moderator == "size_band":
            raw = pd.cut(
                frame["s7"].astype(float),
                bins=[5 - 1e-12, 20, 100, np.inf],
                labels=["5_19", "20_99", "100_PLUS"],
                right=False,
            ).astype(str)
            levels = ["5_19", "20_99", "100_PLUS"]
            mod_block, _ = _dummy_block(pd.Series(raw, index=frame.index), "size_band", levels)
            blocks.append(mod_block)
            names.extend(mod_block.columns.tolist())
        elif moderator == "foreign_owner":
            levels = ["DOMESTIC", "ANY_FOREIGN"]
            mod_block, _ = _dummy_block(c["foreign_owner"], "het_foreign_owner", levels)
            # Main effect already appears in M1. Keep only interactions below.
        elif moderator == "sector_pooled":
            pooled = c["sector"].replace({"2": "SPARSE_2_11", "11": "SPARSE_2_11"})
            levels = sorted(pooled.unique().tolist())
            mod_block, _ = _dummy_block(pooled, "het_sector", levels)
            # Main sector effects already appear in M1.
        else:
            raise ValueError(moderator)
    else:
        mod_block = None

    if adoption:
        a = frame[adoption].astype(float).to_numpy()
        a_df = pd.DataFrame({"adoption": a}, index=frame.index)
        blocks.append(a_df)
        names.append("adoption")
        if moderator and mod_block is not None:
            inter = mod_block.multiply(a, axis=0)
            inter.columns = [f"adoption_x_{x}" for x in mod_block.columns]
            blocks.append(inter)
            names.extend(inter.columns.tolist())
            interaction_names = inter.columns.tolist()

    Xdf = pd.concat(blocks, axis=1)
    if Xdf.isna().any().any():
        cols = Xdf.columns[Xdf.isna().any()].tolist()
        raise RuntimeError(f"Missing values remain in design matrix: {cols}")
    X = Xdf.to_numpy(dtype=float)
    return X, names, encoder, interaction_names


@dataclass
class FitResult:
    beta: np.ndarray
    residual: np.ndarray
    fitted: np.ndarray
    h: np.ndarray
    bread: np.ndarray
    hc3_cov: np.ndarray
    hc3_influence: np.ndarray
    score_contributions: np.ndarray
    rank: int
    condition: float
    names: list[str]


def fit_wls(X: np.ndarray, y: np.ndarray, w: np.ndarray, names: list[str]) -> FitResult:
    if len(y) != X.shape[0] or len(w) != X.shape[0]:
        raise ValueError("Shape mismatch")
    if np.any(~np.isfinite(X)) or np.any(~np.isfinite(y)) or np.any(~np.isfinite(w)) or np.any(w <= 0):
        raise RuntimeError("Nonfinite or nonpositive input to WLS")
    sw = np.sqrt(w)
    Xw = X * sw[:, None]
    yw = y * sw
    rank = int(np.linalg.matrix_rank(Xw))
    if rank != X.shape[1]:
        raise RuntimeError(f"Rank-deficient design: rank={rank}, columns={X.shape[1]}")
    xtx = Xw.T @ Xw
    bread = np.linalg.inv(xtx)
    beta = bread @ (Xw.T @ yw)
    fitted = X @ beta
    residual = y - fitted
    h = np.einsum("ij,jk,ik->i", Xw, bread, Xw)
    if np.any(h >= 1 - 1e-10):
        raise RuntimeError("Leverage too close to one for HC3/PRESS")
    scalar = w * residual / (1.0 - h)
    influence = (X @ bread.T) * scalar[:, None]
    hc3_cov = influence.T @ influence
    scores = X * (w * residual)[:, None]
    condition = float(np.linalg.cond(Xw))
    return FitResult(beta, residual, fitted, h, bread, hc3_cov, influence, scores, rank, condition, names)


def fit_wls_point_only(X: np.ndarray, y: np.ndarray, w: np.ndarray, names: list[str]) -> dict[str, Any]:
    """Return unchanged WLS point estimates and design diagnostics only.

    The frozen leave-one-source-out check requests coefficient ranges and sign
    stability, not HC3 inference. Unit leverage can make HC3 undefined while the
    WLS normal equations remain full rank. This helper changes no sample, term,
    outcome, weight or coefficient estimator.
    """
    if len(y) != X.shape[0] or len(w) != X.shape[0]:
        raise ValueError("Shape mismatch")
    if np.any(~np.isfinite(X)) or np.any(~np.isfinite(y)) or np.any(~np.isfinite(w)) or np.any(w <= 0):
        raise RuntimeError("Nonfinite or nonpositive input to point-only WLS")
    sw = np.sqrt(w)
    Xw = X * sw[:, None]
    yw = y * sw
    rank = int(np.linalg.matrix_rank(Xw))
    if rank != X.shape[1]:
        raise RuntimeError(f"Rank-deficient point-only design: rank={rank}, columns={X.shape[1]}")
    xtx = Xw.T @ Xw
    bread = np.linalg.inv(xtx)
    beta = bread @ (Xw.T @ yw)
    h = np.einsum("ij,jk,ik->i", Xw, bread, Xw)
    return {
        "beta": beta,
        "h": h,
        "rank": rank,
        "condition": float(np.linalg.cond(Xw)),
        "names": names,
    }


def coefficient_record(fit: FitResult, name: str, alpha: float = 0.05) -> dict[str, float]:
    idx = fit.names.index(name)
    beta = float(fit.beta[idx])
    se = math.sqrt(max(float(fit.hc3_cov[idx, idx]), 0.0))
    z = beta / se if se > 0 else float("nan")
    p = float(2 * stats.norm.sf(abs(z))) if math.isfinite(z) else float("nan")
    crit = float(stats.norm.ppf(1 - alpha / 2))
    return {
        "estimate": beta,
        "se_hc3": se,
        "z_hc3": z,
        "p_hc3": p,
        "ci_low": beta - crit * se,
        "ci_high": beta + crit * se,
        "exact_percent_difference": safe_exp_percent(beta),
    }


def wald_test(theta: np.ndarray, covariance: np.ndarray, R: np.ndarray) -> dict[str, float]:
    diff = R @ theta
    middle = R @ covariance @ R.T
    rank = int(np.linalg.matrix_rank(middle))
    stat = float(diff.T @ np.linalg.pinv(middle) @ diff)
    p = float(stats.chi2.sf(stat, rank))
    return {"wald_chi2": stat, "df": rank, "p_value": p}


def association_system(frame: pd.DataFrame, model_id: str, outcome: str, weight: str) -> dict[str, Any]:
    y = frame[outcome].to_numpy(dtype=float)
    w = frame[weight].to_numpy(dtype=float)
    fits: dict[str, FitResult] = {}
    rows: list[dict[str, Any]] = []
    psi = []
    cluster_psi = []
    clusters = frame["country"].astype(str).to_numpy()
    unique_clusters = sorted(np.unique(clusters).tolist())

    for boundary in BOUNDARIES:
        X, names, encoder, _ = design_matrix(frame, model_id, adoption=boundary)
        fit = fit_wls(X, y, w, names)
        fits[boundary] = fit
        rec = coefficient_record(fit, "adoption", alpha=0.05 / 3.0)
        idx = names.index("adoption")
        psi.append(fit.hc3_influence[:, idx])
        cluster_vals = []
        row_bread = fit.bread[idx, :]
        for g in unique_clusters:
            Sg = fit.score_contributions[clusters == g].sum(axis=0)
            cluster_vals.append(float(row_bread @ Sg))
        cluster_psi.append(cluster_vals)
        rows.append({
            "boundary": boundary,
            "model_id": model_id,
            "n": len(frame),
            "p": X.shape[1],
            "rank": fit.rank,
            "condition_number": fit.condition,
            "max_leverage": float(np.max(fit.h)),
            "estimate_log_points": rec["estimate"],
            "se_hc3": rec["se_hc3"],
            "z_hc3": rec["z_hc3"],
            "p_hc3_unadjusted": rec["p_hc3"],
            "simultaneous_ci_level_pct": 100 * (1 - 0.05 / 3),
            "simultaneous_ci_low": rec["ci_low"],
            "simultaneous_ci_high": rec["ci_high"],
            "exact_percent_difference": rec["exact_percent_difference"],
        })

    theta = np.array([rows[i]["estimate_log_points"] for i in range(3)], dtype=float)
    psi_matrix = np.column_stack(psi)
    joint_cov = psi_matrix.T @ psi_matrix
    R_global = np.array([[1, -1, 0], [0, 1, -1]], dtype=float)
    global_test = wald_test(theta, joint_cov, R_global)

    individual_adj = holm_adjust([r["p_hc3_unadjusted"] for r in rows])
    for r, adj in zip(rows, individual_adj):
        r["p_hc3_holm_individual_family"] = adj

    pairs = [(0, 1, "integrated_vs_specialised"), (1, 2, "specialised_vs_digital"), (0, 2, "integrated_vs_digital")]
    pair_rows = []
    pair_p = []
    for i, j, label in pairs:
        diff = theta[i] - theta[j]
        var = joint_cov[i, i] + joint_cov[j, j] - 2 * joint_cov[i, j]
        se = math.sqrt(max(float(var), 0.0))
        z = diff / se if se > 0 else float("nan")
        p = float(2 * stats.norm.sf(abs(z))) if math.isfinite(z) else float("nan")
        pair_p.append(p)
        pair_rows.append({
            "contrast": label,
            "estimate_difference_log_points": float(diff),
            "se_joint_hc3": se,
            "z_joint_hc3": z,
            "p_unadjusted": p,
            "gate_open_primary_global_p_lt_0_05": bool(global_test["p_value"] < 0.05),
        })
    pair_adj = holm_adjust(pair_p)
    for r, adj in zip(pair_rows, pair_adj):
        r["p_holm_gatekept"] = adj if global_test["p_value"] < 0.05 else None
        r["confirmatory_interpretation_permitted"] = bool(global_test["p_value"] < 0.05 and adj < 0.05)

    # Cluster-robust CR1S-style sensitivity across the twelve source strata.
    C = np.column_stack(cluster_psi)
    G = len(unique_clusters)
    p_model = fits[BOUNDARIES[0]].beta.size
    correction = (G / (G - 1)) * ((len(frame) - 1) / (len(frame) - p_model))
    cluster_cov = correction * (C.T @ C)
    cluster_global = wald_test(theta, cluster_cov, R_global)
    cluster_rows = []
    for i, boundary in enumerate(BOUNDARIES):
        se = math.sqrt(max(float(cluster_cov[i, i]), 0.0))
        tstat = theta[i] / se if se > 0 else float("nan")
        p = float(2 * stats.t.sf(abs(tstat), df=G - 1)) if math.isfinite(tstat) else float("nan")
        cluster_rows.append({
            "boundary": boundary,
            "estimate_log_points": float(theta[i]),
            "se_cr1s_source": se,
            "t_df_11": tstat,
            "p_t_df_11": p,
            "clusters": G,
            "status": "SENSITIVITY_NOT_PRIMARY_NO_VERIFIED_PSU",
        })

    return {
        "coefficient_rows": rows,
        "global_equality": global_test,
        "pairwise_rows": pair_rows,
        "joint_hc3_covariance": joint_cov,
        "cluster_rows": cluster_rows,
        "cluster_global_equality": cluster_global,
        "fits": fits,
    }


def leave_one_source_out(frame: pd.DataFrame, outcome: str, weight: str, model_id: str = "M1") -> list[dict[str, Any]]:
    by_boundary: dict[str, list[float]] = {b: [] for b in BOUNDARIES}
    by_boundary_unit_leverage: dict[str, int] = {b: 0 for b in BOUNDARIES}
    details: list[dict[str, Any]] = []
    for source in sorted(frame["country"].unique().tolist()):
        sub = frame.loc[frame["country"].ne(source)].copy()
        for boundary in BOUNDARIES:
            X, names, _, _ = design_matrix(sub, model_id, adoption=boundary)
            fit = fit_wls_point_only(X, sub[outcome].to_numpy(float), sub[weight].to_numpy(float), names)
            beta = float(fit["beta"][names.index("adoption")])
            unit_count = int(np.sum(fit["h"] >= 1 - 1e-10))
            by_boundary[boundary].append(beta)
            by_boundary_unit_leverage[boundary] += int(unit_count > 0)
            details.append({
                "omitted_source": source,
                "boundary": boundary,
                "n": len(sub),
                "p": X.shape[1],
                "rank": fit["rank"],
                "condition_number": fit["condition"],
                "max_leverage": float(np.max(fit["h"])),
                "unit_leverage_observations": unit_count,
                "estimate_log_points": beta,
                "replications": None,
                "minimum_estimate": None,
                "median_estimate": None,
                "maximum_estimate": None,
                "positive_sign_share": None,
                "negative_sign_share": None,
                "runs_with_unit_leverage": None,
                "estimator_status": "WLS_POINT_ESTIMATE_ONLY_NO_HC3",
            })
    summary = []
    for boundary, values in by_boundary.items():
        a = np.asarray(values)
        summary.append({
            "omitted_source": "SUMMARY",
            "boundary": boundary,
            "n": None,
            "p": None,
            "rank": None,
            "condition_number": None,
            "max_leverage": None,
            "unit_leverage_observations": None,
            "estimate_log_points": None,
            "replications": len(a),
            "minimum_estimate": float(a.min()),
            "median_estimate": float(np.median(a)),
            "maximum_estimate": float(a.max()),
            "positive_sign_share": float(np.mean(a > 0)),
            "negative_sign_share": float(np.mean(a < 0)),
            "runs_with_unit_leverage": by_boundary_unit_leverage[boundary],
            "estimator_status": "SUMMARY_OF_WLS_POINT_ESTIMATES_NO_HC3",
        })
    return details + summary


def press_prediction(frame: pd.DataFrame, outcome: str, weight: str, model_id: str = "M1") -> list[dict[str, Any]]:
    y = frame[outcome].to_numpy(float)
    w = frame[weight].to_numpy(float)
    rows = []
    models = [("BASELINE_NO_ADOPTION", None)] + [(b, b) for b in BOUNDARIES]
    baseline_sse = None
    for label, boundary in models:
        X, names, _, _ = design_matrix(frame, model_id, adoption=boundary)
        fit = fit_wls(X, y, w, names)
        loo_residual = fit.residual / (1.0 - fit.h)
        pred = y - loo_residual
        sse = float(np.sum(w * loo_residual ** 2))
        if baseline_sse is None:
            baseline_sse = sse
        rows.append({
            "model": label,
            "n": len(frame),
            "weighted_loo_rmse": weighted_rmse(y, pred, w),
            "weighted_loo_mae": weighted_mae(y, pred, w),
            "weighted_press_sse": sse,
            "relative_press_reduction_vs_baseline": 0.0 if label == "BASELINE_NO_ADOPTION" else float((baseline_sse - sse) / baseline_sse),
            "max_leverage": float(fit.h.max()),
        })
    return rows


def _stable_seed(*parts: Any) -> int:
    raw = "|".join(map(str, parts)).encode("utf-8")
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big") % (2**32 - 1)


def assign_stratified_folds(frame: pd.DataFrame, repetition: int, folds: int = 5) -> np.ndarray:
    assignment = np.empty(len(frame), dtype=int)
    work = frame.reset_index(drop=True)
    strata = work["country"].astype(str) + "::" + work["most_state"].astype(int).astype(str)
    for key, idx in strata.groupby(strata).groups.items():
        idx_arr = np.asarray(list(idx), dtype=int)
        rng = np.random.default_rng(_stable_seed(BASE_SEED, repetition, key))
        rng.shuffle(idx_arr)
        assignment[idx_arr] = np.arange(len(idx_arr)) % folds
    return assignment


def repeated_cross_validation(
    frame: pd.DataFrame,
    outcome: str,
    weight: str,
    repetitions: int = 20,
    folds: int = 5,
    model_id: str = "M1",
) -> list[dict[str, Any]]:
    y_all = frame[outcome].to_numpy(float)
    w_all = frame[weight].to_numpy(float)
    models = [("BASELINE_NO_ADOPTION", None)] + [(b, b) for b in BOUNDARIES]
    rows: list[dict[str, Any]] = []
    for rep in range(repetitions):
        fold_id = assign_stratified_folds(frame, rep, folds)
        pred_by_model = {label: np.full(len(frame), np.nan) for label, _ in models}
        for fold in range(folds):
            train = frame.loc[fold_id != fold].copy()
            test = frame.loc[fold_id == fold].copy()
            train_pos = np.flatnonzero(fold_id != fold)
            test_pos = np.flatnonzero(fold_id == fold)
            for label, boundary in models:
                encoder = fit_encoder(train, model_id)
                Xtr, names, _, _ = design_matrix(train, model_id, encoder=encoder, adoption=boundary)
                Xte, names_te, _, _ = design_matrix(test, model_id, encoder=encoder, adoption=boundary)
                if names != names_te:
                    raise RuntimeError("Training/test design columns differ")
                fit = fit_wls(Xtr, y_all[train_pos], w_all[train_pos], names)
                pred_by_model[label][test_pos] = Xte @ fit.beta
        baseline_rmse = None
        for label, _ in models:
            pred = pred_by_model[label]
            if np.isnan(pred).any():
                raise RuntimeError("Cross-validation prediction is incomplete")
            rmse = weighted_rmse(y_all, pred, w_all)
            mae = weighted_mae(y_all, pred, w_all)
            if baseline_rmse is None:
                baseline_rmse = rmse
            rows.append({
                "repetition": rep + 1,
                "model": label,
                "folds": folds,
                "weighted_rmse": rmse,
                "weighted_mae": mae,
                "rmse_improvement_vs_baseline": 0.0 if label == "BASELINE_NO_ADOPTION" else float(baseline_rmse - rmse),
                "direction_better_than_baseline": bool(label != "BASELINE_NO_ADOPTION" and rmse < baseline_rmse),
            })
    return rows


def classify_low_performance(frame: pd.DataFrame, outcome: str, weight: str) -> tuple[np.ndarray, dict[str, float]]:
    low = np.zeros(len(frame), dtype=bool)
    thresholds: dict[str, float] = {}
    for source, idx in frame.groupby("country", sort=True).groups.items():
        pos = np.asarray(list(idx), dtype=int)
        y = frame.loc[pos, outcome].to_numpy(float)
        w = frame.loc[pos, weight].to_numpy(float)
        threshold = weighted_quantile_threshold(y, w, 0.20)
        low[pos] = y <= threshold
        thresholds[str(source)] = threshold
    return low, thresholds


def classification_metrics(truth: np.ndarray, screen_positive: np.ndarray, weights: np.ndarray) -> dict[str, float]:
    t = truth.astype(bool)
    s = screen_positive.astype(bool)
    w = weights.astype(float)
    tp = float(w[t & s].sum())
    fn = float(w[t & ~s].sum())
    fp = float(w[~t & s].sum())
    tn = float(w[~t & ~s].sum())
    recall = tp / (tp + fn) if tp + fn else float("nan")
    specificity = tn / (tn + fp) if tn + fp else float("nan")
    ppv = tp / (tp + fp) if tp + fp else float("nan")
    npv = tn / (tn + fn) if tn + fn else float("nan")
    fnr = 1 - recall
    fpr = 1 - specificity
    return {
        "balanced_error_rate": 0.5 * (fnr + fpr),
        "false_negative_rate": fnr,
        "false_positive_rate": fpr,
        "recall": recall,
        "specificity": specificity,
        "positive_predictive_value": ppv,
        "negative_predictive_value": npv,
        "target_share": float(w[s].sum() / w.sum()),
        "low_performance_share": float(w[t].sum() / w.sum()),
        "weighted_jaccard": tp / (tp + fp + fn) if tp + fp + fn else float("nan"),
    }


def targeting_analysis(
    frame: pd.DataFrame,
    outcome: str,
    bootstrap_reps: int = 4999,
    seed: int = BASE_SEED,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    truth, _ = classify_low_performance(frame, outcome, "W_PRIMARY_SOURCE_MEAN1")
    w = frame["W_PRIMARY_SOURCE_MEAN1"].to_numpy(float)
    metric_rows = []
    for b in BOUNDARIES:
        metrics = classification_metrics(truth, frame[b].eq(0).to_numpy(), w)
        metric_rows.append({"boundary": b, **metrics})

    pairs = [(0, 1, "integrated_vs_specialised"), (1, 2, "specialised_vs_digital"), (0, 2, "integrated_vs_digital")]
    boot_diffs = {label: [] for _, _, label in pairs}
    rng = np.random.default_rng(seed)
    source_positions = {s: np.asarray(list(idx), dtype=int) for s, idx in frame.groupby("country", sort=True).groups.items()}
    for _ in range(bootstrap_reps):
        sampled_positions = []
        for source in sorted(source_positions):
            idx = source_positions[source]
            sampled_positions.append(rng.choice(idx, size=len(idx), replace=True))
        pos = np.concatenate(sampled_positions)
        boot = frame.iloc[pos].reset_index(drop=True).copy()
        boot["W_PRIMARY_SOURCE_MEAN1"] = boot["base_wt"].astype(float) / boot.groupby("country")["base_wt"].transform("mean")
        low, _ = classify_low_performance(boot, outcome, "W_PRIMARY_SOURCE_MEAN1")
        bw = boot["W_PRIMARY_SOURCE_MEAN1"].to_numpy(float)
        bers = [classification_metrics(low, boot[b].eq(0).to_numpy(), bw)["balanced_error_rate"] for b in BOUNDARIES]
        for i, j, label in pairs:
            boot_diffs[label].append(bers[i] - bers[j])

    pair_rows = []
    raw_p = []
    observed_bers = [r["balanced_error_rate"] for r in metric_rows]
    for i, j, label in pairs:
        arr = np.asarray(boot_diffs[label], dtype=float)
        observed = observed_bers[i] - observed_bers[j]
        p = 2 * min((np.sum(arr <= 0) + 1) / (len(arr) + 1), (np.sum(arr >= 0) + 1) / (len(arr) + 1))
        p = float(min(1.0, p))
        raw_p.append(p)
        pair_rows.append({
            "contrast": label,
            "observed_ber_difference": float(observed),
            "bootstrap_reps": bootstrap_reps,
            "percentile_ci_low": float(np.quantile(arr, 0.025)),
            "percentile_ci_high": float(np.quantile(arr, 0.975)),
            "p_unadjusted": p,
        })
    adjusted = holm_adjust(raw_p)
    for row, p_adj in zip(pair_rows, adjusted):
        row["p_holm"] = p_adj
        row["significant_at_0_05"] = bool(p_adj < 0.05)
    return metric_rows, pair_rows


def heterogeneity_frame(primary: pd.DataFrame, moderator: str) -> pd.DataFrame:
    d = primary.copy()
    if moderator == "size_band":
        d = d.loc[d["s7"].ge(5)].copy()
        d["size_band"] = pd.cut(
            d["s7"].astype(float),
            bins=[5 - 1e-12, 20, 100, np.inf],
            labels=["5_19", "20_99", "100_PLUS"],
            right=False,
        ).astype(str)
    elif moderator == "foreign_owner":
        a3b = pd.to_numeric(d["a3b"], errors="coerce")
        d = d.loc[a3b.between(0, 100)].copy()
    elif moderator == "sector_pooled":
        pass
    else:
        raise ValueError(moderator)
    return d.reset_index(drop=True)


def heterogeneity_omnibus(primary: pd.DataFrame, outcome: str, weight: str) -> list[dict[str, Any]]:
    results = []
    raw_p = []
    for moderator in ["size_band", "foreign_owner", "sector_pooled"]:
        frame = heterogeneity_frame(primary, moderator)
        y = frame[outcome].to_numpy(float)
        w = frame[weight].to_numpy(float)
        theta_parts: list[float] = []
        psi_parts: list[np.ndarray] = []
        term_labels: list[str] = []
        for boundary in BOUNDARIES:
            X, names, _, inter_names = design_matrix(frame, "M1", adoption=boundary, moderator=moderator)
            fit = fit_wls(X, y, w, names)
            for term in inter_names:
                idx = names.index(term)
                theta_parts.append(float(fit.beta[idx]))
                psi_parts.append(fit.hc3_influence[:, idx])
                term_labels.append(f"{boundary}:{term}")
        theta = np.asarray(theta_parts)
        psi = np.column_stack(psi_parts)
        cov = psi.T @ psi
        if len(theta) == 0:
            raise RuntimeError(f"No interaction terms for {moderator}")
        stat = float(theta.T @ np.linalg.pinv(cov) @ theta)
        df = int(np.linalg.matrix_rank(cov))
        p = float(stats.chi2.sf(stat, df))
        raw_p.append(p)
        results.append({
            "moderator": moderator,
            "n": len(frame),
            "interaction_terms": len(theta),
            "joint_wald_chi2": stat,
            "df": df,
            "p_unadjusted": p,
            "follow_up_family": "interaction coefficients versus reference, Holm within moderator if BH gate opens",
        })
    q = bh_adjust(raw_p)
    for row, qv in zip(results, q):
        row["p_bh_across_three_moderators"] = qv
        row["bh_q_0_10_gate_open"] = bool(qv <= 0.10)
    return results


def robustness_grid(full: pd.DataFrame, primary: pd.DataFrame) -> list[dict[str, Any]]:
    variants = [
        ("P0_PRIMARY", "PRIMARY_S60_N200", "Y_PRIMARY_RAW", "W_PRIMARY_SOURCE_MEAN1", "M1", "PRIMARY"),
        ("R01_OUTCOME_Z_SOURCE", "PRIMARY_S60_N200", "Y_ROBUST_Z_SOURCE", "W_PRIMARY_SOURCE_MEAN1", "M1", "OUTCOME"),
        ("R02_OUTCOME_WINSOR_1_99", "PRIMARY_S60_N200", "Y_ROBUST_WINSOR_1_99", "W_PRIMARY_SOURCE_MEAN1", "M1", "OUTCOME"),
        ("R03_SAMPLE_STRICT", "STRICT_S80_N200", "Y_PRIMARY_RAW", "W_PRIMARY_SOURCE_MEAN1", "M1", "SAMPLE"),
        ("R04_SAMPLE_BROAD", "BROAD_AVAILABLE_N20", "Y_PRIMARY_RAW", "W_PRIMARY_SOURCE_MEAN1", "M1", "SAMPLE"),
        ("R05_SAMPLE_S7_GE5", "PRIMARY_S7_GE5", "Y_PRIMARY_RAW", "W_PRIMARY_SOURCE_MEAN1", "M1", "SAMPLE"),
        ("R06_WEIGHT_UNWEIGHTED", "PRIMARY_S60_N200", "Y_PRIMARY_RAW", "W_SENS_UNWEIGHTED", "M1", "WEIGHT"),
        ("R07_WEIGHT_EQUAL_SOURCE", "PRIMARY_S60_N200", "Y_PRIMARY_RAW", "W_SENS_EQUAL_SOURCE", "M1", "WEIGHT"),
        ("R08_WEIGHT_EQUAL_COUNTRY", "PRIMARY_S60_N200", "Y_PRIMARY_RAW", "W_SENS_EQUAL_REPORTING_COUNTRY", "M1", "WEIGHT"),
        ("R09_WEIGHT_RAW", "PRIMARY_S60_N200", "Y_PRIMARY_RAW", "W_SENS_RAW", "M1", "WEIGHT"),
        ("R10_WEIGHT_CAP99", "PRIMARY_S60_N200", "Y_PRIMARY_RAW", "W_SENS_SOURCE_MEAN1_CAP99", "M1", "WEIGHT"),
        ("R11_CONTROLS_M0", "PRIMARY_S60_N200", "Y_PRIMARY_RAW", "W_PRIMARY_SOURCE_MEAN1", "M0", "CONTROLS"),
        ("R12_CONTROLS_M1_NO_SIZE", "PRIMARY_S60_N200", "Y_PRIMARY_RAW", "W_PRIMARY_SOURCE_MEAN1", "M1_NO_SIZE", "CONTROLS"),
        ("R13_CONTROLS_M2", "PRIMARY_S60_N200", "Y_PRIMARY_RAW", "W_PRIMARY_SOURCE_MEAN1", "M2", "CONTROLS"),
        ("R14_DENOMINATOR_E1_MATCHED", "MATCHED_E1_DENOMINATOR", "Y_SENS_E1", "W_PRIMARY_SOURCE_MEAN1", "M1", "DENOMINATOR"),
        ("R15_DENOMINATOR_COMPONENT_MATCHED", "MATCHED_COMPONENT_DENOMINATOR", "Y_SENS_COMPONENT", "W_PRIMARY_SOURCE_MEAN1", "M1", "DENOMINATOR"),
    ]
    rows: list[dict[str, Any]] = []
    for variant, sample_id, outcome, weight, model, axis in variants:
        if sample_id == "PRIMARY_S60_N200":
            frame = primary.copy()
        else:
            frame = build_sample(full, sample_id)
            frame = add_outcomes_and_weights(frame, primary_reference=primary)
            # Preserve the frozen primary-sample weights on matched denominator subsets.
            if sample_id in {"MATCHED_E1_DENOMINATOR", "MATCHED_COMPONENT_DENOMINATOR"}:
                weight_map = primary.set_index(["country", "firmid"])["W_PRIMARY_SOURCE_MEAN1"]
                frame["W_PRIMARY_SOURCE_MEAN1"] = [weight_map.loc[(c, int(fid))] for c, fid in zip(frame["country"], frame["firmid"])]
        system = association_system(frame, model, outcome, weight)
        global_result = system["global_equality"]
        for coef in system["coefficient_rows"]:
            rows.append({
                "variant_id": variant,
                "one_axis": axis,
                "sample_id": sample_id,
                "outcome_id": outcome,
                "weight_id": weight,
                "model_id": model,
                "n": len(frame),
                "boundary": coef["boundary"],
                "estimate_log_points_or_standard_units": coef["estimate_log_points"],
                "se_hc3": coef["se_hc3"],
                "p_hc3_unadjusted": coef["p_hc3_unadjusted"],
                "global_equality_chi2": global_result["wald_chi2"],
                "global_equality_df": global_result["df"],
                "global_equality_p": global_result["p_value"],
                "status": "MANDATORY_REPORT_NO_SELECTIVE_OMISSION",
            })
    return rows


def build_manifest(root: Path) -> None:
    files = sorted(p for p in root.rglob("*") if p.is_file() and p.name not in {"MANIFEST.csv", "SHA256SUMS.txt"})
    rows = []
    sums = []
    for p in files:
        rel = p.relative_to(root).as_posix()
        digest = sha256_file(p)
        rows.append({"path": rel, "size_bytes": p.stat().st_size, "sha256": digest})
        sums.append(f"{digest}  {rel}")
    write_csv(root / "MANIFEST.csv", rows, ["path", "size_bytes", "sha256"])
    (root / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8")


def run_analysis(
    full: pd.DataFrame,
    protocol: dict[str, Any],
    out_dir: Path,
    *,
    test_mode: bool = False,
    cv_repetitions: int = 20,
    classification_bootstrap_reps: int = 4999,
) -> dict[str, Any]:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    full = prepare_full_frame(full)
    primary = build_sample(full, "PRIMARY_S60_N200")
    if not test_mode:
        if len(primary) != EXPECTED_PRIMARY_N:
            raise RuntimeError(f"Primary sample N mismatch: {len(primary)}")
        fp = sample_fingerprint(primary)
        if fp != EXPECTED_PRIMARY_MEMBERSHIP_SHA256:
            raise RuntimeError(f"Primary sample membership hash mismatch: {fp}")
    else:
        fp = sample_fingerprint(primary)
    primary = add_outcomes_and_weights(primary)

    association = association_system(primary, "M1", "Y_PRIMARY_RAW", "W_PRIMARY_SOURCE_MEAN1")
    write_csv(out_dir / "01_PRIMARY_ASSOCIATION.csv", association["coefficient_rows"])
    write_json(out_dir / "02_PRIMARY_EQUALITY_TEST.json", {
        "primary_global_equality": association["global_equality"],
        "pairwise_gate": "Pairwise Holm-adjusted contrasts are confirmatory only if the global equality p-value is below 0.05.",
        "joint_hc3_covariance": association["joint_hc3_covariance"].tolist(),
    })
    write_csv(out_dir / "03_PRIMARY_PAIRWISE_CONTRASTS.csv", association["pairwise_rows"])
    write_csv(out_dir / "04_SOURCE_CLUSTER_SENSITIVITY.csv", association["cluster_rows"])
    write_json(out_dir / "05_SOURCE_CLUSTER_GLOBAL_TEST.json", association["cluster_global_equality"])
    write_csv(out_dir / "06_LEAVE_ONE_SOURCE_OUT.csv", leave_one_source_out(primary, "Y_PRIMARY_RAW", "W_PRIMARY_SOURCE_MEAN1"))

    press_rows = press_prediction(primary, "Y_PRIMARY_RAW", "W_PRIMARY_SOURCE_MEAN1")
    write_csv(out_dir / "07_PREDICTION_PRESS.csv", press_rows)
    cv_rows = repeated_cross_validation(
        primary,
        "Y_PRIMARY_RAW",
        "W_PRIMARY_SOURCE_MEAN1",
        repetitions=cv_repetitions,
        folds=5,
    )
    write_csv(out_dir / "08_PREDICTION_REPEATED_5FOLD.csv", cv_rows)
    stability = []
    cvdf = pd.DataFrame(cv_rows)
    baseline = cvdf.loc[cvdf["model"].eq("BASELINE_NO_ADOPTION"), ["repetition", "weighted_rmse"]].rename(columns={"weighted_rmse": "baseline_rmse"})
    for boundary in BOUNDARIES:
        sub = cvdf.loc[cvdf["model"].eq(boundary)].merge(baseline, on="repetition")
        improvements = sub["baseline_rmse"] - sub["weighted_rmse"]
        stability.append({
            "boundary": boundary,
            "repetitions": cv_repetitions,
            "better_than_baseline_repetitions": int((improvements > 0).sum()),
            "stability_gate_16_of_20_or_scaled_test_mode": bool((improvements > 0).sum() >= (16 if cv_repetitions == 20 else math.ceil(0.8 * cv_repetitions))),
            "median_rmse_improvement": float(improvements.median()),
            "p10_rmse_improvement": float(improvements.quantile(0.10)),
            "p90_rmse_improvement": float(improvements.quantile(0.90)),
            "formal_p_value": None,
        })
    write_csv(out_dir / "09_PREDICTION_STABILITY.csv", stability)

    target_metrics, target_pairs = targeting_analysis(
        primary,
        "Y_PRIMARY_RAW",
        bootstrap_reps=classification_bootstrap_reps,
        seed=BASE_SEED,
    )
    write_csv(out_dir / "10_TARGETING_CLASSIFICATION_METRICS.csv", target_metrics)
    write_csv(out_dir / "11_TARGETING_BER_PAIRWISE_BOOTSTRAP.csv", target_pairs)

    heterogeneity = heterogeneity_omnibus(primary, "Y_PRIMARY_RAW", "W_PRIMARY_SOURCE_MEAN1")
    write_csv(out_dir / "12_HETEROGENEITY_OMNIBUS.csv", heterogeneity)

    robustness = robustness_grid(full, primary)
    write_csv(out_dir / "13_ROBUSTNESS_GRID.csv", robustness)

    state = {
        "schema_version": "1.0",
        "phase": "E4 — authorised execution",
        "test_mode": test_mode,
        "primary_n": len(primary),
        "primary_membership_sha256": fp,
        "protocol_status": protocol["status"],
        "claim_ceiling": "descriptive_associational_predictive_only",
        "max_branch": "SUSPENDED",
        "raw_or_row_level_outputs_written": False,
        "source_rankings_written": False,
        "classification_bootstrap_reps": classification_bootstrap_reps,
        "cv_repetitions": cv_repetitions,
    }
    write_json(out_dir / "E4_EXECUTION_STATE.json", state)
    build_manifest(out_dir)
    return state


def synthetic_fixture(n_per_source: int = 125, seed: int = BASE_SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    fid = 1
    for s_idx, source in enumerate(PRIMARY_SOURCES):
        for i in range(n_per_source):
            state = int(rng.choice([1, 2, 3, 4, 5], p=[0.32, 0.42, 0.03, 0.15, 0.08]))
            s7 = float(max(5, round(np.exp(rng.normal(3.1 + 0.08 * s_idx, 0.8)))))
            latent = 9.0 + 0.04 * state + 0.12 * math.log(s7) + 0.1 * s_idx + rng.normal(0, 0.7)
            e6a = float(math.exp(latent) * s7)
            onehot = {f"ib9b{k}": int(k == state) for k in range(1, 6)}
            a3b = float(rng.choice([0, 0, 0, 20, 60, 100, np.nan]))
            a6 = float(rng.integers(1950, 2023)) if rng.random() > 0.02 else np.nan
            region = int(rng.integers(1, 5))
            e1 = s7 * float(rng.uniform(0.8, 1.2))
            comps = np.array([0.45, 0.25, 0.2, 0.1]) * e1
            rows.append({
                "firmid": fid,
                "country": source,
                "region_id": region,
                "a5a": int(rng.choice([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 101, 102])),
                "s4": int(rng.choice([0, 1])),
                "s7": s7,
                "a3b": a3b,
                "a6": a6,
                "a7a": float(rng.integers(0, 55)) if rng.random() > 0.04 else np.nan,
                "a7b": int(rng.choice([1, 2])) if rng.random() > 0.03 else np.nan,
                "a7c": int(rng.integers(1, 7)) if rng.random() > 0.04 else np.nan,
                "a7d": int(rng.choice([1, 2])) if rng.random() > 0.05 else np.nan,
                "e1": e1,
                "e1a": comps[0], "e1b": comps[1], "e1c": comps[2], "e1d": comps[3],
                "e6a": e6a,
                "base_wt": float(np.exp(rng.normal(0, 0.7))),
                **onehot,
            })
            fid += 1
    return pd.DataFrame(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--protocol", type=Path, required=True)
    ap.add_argument("--expected-e3-protocol-sha256")
    ap.add_argument("--microdata", type=Path)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--authorisation-token")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--cv-repetitions", type=int, default=20)
    ap.add_argument("--classification-bootstrap-reps", type=int, default=4999)
    args = ap.parse_args()

    protocol, protocol_hash = load_protocol(args.protocol, args.expected_e3_protocol_sha256)
    if args.self_test:
        frame = synthetic_fixture()
        state = run_analysis(
            frame,
            protocol,
            args.out_dir,
            test_mode=True,
            cv_repetitions=min(args.cv_repetitions, 2),
            classification_bootstrap_reps=min(args.classification_bootstrap_reps, 99),
        )
        print("E4_SYNTHETIC_SELF_TEST_PASS")
        print(json.dumps(state, sort_keys=True))
        return 0

    if args.authorisation_token != AUTHORISATION_TOKEN:
        raise SystemExit("Real-data execution refused: missing exact E4 authorisation token")
    if not args.expected_e3_protocol_sha256:
        raise SystemExit("Real-data execution refused: exact E3 protocol hash is required")
    if not args.microdata:
        raise SystemExit("Real-data execution refused: --microdata is required")
    frame = load_real_microdata(args.microdata)
    state = run_analysis(
        frame,
        protocol,
        args.out_dir,
        test_mode=False,
        cv_repetitions=args.cv_repetitions,
        classification_bootstrap_reps=args.classification_bootstrap_reps,
    )
    state["e3_protocol_sha256"] = protocol_hash
    write_json(args.out_dir / "E4_EXECUTION_STATE.json", state)
    build_manifest(args.out_dir)
    print("E4_AUTHORISED_EXECUTION_COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
