#!/usr/bin/env python3
"""Re-estimate the predeclared both-function diagnostic with independent primitives."""
import argparse,json
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from threadpoolctl import threadpool_limits
from verify_h5_raw import prepare,fit,predict,score,groups,write_csv,write_json,PRIMARY,TARGETS,COUNTRY,fingerprint

def run(a):
 assert not a.output.exists();a.output.mkdir(parents=True)
 started=datetime.now(timezone.utc).isoformat();d=prepare(a.raw)['matched_functions'];primary=d.loc[d.country.isin(PRIMARY)]
 tasks=[(c,primary.loc[primary.reporting_country.ne(c)],primary.loc[primary.reporting_country.eq(c)]) for c in sorted(set(primary.reporting_country))];tasks.append(('all_primary_training',primary,d.loc[d.country.isin(TARGETS)]))
 rows=[];fits=[]
 for kind in ['logistic','tree']:
  for held,train,test in tasks:
   test=test.sort_values(['country','firmid'],kind='stable').reset_index(drop=True)
   pipe,lock=fit(train,kind,'B_both_MOST5');s=predict(pipe,test,kind);assert np.array_equal(s,predict(pipe,test.iloc[::-1],kind)[::-1]);fits.append({'learner':kind,'held_out_country':held,**lock})
   for source,ii in test.groupby('country',sort=True).groups.items():
    ii=np.asarray(list(ii));part=test.loc[ii];metric,_=score(part,s[ii],.5);metric.update(cohort='matched_functions',learner=kind,source=source,country=COUNTRY.get(source,source),policy='B_both_MOST5',quota=.5,membership_sha256=fingerprint(part));rows.append(metric)
 write_csv(a.output/'INDEPENDENT_BOTH_FUNCTIONS_Q50.csv',rows)
 write_json(a.output/'BOTH_FUNCTIONS_QA.json',{'status':'PASS','fit_n':len(fits),'source_policy_n':len(rows),'started_utc':started,'completed_utc':datetime.now(timezone.utc).isoformat(),'fits':fits,'scope':'Predeclared both-function diagnostic q50 only. Independent primitives imported from this verifier directory, no canonical H5 scientific functions.'})

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--raw',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 with threadpool_limits(limits=1):run(a)
