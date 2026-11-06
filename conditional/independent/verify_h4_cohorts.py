"""Compare independent cohort reconstructions with H4 aggregate membership receipts."""
import argparse
from collections import Counter
import csv
import json
import math
from pathlib import Path
import numpy as np
from verify_h4_primary import read_raw,prepare,fingerprint,digest,PROTOCOL_SHA

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--microdata',required=True,type=Path);p.add_argument('--protocol',required=True,type=Path)
    p.add_argument('--canonical-run',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--include-lottery',action='store_true')
    a=p.parse_args()
    if digest(a.protocol)!=PROTOCOL_SHA:raise ValueError('Protocol differs')
    protocol=json.loads(a.protocol.read_text());frame=read_raw(a.microdata,protocol)
    cohorts,bases,report=prepare(frame,protocol)
    planning=cohorts['planning'];d=planning.d3c.to_numpy(dtype=float)
    keep=np.isfinite(d)&(d>=0)&(d==np.floor(d))&(d!=2500000)
    paired=planning.loc[keep].copy()
    paired['eval_weight']=paired.base_wt/paired.groupby('country').base_wt.transform('mean')
    cohorts['paired_common_productivity']=paired.copy()
    paired_finance=paired.copy();paired_finance['event']=paired_finance.d3c.gt(0)
    cohorts['paired_common_finance']=paired_finance
    aliases={'finance_planning_ex99':'finance_planning_excluding99'}
    canonical=json.loads((a.canonical_run/'COHORT_QA.json').read_text())['cohorts']
    checks=[]
    for own_name,cohort in cohorts.items():
        name=aliases.get(own_name,own_name);expected=canonical[name]
        primary=cohort.loc[cohort.country.isin(protocol['primary_sources'])]
        values={'matched_primary_n':len(primary),'full_matched_n':len(cohort),
                'matched_primary_membership_sha256':fingerprint(primary),
                'source_counts':{s:len(g) for s,g in cohort.groupby('country')}}
        for key,value in values.items():
            if value!=expected[key]:raise ValueError('Cohort receipt differs: '+name+'/'+key)
            checks.append(name+'/'+key)
        if own_name in ['planning','administration']:
            base=bases[own_name];primarybase=base.loc[base.country.isin(protocol['primary_sources'])]
            if len(primarybase)!=expected['MOST_base_primary_n'] or fingerprint(primarybase)!=expected['MOST_base_primary_membership_sha256']:
                raise ValueError('Pre-adoption cohort differs')
            checks.extend([name+'/MOST_base_primary_n',name+'/MOST_base_primary_membership_sha256'])
    result={'status':'PASS','scope':'Independent raw reconstruction of all six H4 cohort memberships',
            'checks':len(checks),'checked_fields':checks,'H4_computational_modules_imported':False,
            'paired_common_primary_n':int(paired.country.isin(protocol['primary_sources']).sum()),
            'source_receipt_sha256':digest(a.canonical_run/'COHORT_QA.json')}
    if a.include_lottery:
        with (a.canonical_run/'source_policy_quota_results.csv').open(encoding='utf-8-sig',newline='') as h:
            rows=[r for r in csv.DictReader(h) if r['policy']=='lottery']
        lookup={(r['cohort'],r['source'],float(r['quota'])):r for r in rows}
        counts=Counter();maxima=Counter()
        for own_name,cohort in cohorts.items():
            name=aliases.get(own_name,own_name)
            for source,g in cohort.groupby('country',sort=True):
                weights=g.eval_weight.to_numpy(dtype=float);events=g.event.to_numpy(dtype=bool)
                mass=math.fsum(weights);cases=math.fsum(weights*events)
                for quota in [.2,.35,.5,.75]:
                    actual=lookup[name,source,quota]
                    expected={'eligible_weighted_mass':mass,'expected_weighted_contacts':quota*mass,
                              'expected_weighted_cases':quota*cases,'event_prevalence_percent':100*cases/mass,
                              'cases_per_100_expected_contacts':100*cases/mass,
                              'event_recall_percent':100*quota if cases else None}
                    for key,value in expected.items():
                        if value is None:
                            if actual[key] not in ('',None):raise ValueError('Missing zero-event recall differs')
                            counts[key]+=1;continue
                        error=abs(value-float(actual[key]));counts[key]+=1;maxima[key]=max(maxima[key],error)
                        if error>1e-7:raise ValueError('Event/lottery quantity differs: '+name+'/'+source+'/'+key)
        result['lottery_event_checks']=dict(counts);result['lottery_event_maximum_errors']=dict(maxima)
        result['scope']+='; all source/target event prevalence and lottery accounting at all four quotas'
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'status':'PASS','checks':len(checks),'cohorts':len(cohorts)}))

if __name__=='__main__':main()
