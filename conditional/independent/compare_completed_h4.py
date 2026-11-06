"""Compare independently recomputed aggregate H4 results with completed outputs."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
from verify_h4_primary import compare,digest


def read(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as h:return list(csv.DictReader(h))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--canonical-run',required=True,type=Path)
    p.add_argument('--primary-run',required=True,type=Path)
    p.add_argument('--paired-run',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    a=p.parse_args()
    primary=read(a.primary_run/'INDEPENDENT_PRIMARY_SOURCE_RESULTS.csv')
    for row in primary:
        for name in ['quota','expected_weighted_contacts','expected_weighted_cases','eligible_weighted_mass','cases_per_100_expected_contacts','event_prevalence_percent']:
            row[name]=float(row[name])
    if len(primary)!=36:raise ValueError('Independent primary CSV incomplete')
    primaryqa=compare(primary,a.canonical_run)
    canonical_groups=read(a.canonical_run/'group_contact_results.csv')
    canonical_groups={(r['source'],r['policy'],r['dimension'],r['group']):r for r in canonical_groups
                      if r['cohort']=='planning' and r['route']=='country_holdout' and abs(float(r['quota'])-.5)<1e-12}
    own_groups=read(a.primary_run/'INDEPENDENT_PRIMARY_GROUP_RESULTS.csv')
    counts=Counter();maxima=Counter()
    for own in own_groups:
        key=tuple(own[k] for k in ['source','policy','dimension','group'])
        actual=canonical_groups[key]
        if int(own['group_n'])!=int(actual['group_n']):raise ValueError('Independent group membership count differs')
        counts['group_n']+=1
        for left,right in [('eligible_group_weight','eligible_weighted_group_mass'),
                           ('contact_share_percent','expected_contact_share_percent'),
                           ('group_contact_rate_percent','within_group_contact_rate_percent')]:
            error=abs(float(own[left])-float(actual[right]));maxima[left]=max(maxima[left],error);counts[left]+=1
            if error>1e-7:raise ValueError('Independent group metric differs: '+str(key)+' '+left+' '+str(error))
    paired=read(a.paired_run/'INDEPENDENT_EXPECTED_ALLOCATION_DISTANCE.csv')
    if len(paired)!=36:raise ValueError('Independent paired CSV incomplete')
    canonical=read(a.canonical_run/'cross_target_allocation.csv')
    canonical={(r['source'],r['policy']):r for r in canonical if r['route']=='country_holdout' and abs(float(r['quota'])-.5)<1e-12}
    pc=Counter();pm=Counter()
    for own in paired:
        actual=canonical[own['source'],own['policy']]
        if int(own['eligible_n'])!=int(actual['common_n']):raise ValueError('Common cohort count differs')
        pc['common_n']+=1
        error=abs(float(own['expected_allocation_tv_pp'])-float(actual['expected_allocation_tv_pp']))
        pc['expected_allocation_tv_pp']+=1;pm['expected_allocation_tv_pp']=max(pm['expected_allocation_tv_pp'],error)
        if error>1e-7:raise ValueError('Expected allocation distance differs: '+str(error))
    receipt={'status':'PASS','scope':'Independent raw-data primary planning fixed-model and common-objective expected-allocation recomputation',
             'computational_H4_modules_imported':False,'primary':primaryqa,
             'group_checks':dict(counts),'group_maximum_errors':dict(maxima),
             'paired_objective_checks':dict(pc),'paired_objective_maximum_errors':dict(pm),
             'absolute_tolerance':1e-7,
             'independent_model_fits_primary':33,'independent_model_fits_paired':66,
             'limitations':['Same raw sample and the same declared sklearn model family; not independent external data.',
                            'Only three primary model families at q50 are independently fitted; all16policies/allquotas are not claimed independently recomputed.',
                            'No mathematical proof, survey-valid confidence interval or causal inference.',
                            'Distance concerns normalised expected allocation, not realised lists.'],
             'source_files':{str(path):digest(path) for path in [Path(__file__),a.primary_run/'INDEPENDENT_PRIMARY_SOURCE_RESULTS.csv',
                 a.primary_run/'INDEPENDENT_PRIMARY_GROUP_RESULTS.csv',a.paired_run/'INDEPENDENT_EXPECTED_ALLOCATION_DISTANCE.csv',
                 a.canonical_run/'source_policy_quota_results.csv',a.canonical_run/'group_contact_results.csv',a.canonical_run/'cross_target_allocation.csv']}}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({'status':'PASS','primary_rows':len(primary),'group_rows':len(own_groups),'paired_rows':len(paired),
                      'primary_max_error':max(primaryqa['maximum_errors'].values()),'group_max_error':max(maxima.values()),
                      'paired_max_error':max(pm.values())}))

if __name__=='__main__':main()
