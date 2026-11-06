"""Independent paired-objective expected-allocation distance on common FAT rows."""
from __future__ import annotations
import argparse
import csv
import json
import math
from pathlib import Path
import numpy as np
from verify_h4_primary import (digest,read_raw,prepare,independent_fit_predict,
    contact_probabilities,PROTOCOL_SHA,RAW_SHA)

ADDENDUM_SHA='a642133ea710cf15db06ae172df4d718d15f7388820b0324d86938a6c5388fd1'


def recompute(common,protocol):
    primary=common.loc[common.country.isin(protocol['primary_sources'])].copy()
    rows=[];fits=[]
    for holdout in sorted(primary.reporting_country.unique()):
        train=primary.loc[primary.reporting_country!=holdout].copy()
        target=primary.loc[primary.reporting_country==holdout].copy()
        for policy in ['B','B_MOST5','B_MAX5']:
            scores={}
            for objective in ['productivity','finance']:
                t=train.copy();v=target.copy()
                if objective=='finance':
                    t['event']=t.d3c.gt(0);v['event']=v.d3c.gt(0)
                score,receipt=independent_fit_predict(t,v,policy)
                receipt.update({'holdout_country':holdout,'policy':policy,'objective':objective})
                fits.append(receipt);scores[objective]=score
            for source,indices in target.groupby('country',sort=True).groups.items():
                v=target.loc[indices];position=target.index.get_indexer(indices)
                weights=v.eval_weight.to_numpy(dtype=float)
                probs={key:contact_probabilities(value[position],weights,.5) for key,value in scores.items()}
                totals={key:math.fsum(weights*p) for key,p in probs.items()}
                tv=50*math.fsum(abs(weights*probs['productivity']/totals['productivity']-
                                     weights*probs['finance']/totals['finance']))
                # Equal contact budgets make this direct check equivalent here;
                # it is a check of the implemented calculation, not a new result.
                direct=100*math.fsum(weights*abs(probs['productivity']-probs['finance']))/(2*totals['productivity'])
                if abs(tv-direct)>1e-9:raise ValueError('Allocation distance normalisation differs')
                rows.append({'source':source,'country':holdout,'policy':policy,'quota':.5,
                             'eligible_n':len(v),'expected_weighted_contacts_productivity':totals['productivity'],
                             'expected_weighted_contacts_finance':totals['finance'],
                             'expected_allocation_tv_pp':tv})
    return rows,fits


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--microdata',required=True,type=Path);p.add_argument('--protocol',required=True,type=Path)
    p.add_argument('--addendum',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args()
    if digest(a.protocol)!=PROTOCOL_SHA or digest(a.addendum)!=ADDENDUM_SHA:raise ValueError('Locked design differs')
    if a.output.exists():raise ValueError('Choose a new output directory')
    protocol=json.loads(a.protocol.read_text());frame=read_raw(a.microdata,protocol)
    cohorts,_,_=prepare(frame,protocol)
    plan=cohorts['planning']
    finance=np.asarray(plan.d3c,dtype=float)
    keep=np.isfinite(finance)&(finance>=0)&(finance==np.floor(finance))&(finance!=2500000)
    common=plan.loc[keep].copy()
    common['eval_weight']=common.base_wt/common.groupby('country').base_wt.transform('mean')
    rows,fits=recompute(common,protocol)
    a.output.mkdir(parents=True)
    with (a.output/'INDEPENDENT_EXPECTED_ALLOCATION_DISTANCE.csv').open('w',newline='') as h:
        writer=csv.DictWriter(h,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    receipt={'status':'RECOMPUTED_PENDING_CANONICAL_COMPARISON',
             'scope':'Independent B/B_MOST5/B_MAX5 paired-objective q50 expected-allocation distance',
             'protocol_sha256':PROTOCOL_SHA,'addendum_sha256':ADDENDUM_SHA,'raw_sha256':RAW_SHA,
             'common_primary_n':int(common.country.isin(protocol['primary_sources']).sum()),
             'source_policy_rows':len(rows),'fits':len(fits),'fit_receipts':fits,
             'individual_records_predictions_or_identifiers_saved':False,
             'realised_overlap_claimed':False}
    (a.output/'INDEPENDENT_A01_QA.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({k:receipt[k] for k in ['status','common_primary_n','source_policy_rows','fits']}))

if __name__=='__main__':main()
