#!/usr/bin/env python3
"""Reproduce transfer results from the pinned FAT archive and publication aggregates.

This public route needs no private parity-reference CSV. It reconstructs cells
with the independent raw-row implementation and allocates with the unchanged
exact-arithmetic engine. Newly generated cells and full scores remain private.
"""
import argparse
import csv
from decimal import Decimal
from fractions import Fraction as F
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent
PROTOCOL_SHA="80c5d6d9d69cbb38901ee1f169acc9d912ac11a3d1fb1604aa46037c6f3418bb"


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec)
    sys.modules[name]=m;spec.loader.exec_module(m);return m


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path):
    with path.open(encoding="utf-8-sig",newline="") as h:return list(csv.DictReader(h))


def run(raw,output,reported):
    if output.exists():raise ValueError("Choose a new private output directory")
    protocol=ROOT/"protocol/H1_PROTOCOL.json"
    if sha(protocol)!=PROTOCOL_SHA:raise ValueError("Frozen H1 protocol differs")
    independent=load("papere_public_independent_rows",ROOT/"verify_empirical_rows.py")
    engine=load("papere_public_exact_engine",ROOT/"engine/holdout_engine.py")
    contract,sources,cells,quantiles=independent.reference(raw,protocol)
    data={}
    for source in sorted(sources):
        ordered=sorted((x for x in cells if x["source"]==source),key=lambda x:x["state"])
        data[source]=tuple(engine.Cell(x["n"],x["n_cases"],F(format(x["weight_mass"],".18f")),
                                      F(format(x["case_mass"],".18f"))) for x in ordered)
    primary={s:data[s] for s in contract["primary_sources"]}
    targets={s:data[s] for s in contract["excluded_primary_targets"]}
    def csv_payload(subset):
        stream=io.StringIO(newline="");writer=csv.writer(stream,lineterminator="\n")
        writer.writerow(("source","state","n","n_cases","weight_mass","case_mass"))
        for s,group in sorted(subset.items()):
            for state,c in enumerate(group,1):
                masses=[format(Decimal(v.numerator)/Decimal(v.denominator),".18f") for v in (c.weight,c.cases)]
                writer.writerow((s,state,c.n,c.n_cases,*masses))
        return stream.getvalue().encode()
    primary_bytes=csv_payload(primary);target_bytes=csv_payload(targets)
    countries={s:independent.country(s) for s in data}
    provenance="Pinned original FAT input reconstructed with independent raw-row implementation; exact frozen allocation engine."
    exposure=contract["known_prior_exposure"]
    common={"evidence_type":"empirical","provenance":provenance,"prior_exposure":exposure}
    output.mkdir(parents=True)
    engine.write_json(output/"PUBLIC_ROUTE_STATUS.json",{"status":"RUNNING","public_release_approved":False})
    try:
        lock=engine.fit(primary,{s:countries[s] for s in primary},PROTOCOL_SHA,
                        input_sha256=hashlib.sha256(primary_bytes).hexdigest(),**common)
        # The all-primary coding is committed before either excluded source is scored.
        engine.write_json(output/"ALL_PRIMARY_TRAINING_LOCK.json",lock)
        target=engine.score(lock,targets,{s:countries[s] for s in targets},PROTOCOL_SHA,
                            country_disjoint=True,**common)
        source=engine.crossvalidate(primary,{s:countries[s] for s in primary},PROTOCOL_SHA,"source",**common)
        country=engine.crossvalidate(primary,{s:countries[s] for s in primary},PROTOCOL_SHA,"country",**common)
        reports={"SOURCE_TRANSFER.json":source,"COUNTRY_TRANSFER.json":country,"EXCLUDED_PRIMARY_TRANSFER.json":target}
        for name,value in reports.items():engine.write_json(output/name,value)
        private=output/"private_source_cells";private.mkdir()
        for name,payload in (("primary",primary_bytes),("excluded_primary",target_bytes)):
            # The generated local cells are not candidates for public redistribution.
            (private/(name+"_cells.csv")).write_bytes(payload)
        maxima={};checks=0
        def close(label,actual,expected):
            nonlocal checks
            if actual is None or expected in (None,""):
                if actual is not None or expected not in (None,""):raise ValueError("Missing-value mismatch: "+label)
                return
            error=abs(float(actual)-float(expected));maxima[label]=max(maxima.get(label,0.),error);checks+=1
            if error>1e-9:raise ValueError("Publication aggregate mismatch: "+label)
        summary={}
        for route,report in (("source_holdout",source),("country_holdout",country)):
            for row in report["summary"]:
                summary[(route,row["aggregation"],F(row["quota"]),row["policy"])]=row
        for row in read_csv(reported/"transfer_summaries.csv"):
            actual=summary[(row["route"],row["aggregation"],F(row["quota"]),row["policy"])]
            for k,v in actual.items():
                if isinstance(v,(F,int,float)) and k in row:close("summary_"+k,v,row[k])
        scores={(r["source"],F(r["quota"]),r["policy"]):r for report in (source,target) for r in report["results"]}
        q50=read_csv(reported/"within_source_quota_50_percent.csv")
        for row in q50:
            for policy in engine.FIXED.keys() | {"train_selected_three_block"}:
                actual=scores[(row["source"],F(".5"),policy)]
                for suffix,key in (("_yield_per_100_expected_contacts","cases_per_100_expected_contacts"),
                                   ("_yield_delta_vs_five","yield_delta_vs_five"),
                                   ("_composition_tv_vs_five_pp","composition_tv_vs_five_pp")):
                    close("q50"+suffix,actual[key],row[policy+suffix])
        for row in read_csv(reported/"excluded_primary_all_quotas.csv"):
            actual=scores[(row["source"],F(row["quota"]),row["policy"])]
            for key in ("cases_per_100_expected_contacts","yield_delta_vs_five","yield_delta_vs_digital","composition_tv_vs_five_pp"):
                close("target_"+key,actual[key],row[key])
        for name,value in reports.items():
            with (output/name).open("rb") as handle:os.fsync(handle.fileno())
            if json.loads((output/name).read_text())!=engine.jsonable(value):
                raise ValueError("Incomplete result readback: "+name)
        for name,expected in (("primary",60),("excluded_primary",10)):
            with (private/(name+"_cells.csv")).open(newline="") as handle:
                if len(list(csv.DictReader(handle)))!=expected:raise ValueError("Incomplete private cell readback")
        receipt={"status":"PUBLIC_RAW_RECOMPUTATION_PASS","scope":"RETROSPECTIVE_TRANSFER_FROM_PINNED_RAW_NO_PRIVATE_PARITY_INPUTS",
                 "raw_sha256":sha(raw),"protocol_sha256":PROTOCOL_SHA,
                 "direct_raw_script_sha256":sha(Path(__file__)),"independent_reader_sha256":sha(ROOT/"verify_empirical_rows.py"),
                 "exact_engine_sha256":sha(ROOT/"engine/holdout_engine.py"),
                 "numeric_checks_against_publication_aggregates":checks,"maximum_absolute_errors":maxima,
                 "absolute_tolerance":1e-9,"source_policy_quota_rows":sum(len(x["results"]) for x in reports.values()),
                 "summary_rows":len(summary),"source_state_cells_private":len(cells),
                 "source_weight_scale_flags":sum(x["scale_membership_difference_n"]>0 for x in quantiles),
                 "private_canonical_39_parity_checks_repeated":False,
                 "row_level_outputs_written":False,"public_release_approved":False,
                 "note":"Numerical comparison, not byte identity with the canonical provenance-bearing records. The canonical39-reference check remains archived privately."}
        engine.write_json(output/"PUBLIC_ROUTE_STATUS.json",receipt)
        for path in output.rglob("*"):
            if path.is_file():
                with path.open("rb") as handle:os.fsync(handle.fileno())
        if json.loads((output/"PUBLIC_ROUTE_STATUS.json").read_text())!=receipt:
            raise ValueError("Incomplete status readback")
        return receipt
    except Exception as exc:
        engine.write_json(output/"PUBLIC_ROUTE_STATUS.json",{"status":"FAILED_NO_COMPLETE_REPRODUCTION_CLAIM","reason":str(exc)})
        raise


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--microdata",required=True,type=Path);p.add_argument("--output",required=True,type=Path)
    p.add_argument("--reported",type=Path,default=ROOT.parent/"reported_results/transfer")
    a=p.parse_args();r=run(a.microdata.resolve(),a.output.resolve(),a.reported.resolve())
    print(json.dumps({"status":r["status"],"numeric_checks":r["numeric_checks_against_publication_aggregates"],"max_error":max(r["maximum_absolute_errors"].values())}))
