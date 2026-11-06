#!/usr/bin/env python3
"""Verify H5 aggregate accounting, source completeness and archived H4 parity."""
from pathlib import Path
import argparse,json,math
import numpy as np
import pandas as pd
from run_h4_pilot import write_json

def verify(out,h4_reference=None,replay=None):
    d=pd.read_csv(out/'source_policy_quota_results.csv');g=pd.read_csv(out/'group_contact_results.csv')
    keys=['cohort','source','policy','quota']
    assert not d.duplicated(keys).any();assert len(d)==672
    for name,a in d.groupby('cohort'):
        assert a.source.nunique()==14 and a.policy.nunique()=={'planning_H4':4,'common_functions':8}[name]
        assert set(a.quota)=={.2,.35,.5,.75}
        assert len(a)==14*a.policy.nunique()*4
    quota=np.max(np.abs(d.expected_weighted_contacts-d.quota*d.eligible_weighted_mass))
    assert quota<1e-8
    assert ((d.cases_per_100_expected_contacts>=0)&(d.cases_per_100_expected_contacts<=100)).all()
    y=100*d.expected_weighted_cases/d.expected_weighted_contacts
    yield_error=np.max(np.abs(y-d.cases_per_100_expected_contacts));assert yield_error<1e-10
    group_share_error=0.;group_rate_error=0.;group_mass_error=0.;group_rows=0
    for key,a in g.groupby(keys+['dimension']):
        mask=np.ones(len(d),bool)
        for col,v in zip(keys,key[:4]):mask&=d[col].eq(v).to_numpy()
        row=d.loc[mask].iloc[0]
        group_share_error=max(group_share_error,abs(a.expected_contact_share_percent.sum()-100))
        masses=a.eligible_weighted_group_mass*a.within_group_contact_rate_percent/100
        group_rate_error=max(group_rate_error,abs(masses.sum()-row.expected_weighted_contacts))
        group_mass_error=max(group_mass_error,abs(a.eligible_weighted_group_mass.sum()-row.eligible_weighted_mass))
        recovered=100*masses/row.expected_weighted_contacts
        assert np.max(np.abs(recovered-a.expected_contact_share_percent))<1e-9
        group_rows+=len(a)
    assert max(group_share_error,group_rate_error,group_mass_error)<1e-8
    qa={'status':'PASS','scope':'AGGREGATE_ACCOUNTING_AND_OPTIONAL_H4_PARITY','source_rows':len(d),'group_rows':group_rows,
        'max_quota_error':float(quota),'max_yield_identity_error':float(yield_error),'max_group_share_sum_error':float(group_share_error),
        'max_group_contact_mass_error':float(group_rate_error),'max_group_eligible_mass_error':float(group_mass_error)}
    if h4_reference:
        old=pd.read_csv(h4_reference/'source_policy_quota_results.csv')
        old=old.loc[old.cohort.eq('planning')&old.policy.isin(['B','B_MOST5'])].copy()
        old['policy']=old.policy.map({'B':'logistic_B','B_MOST5':'logistic_B_plan_MOST5'})
        new=d.loc[d.cohort.eq('planning_H4')&d.policy.str.startswith('logistic')]
        join=new.merge(old,on=['source','policy','quota'],validate='one_to_one',suffixes=('_h5','_h4'))
        assert len(join)==112
        mets=['expected_weighted_contacts','expected_weighted_cases','eligible_weighted_mass','event_prevalence_percent','cases_per_100_expected_contacts','event_recall_percent','yield_delta_vs_lottery','yield_delta_vs_B']
        maxerr=max(float(np.max(np.abs(join[m+'_h5']-join[m+'_h4']))) for m in mets)
        assert maxerr<1e-9
        assert (join.target_membership_sha256_h5==join.target_membership_sha256_h4).all()
        qa['H4_parity']={'rows':112,'numeric_metrics':len(mets),'numeric_comparisons':112*len(mets),'max_absolute_error':maxerr,'all_membership_hashes_equal':True}
    if replay:
        files=sorted(x.name for x in out.glob('*.csv'))
        checks=[];nc=0
        for fname in files:
            a=(out/fname).read_bytes();b=(replay/fname).read_bytes();assert a==b,fname
            df=pd.read_csv(out/fname);num=df.select_dtypes(include='number');nc+=num.size
            checks.append({'name':fname,'byte_identical':True,'rows':len(df),'numeric_values':num.size})
        qa['clean_replay']={'files':checks,'numeric_values_compared':nc,'max_absolute_numeric_error':0.0}
    return qa

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--results',type=Path,required=True);p.add_argument('--h4-reference',type=Path);p.add_argument('--replay',type=Path);p.add_argument('--receipt',type=Path,required=True);a=p.parse_args()
    qa=verify(a.results,a.h4_reference,a.replay);write_json(a.receipt,qa);print(json.dumps(qa,indent=2))
