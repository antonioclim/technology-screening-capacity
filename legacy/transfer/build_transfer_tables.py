#!/usr/bin/env python3
"""Rebuild supplement CSV panels from the supplied H2 publication aggregates."""
import argparse,csv
from pathlib import Path

def read(path):
    with path.open(encoding="utf-8-sig",newline="") as handle:return list(csv.DictReader(handle))

def write(path,rows,fields):
    with path.open("w",encoding="utf-8-sig",newline="") as handle:
        out=csv.DictWriter(handle,fieldnames=fields,lineterminator="\n");out.writeheader();out.writerows(rows)

def build(inputs,output):
    if output.exists():raise ValueError("Choose a new output directory")
    summary=read(inputs/"transfer_summaries.csv")
    targets=read(inputs/"excluded_primary_all_quotas.csv")
    q50=read(inputs/"within_source_quota_50_percent.csv")
    assert len(summary)==64 and len(targets)==32 and len(q50)==14
    output.mkdir(parents=True)
    five={r["quota"]:r for r in summary if r["route"]=="source_holdout" and r["aggregation"]=="equal_source" and r["policy"]=="five_states"}
    s2=[]
    for r in summary:
        if r["route"]!="source_holdout" or r["aggregation"]!="equal_source":continue
        s2.append({"quota":r["quota"],"policy":r["policy"],"yield_per_100_expected_weighted_contacts":r["cases_per_100_expected_contacts"],"yield_loss_vs_five":-float(r["yield_delta_vs_five"]),"mean_composition_distance_pp":r["composition_tv_vs_five_pp"]})
    write(output/"Table_S2_source_transfer.csv",s2,list(s2[0]))
    s3=[]
    for source in sorted({r["source"] for r in targets}):
        for quota in ("0.20","0.35","0.50","0.75"):
            d={r["policy"]:r for r in targets if r["source"]==source and r["quota"]==quota}
            row={"source":source,"quota":quota}
            for p in ("five_states","digital","train_selected_three_block","population_lottery"):row[p+"_yield"]=d[p]["cases_per_100_expected_contacts"]
            row["three_group_loss_vs_five"]=-float(d["train_selected_three_block"]["yield_delta_vs_five"])
            row["three_group_composition_distance_pp"]=d["train_selected_three_block"]["composition_tv_vs_five_pp"]
            s3.append(row)
    write(output/"Table_S3_excluded_sources.csv",s3,list(s3[0]))
    s4=[]
    for r in q50:
        if r["cohort_role"]!="primary":continue
        s4.append({"source":r["source"],"eligible_n":r["eligible_n"],"selected_partition":r["selected_partition"],"digital_loss_vs_five":-float(r["digital_yield_delta_vs_five"]),"three_group_loss_vs_five":-float(r["train_selected_three_block_yield_delta_vs_five"]),"digital_composition_distance_pp":r["digital_composition_tv_vs_five_pp"],"three_group_composition_distance_pp":r["train_selected_three_block_composition_tv_vs_five_pp"]})
    assert len(s2)==16 and len(s3)==8 and len(s4)==12
    write(output/"Table_S4_source_heterogeneity.csv",s4,list(s4[0]))
    country=[r for r in summary if r["route"]=="country_holdout" and r["aggregation"]=="equal_country_within_country_equal_source"]
    fields=("quota","policy","cases_per_100_expected_contacts","yield_delta_vs_five","composition_tv_vs_five_pp")
    write(output/"Country_transfer_summary.csv",[{k:r[k] for k in fields} for r in country],fields)
    return {"S2":len(s2),"S3":len(s3),"S4":len(s4),"country":len(country)}

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--inputs",required=True,type=Path);p.add_argument("--output",required=True,type=Path);a=p.parse_args();print(build(a.inputs,a.output))
