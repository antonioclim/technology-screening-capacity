"""Independent arithmetic checks of complete H4 aggregate output tables."""
import argparse
from collections import defaultdict
import csv
import json
import math
from pathlib import Path


def read(path):
    with path.open(newline='') as f:return list(csv.DictReader(f))


def main(run,summary,output):
    counts=defaultdict(int);maxima=defaultdict(float)
    def close(label,a,b,tol=1e-9):
        difference=abs(float(a)-float(b));counts[label]+=1;maxima[label]=max(maxima[label],difference)
        if difference>tol:raise ValueError((label,a,b,difference))
    source=read(run/'source_policy_quota_results.csv')
    keyed={}
    for row in source:
        key=(row['cohort'],row['route'],row['source'],row['policy'],row['quota'])
        if key in keyed:raise ValueError('Duplicate source score')
        keyed[key]=row
        close('quota_mass',float(row['expected_weighted_contacts']),float(row['quota'])*float(row['eligible_weighted_mass']))
        close('source_yield',float(row['cases_per_100_expected_contacts']),100*float(row['expected_weighted_cases'])/float(row['expected_weighted_contacts']))
    groups=defaultdict(list)
    for row in read(run/'group_contact_results.csv'):
        key=(row['cohort'],row['route'],row['source'],row['policy'],row['quota'])
        groups[key+(row['dimension'],)].append(row)
        rate=float(row['within_group_contact_rate_percent']);share=float(row['expected_contact_share_percent'])
        if not -1e-10<=rate<=100+1e-10 or not -1e-10<=share<=100+1e-10:
            raise ValueError('Invalid group rate/share')
        counts['group_bounds']+=1
    for key,rows in groups.items():
        ref=keyed[key[:-1]]
        close('group_N',sum(int(r['group_n']) for r in rows),int(ref['n']),0)
        close('group_mass',math.fsum(float(r['eligible_weighted_group_mass']) for r in rows),float(ref['eligible_weighted_mass']))
        close('group_share_sum',math.fsum(float(r['expected_contact_share_percent']) for r in rows),100.)
        close('group_contact_reconstruction',math.fsum(float(r['eligible_weighted_group_mass'])*float(r['within_group_contact_rate_percent'])/100 for r in rows),float(ref['expected_weighted_contacts']))
    country=defaultdict(list)
    for row in source:
        key=(row['cohort'],row['route'],row['country'],row['policy'],row['quota'])
        country[key].append(float(row['cases_per_100_expected_contacts']))
    for row in read(summary/'country_policy_quota_results.csv'):
        key=(row['cohort'],row['route'],row['country'],row['policy'],row['quota'])
        values=country[key]
        close('equal_source_country_yield',float(row['cases_per_100_expected_contacts']),math.fsum(values)/len(values))
    bycountry={k:math.fsum(v)/len(v) for k,v in country.items()}
    for row in read(summary/'equal_country_contrast_summaries.csv'):
        differences=[]
        for ct in sorted({k[2] for k in bycountry if k[0]==row['cohort'] and k[1]=='country_holdout'}):
            left=bycountry[(row['cohort'],'country_holdout',ct,row['left_policy'],row['quota'])]
            right=bycountry[(row['cohort'],'country_holdout',ct,row['right_policy'],row['quota'])]
            differences.append(left-right)
        close('equal_country_contrast_mean',row['equal_country_mean'],math.fsum(differences)/len(differences))
        close('equal_country_contrast_min',row['country_min'],min(differences))
        close('equal_country_contrast_max',row['country_max'],max(differences))
    result={'status':'PASS','scope':'Independent arithmetic from written aggregate tables; not independent model fitting',
            'source_score_rows':len(source),'source_group_dimension_sets':len(groups),
            'checks':dict(counts),'maximum_absolute_errors':dict(maxima),'absolute_tolerance':1e-9}
    output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--summary',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();main(a.run.resolve(),a.summary.resolve(),a.output.resolve())
