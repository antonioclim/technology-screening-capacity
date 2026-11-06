#!/usr/bin/env python3
"""Compare independently reconstructed H5 metrics and audit all canonical aggregates."""
import argparse,json,math
from pathlib import Path
import numpy as np
import pandas as pd
from verify_h5_raw import write_json

def compare(a):
 own=pd.read_csv(a.independent/'raw_reestimation/INDEPENDENT_SOURCE_Q50.csv');both=pd.read_csv(a.independent/'both_diagnostic/INDEPENDENT_BOTH_FUNCTIONS_Q50.csv');canon=pd.read_csv(a.canonical/'source_policy_quota_results.csv')
 def mapframe(d):
  d=d.copy();d['cohort']=d.cohort.map({'planning':'planning_H4','matched_functions':'common_functions'});d['policy']=d.learner+'_'+d.policy;return d
 own=mapframe(own);both=mapframe(both)
 key=['cohort','source','policy','quota'];j=own.merge(canon,on=key,suffixes=('_ind','_canonical'),validate='1:1');assert len(j)==140
 checks={};n=0
 for left,right in [('expected_weighted_contacts','expected_weighted_contacts'),('expected_weighted_cases','expected_weighted_cases'),('cases_per_100_expected_contacts','cases_per_100_expected_contacts'),('event_prevalence_percent','event_prevalence_percent'),('yield_delta_vs_B','yield_delta_vs_B'),('sector_composition_tv_vs_B_pp','sector_tv_vs_B_pp'),('employment_composition_tv_vs_B_pp','employment_tv_vs_B_pp')]:
  l=left+'_ind' if left==right else left;r=right+'_canonical' if left==right else right
  diff=float(abs(j[l]-j[r]).max());assert diff<1e-9;checks[left]=diff;n+=len(j)
 assert (j.membership_sha256==j.target_membership_sha256).all();assert (j.n_ind==j.n_canonical).all()
 jb=both.merge(canon,on=key,suffixes=('_ind','_canonical'),validate='1:1');assert len(jb)==28
 for col in ['expected_weighted_contacts','expected_weighted_cases','cases_per_100_expected_contacts','event_prevalence_percent']:
  diff=float(abs(jb[col+'_ind']-jb[col+'_canonical']).max());assert diff<1e-9;checks['both_'+col]=diff;n+=len(jb)
 assert (jb.membership_sha256==jb.target_membership_sha256).all()
 g=mapframe(pd.read_csv(a.independent/'raw_reestimation/INDEPENDENT_GROUP_Q50.csv'));cg=pd.read_csv(a.canonical/'group_contact_results.csv');gj=g.merge(cg,on=key+['dimension','group'],suffixes=('_ind','_canonical'),validate='1:1');assert len(gj)==2104
 gd={}
 for col in ['eligible_weighted_group_mass','expected_contact_share_percent','within_group_contact_rate_percent']:
  diff=float(abs(gj[col+'_ind']-gj[col+'_canonical']).max());assert diff<1e-9;gd[col]=diff;n+=len(gj)
 f=pd.read_csv(a.independent/'raw_reestimation/INDEPENDENT_FUNCTION_CONTRASTS_Q50.csv').rename(columns={'learner':'family'});cf=pd.read_csv(a.canonical/'source_function_contrasts.csv');cf=cf.loc[cf.quota==.5];fj=f.merge(cf,on=['family','source'],suffixes=('_ind','_canonical'),validate='1:1');assert len(fj)==28
 fd={}
 for col,cc in [('yield_admin_minus_planning','admin_minus_plan_yield'),('expected_allocation_tv_pp','function_expected_allocation_tv_pp')]:
  diff=float(abs(fj[col]-fj[cc]).max());assert diff<1e-9;fd[col]=diff;n+=len(fj)
 # Directly reconstruct all canonical group accounting, all four quotas and both learners.
 accounting=[]
 for k,x in cg.groupby(key+['dimension'],sort=True):
  eligible=math.fsum(x.eligible_weighted_group_mass);contact=math.fsum(x.eligible_weighted_group_mass*x.within_group_contact_rate_percent/100)
  q=k[3];share=math.fsum(x.expected_contact_share_percent)
  row=canon.loc[(canon.cohort==k[0])&(canon.source==k[1])&(canon.policy==k[2])&(canon.quota==q)];assert len(row)==1;row=row.iloc[0]
  errors={'eligible_mass':abs(eligible-row.eligible_weighted_mass),'contact_mass':abs(contact-row.expected_weighted_contacts),'quota_mass':abs(contact-q*eligible),'share_sum':abs(share-100)}
  assert max(errors.values())<1e-9
  assert x.within_group_contact_rate_percent.between(-1e-9,100+1e-9).all();assert x.expected_contact_share_percent.between(-1e-9,100+1e-9).all()
  accounting.append(errors)
 # Mean-source inside India, then equal-country; no pooled or equal-source substitution.
 summary=pd.read_csv(a.canonical/'equal_country_policy_summaries.csv');primary=canon.loc[canon.route=='country_holdout'];means=primary.groupby(['cohort','policy','quota','country'],as_index=False)[['cases_per_100_expected_contacts','yield_delta_vs_B']].mean().groupby(['cohort','policy','quota'],as_index=False).mean(numeric_only=True)
 sj=means.merge(summary,on=['cohort','policy','quota'],validate='1:1');assert len(sj)==48
 sd={}
 for col in ['cases_per_100_expected_contacts','yield_delta_vs_B']:
  diff=float(abs(sj[col]-sj[col+'_mean']).max());assert diff<1e-9;sd[col]=diff;n+=len(sj)
 qa={'status':'PASS','independent_fit_n':144,'independent_q50_source_policy_rows':168,'independent_group_rows':2104,'independent_function_contrast_rows':28,'numeric_comparisons':n,'source_metric_max_errors':checks,'group_metric_max_errors':gd,'function_contrast_max_errors':fd,'equal_country_summary_max_errors':sd,'all_quota_canonical_group_blocks':len(accounting),'all_quota_group_accounting_max_errors':{k:max(row[k] for row in accounting) for k in accounting[0]},'membership_hash_and_source_n_all_match':True,'tolerance':1e-9,'scope':'Independent raw re-estimation: all12 predeclared cohort/learner/policy combinations atq50 all14sources including both-function diagnostic. Independent group re-estimation excludes both-function diagnostic. Canonical aggregate-accounting/summary audit includes allfourquotas. No survey inference/formal verification/native Windows/prospective validation.'}
 write_json(a.independent/'INDEPENDENT_CANONICAL_COMPARISON_QA.json',qa);print(json.dumps(qa,indent=2))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--independent',type=Path,required=True);p.add_argument('--canonical',type=Path,required=True);compare(p.parse_args())
