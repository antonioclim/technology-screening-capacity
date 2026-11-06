#!/usr/bin/env python3
"""Summarise locked H4 aggregate scores without refitting or selecting models."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from run_h4_pilot import PROTOCOL_SHA,ADDENDUM_SHA,write_csv,write_json,require


CORE_CONTRASTS=[('MOST5_increment','B_MOST5','B'),('MAX5_vs_MOST5','B_MAX5','B_MOST5'),
                ('MOST_detail_vs_binary','B_MOST5','B_MOST_binary'),('MAX_detail_vs_binary','B_MAX5','B_MAX_binary'),
                ('MAX_addition_to_MOST','B_MOST5_MAX5','B_MOST5'),
                ('MOST_learned_vs_fixed','learned_MOST5','fixed_MOST5'),('MAX_learned_vs_fixed','learned_MAX5','fixed_MAX5'),
                ('MOST5_increment_with_size','B_SIZE_MOST5','B_SIZE'),('MAX5_increment_with_size','B_SIZE_MAX5','B_SIZE')]


def finite_record(record):
    result={}
    for key,value in record.items():
        if isinstance(value,np.generic):value=value.item()
        if isinstance(value,float) and not np.isfinite(value):value=None
        result[key]=value
    return result


def summarise(run,output):
    status=json.loads((run/'RUN_STATUS.json').read_text())
    require(status['status']=='PASS','Cannot summarise an incomplete empirical run')
    require(status['protocol_sha256']==PROTOCOL_SHA and status['addendum_A01_sha256']==ADDENDUM_SHA,'Protocol identity mismatch')
    require(not output.exists(),'Use a new output directory')
    output.mkdir(parents=True)
    raw=pd.read_csv(run/'source_policy_quota_results.csv')
    country_keys=['cohort','route','country','policy','quota']
    metric_columns=['cases_per_100_expected_contacts','event_prevalence_percent','event_recall_percent',
                    'yield_delta_vs_lottery','yield_delta_vs_B','sector_composition_tv_vs_B_pp',
                    'employment_composition_tv_vs_B_pp','MOST_composition_tv_vs_B_pp','MAX_composition_tv_vs_B_pp']
    country=raw.groupby(country_keys,sort=True)[metric_columns].mean().reset_index()
    country['source_count']=raw.groupby(country_keys).size().to_numpy()
    mass=raw.groupby(country_keys)[['n','expected_weighted_contacts','expected_weighted_cases']].sum().reset_index()
    country=country.merge(mass,on=country_keys,validate='one_to_one')
    country['contact_weighted_yield']=100*country.expected_weighted_cases/country.expected_weighted_contacts
    write_csv(output/'country_policy_quota_results.csv',[finite_record(r) for r in country.to_dict('records')])
    primary=country.loc[country.route.eq('country_holdout')]
    summaries=[]
    for key,g in primary.groupby(['cohort','policy','quota'],sort=True):
        require(len(g)==11,'Expected eleven country scores for every primary policy/quota')
        row=dict(zip(['cohort','policy','quota'],key));row['country_n']=len(g)
        for metric in metric_columns:
            row[metric+'_country_mean']=float(g[metric].mean())
            row[metric+'_country_min']=float(g[metric].min())
            row[metric+'_country_max']=float(g[metric].max())
        summaries.append(row)
    write_csv(output/'equal_country_policy_summaries.csv',summaries)
    contrasts=CORE_CONTRASTS+[(p+'_vs_lottery',p,'lottery') for p in status['policies']]
    paired=[]
    for (cohort,route,ct,q),g in country.groupby(['cohort','route','country','quota'],sort=True):
        by_policy=g.set_index('policy')
        for name,left,right in contrasts:
            a=by_policy.loc[left];b=by_policy.loc[right]
            paired.append({'cohort':cohort,'route':route,'country':ct,'quota':q,'contrast':name,
                           'left_policy':left,'right_policy':right,
                           'left_yield_per_100_contacts':float(a.cases_per_100_expected_contacts),
                           'right_yield_per_100_contacts':float(b.cases_per_100_expected_contacts),
                           'paired_yield_difference':float(a.cases_per_100_expected_contacts-b.cases_per_100_expected_contacts)})
    write_csv(output/'country_paired_contrasts.csv',paired)
    paired_df=pd.DataFrame(paired);summaries=[]
    for key,g in paired_df.loc[paired_df.route.eq('country_holdout')].groupby(['cohort','quota','contrast','left_policy','right_policy'],sort=True):
        values=g.paired_yield_difference.to_numpy(float)
        require(len(values)==11,'Incomplete country contrast')
        row=dict(zip(['cohort','quota','contrast','left_policy','right_policy'],key))
        row.update(equal_country_mean=float(values.mean()),country_min=float(values.min()),country_max=float(values.max()),
                   positive_countries=int((values>0).sum()),exact_zero_countries=int((values==0).sum()),negative_countries=int((values<0).sum()),country_n=11)
        summaries.append(row)
    write_csv(output/'equal_country_contrast_summaries.csv',summaries)
    # Direct MAX/MOST distribution contrasts use the same source, cohort and quota.
    group=pd.read_csv(run/'group_contact_results.csv',dtype={'group':str})
    group_keys=['cohort','route','source','country','quota','dimension','group']
    selected=group.loc[group.policy.isin(['B_MOST5','B_MAX5'])]
    shares=selected.pivot(index=group_keys,columns='policy',values='expected_contact_share_percent').reset_index()
    rates=selected.pivot(index=group_keys,columns='policy',values='within_group_contact_rate_percent').reset_index()
    require(shares[group_keys].equals(rates[group_keys]),'Share/rate distribution keys are misaligned')
    distribution=[]
    for (_,s),(_,r) in zip(shares.iterrows(),rates.iterrows()):
        row={k:s[k] for k in group_keys}
        row.update(MOST_contact_share_percent=float(s['B_MOST5']),MAX_contact_share_percent=float(s['B_MAX5']),
                   MAX_minus_MOST_share_pp=float(s['B_MAX5']-s['B_MOST5']),
                   MOST_group_contact_rate_percent=float(r['B_MOST5']),MAX_group_contact_rate_percent=float(r['B_MAX5']),
                   MAX_minus_MOST_group_rate_pp=float(r['B_MAX5']-r['B_MOST5']))
        distribution.append(row)
    write_csv(output/'MAX_MOST_group_differences.csv',distribution)
    dist=pd.DataFrame(distribution)
    tv=dist.groupby(['cohort','route','source','country','quota','dimension']).MAX_minus_MOST_share_pp.apply(lambda x:float(np.abs(x).sum()/2)).reset_index(name='composition_tv_pp')
    write_csv(output/'MAX_MOST_source_composition_distance.csv',[finite_record(r) for r in tv.to_dict('records')])
    # A01 common-cohort allocation differences: average sources within India,
    # then countries equally. No actual realised-list overlap is inferred.
    cross=pd.read_csv(run/'cross_target_allocation.csv')
    columns=['expected_allocation_tv_pp','sector_composition_tv_pp','employment_composition_tv_pp',
             'productivity_yield_per_100_contacts','finance_yield_per_100_contacts',
             'productivity_yield_delta_vs_B','finance_yield_delta_vs_B']
    cross_country=cross.groupby(['route','country','policy','quota'])[columns].mean().reset_index()
    write_csv(output/'paired_objectives_country_results.csv',[finite_record(r) for r in cross_country.to_dict('records')])
    cross_summary=[]
    for key,g in cross_country.loc[cross_country.route.eq('country_holdout')].groupby(['policy','quota']):
        row=dict(zip(['policy','quota'],key));row['country_n']=len(g)
        for metric in columns:
            row[metric+'_country_mean']=float(g[metric].mean());row[metric+'_country_min']=float(g[metric].min());row[metric+'_country_max']=float(g[metric].max())
        cross_summary.append(row)
    write_csv(output/'paired_objectives_equal_country_summaries.csv',cross_summary)
    receipt={'status':'PASS','scope':'Prespecified descriptive country summaries; no refitting or model selection',
             'base_protocol_sha256':PROTOCOL_SHA,'A01_sha256':ADDENDUM_SHA,'country_policy_rows':len(country),
             'country_contrast_rows':len(paired),'contrast_summary_rows':len(summaries),'MAX_MOST_distribution_rows':len(distribution),
             'India_equal_source_mean_within_country':True,'secondary_targets_outside_primary_averages':True,
             'positivity_sign_counts_use_exact_float_sign_not_statistical_significance':True}
    write_json(output/'SUMMARY_QA.json',receipt)
    print(json.dumps(receipt))


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--run',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();summarise(args.run.resolve(),args.output.resolve())
