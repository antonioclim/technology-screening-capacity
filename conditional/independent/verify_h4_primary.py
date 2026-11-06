"""Independent H4 primary-model replay from authenticated original FAT rows.

This verifier imports no H4 or canonical analysis computation module. It retains
only aggregate scores, counts, parameter summaries and input/output identities.
It is numerical verification on the same sample, not formal verification or a
new sampling-confidence analysis.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from hashlib import sha256
import io
import json
import math
from pathlib import Path
import platform
import warnings
from zipfile import ZipFile

import numpy as np
import pandas as pd
import sklearn
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import OneHotEncoder, StandardScaler

PROTOCOL_SHA='a62c851289541a00e387c68f8bcbc31c78677c18116c714f46c180af2858f777'
RAW_SHA='6d77d3ffb9dcef2ca4534e1c438ddd2e0b357eb852e6c5b48aa5fa6c3cbe2f0e'
MEMBER_SHA='f61a2c6e09f4763818ae1d4db8b330e97bffd8bb0824c2d833b79d728152bd17'
PRIMARY_FP='59d49ff980b98de612b32d721ed35dc80a92fb3175be2e1ddfcf8d36168c6f76'
DOMAINS={
    'sector':[*map(str,range(1,12)),'101','102','UNKNOWN'],
    'multi_establishment':['0','1','UNKNOWN'],
    'foreign_owner':['DOMESTIC','ANY_FOREIGN','UNKNOWN'],
    'MOST5':list('12345'), 'MAX5':list('12345'),
}
COUNTRIES={'India_Wave2_New':'India','BurkinaFaso':'Burkina Faso','Korea':'Republic of Korea','Vietnam':'Viet Nam'}


def digest(path):return sha256(Path(path).read_bytes()).hexdigest()
def country(source):return COUNTRIES.get(source,source)


def fingerprint(frame):
    ordered=frame.sort_values(['country','firmid'],kind='mergesort')
    text='\n'.join(str(s)+'|'+str(int(i)) for s,i in ordered[['country','firmid']].itertuples(index=False,name=None))+'\n'
    return sha256(text.encode()).hexdigest()


def read_raw(path,protocol):
    if digest(path)!=RAW_SHA:raise ValueError('Original ZIP identity differs')
    with ZipFile(path) as archive:
        if archive.testzip() is not None:raise ValueError('Original ZIP CRC differs')
        blob=archive.read('fat0_raw_data_qje.csv')
    if sha256(blob).hexdigest()!=MEMBER_SHA:raise ValueError('Original member differs')
    frame=pd.read_csv(io.BytesIO(blob),low_memory=False)
    if frame.shape!=(21055,723) or frame.firmid.duplicated().any():raise ValueError('Raw shape/identity differs')
    frame=frame.loc[frame.country.isin(protocol['primary_sources']+protocol['secondary_targets'])].copy()
    return frame.sort_values(['country','firmid'],kind='mergesort').reset_index(drop=True)


def state_masks(frame,most_prefix,adopt_prefix):
    most=frame[[most_prefix+str(k) for k in range(1,6)]].to_numpy(dtype=float)
    adopt=frame[[adopt_prefix+str(k) for k in range(1,6)]].to_numpy(dtype=float)
    mvalid=np.isin(most,[0,1]).all(axis=1)&(np.sum(most,axis=1)==1)
    avalid=np.isin(adopt,[0,1]).all(axis=1)&(np.sum(adopt,axis=1)>=1)
    mstate=np.argmax(np.nan_to_num(most,nan=-1),axis=1)+1
    maxstate=np.max(np.nan_to_num(adopt,nan=0)*np.arange(1,6),axis=1).astype(int)
    consistency=adopt[np.arange(len(frame)),mstate-1]==1
    return mvalid,avalid,mstate,maxstate,consistency


def event_on_base(base):
    result=base.copy()
    result['event']=False
    thresholds={}
    for source,group in result.groupby('country',sort=True):
        weights=group.base_wt.to_numpy(dtype=float)/float(group.base_wt.mean())
        values=np.log(group.e6a.to_numpy(dtype=float)/group.s7.to_numpy(dtype=float))
        order=np.argsort(values,kind='mergesort')
        cumulative=np.cumsum(weights[order])
        position=np.searchsorted(cumulative,.20*cumulative[-1],side='left')
        threshold=float(values[order[min(position,len(order)-1)]])
        result.loc[group.index,'event']=values<=threshold
        thresholds[source]=threshold
    return result,thresholds


def prepare(frame,protocol):
    positive=np.isfinite(frame.e6a)&(frame.e6a>0)&np.isfinite(frame.s7)&(frame.s7>0)&np.isfinite(frame.base_wt)&(frame.base_wt>0)
    primary=frame.country.isin(protocol['primary_sources']).to_numpy()
    cohorts={};base_frames={};report={}
    for name,mp,ap,expected_base,expected_matched in [
        ('planning','ib9b','db9a',14412,13996),
        ('administration','ib8b','db8a',14707,14249),
    ]:
        mv,av,ms,mx,consistent=state_masks(frame,mp,ap)
        selection=positive.to_numpy()&mv
        base=frame.loc[selection].copy()
        base['MOST5']=ms[selection]
        base['MAX5']=mx[selection]
        base['adoption_valid']=av[selection]
        base['consistent']=consistent[selection]
        base,thresholds=event_on_base(base)
        base_frames[name]=base
        baseprimary=base[base.country.isin(protocol['primary_sources'])]
        matched=base[base.adoption_valid].copy()
        if not matched.consistent.all():raise ValueError('MOST/adoption inconsistency: '+name)
        primarymatched=matched[matched.country.isin(protocol['primary_sources'])]
        if len(baseprimary)!=expected_base or len(primarymatched)!=expected_matched:raise ValueError('Cohort count: '+name)
        if name=='planning' and fingerprint(baseprimary)!=PRIMARY_FP:raise ValueError('Original H1 membership differs')
        matched['eval_weight']=matched.base_wt/matched.groupby('country').base_wt.transform('mean')
        matched['reporting_country']=matched.country.map(country)
        cohorts[name]=matched.reset_index(drop=True)
        report[name]={'MOST_primary_N':len(baseprimary),'matched_primary_N':len(primarymatched),
                      'MOST_primary_membership_sha256':fingerprint(baseprimary),
                      'matched_primary_membership_sha256':fingerprint(primarymatched),
                      'contradictions':int((~matched.consistent).sum()),
                      'source_thresholds':thresholds,
                      'source_counts':{str(s):len(g) for s,g in matched.groupby('country')}}
    mv,av,ms,mx,consistent=state_masks(frame,'ib9b','db9a')
    d=pd.to_numeric(frame.d3c,errors='coerce').to_numpy(dtype=float)
    fvalid=np.isfinite(frame.base_wt)&(frame.base_wt>0)&mv&av&np.isfinite(d)&(d>=0)&(d==np.floor(d))&(d!=2500000)
    for name,selection in [('finance_planning',fvalid),('finance_planning_ex99',fvalid&(d!=99))]:
        f=frame.loc[selection].copy()
        f['MOST5']=ms[selection];f['MAX5']=mx[selection];f['event']=d[selection]>0
        if not consistent[selection].all():raise ValueError('Finance MOST/adoption inconsistency')
        f['eval_weight']=f.base_wt/f.groupby('country').base_wt.transform('mean')
        f['reporting_country']=f.country.map(country)
        cohorts[name]=f.reset_index(drop=True)
        p=f[f.country.isin(protocol['primary_sources'])]
        report[name]={'matched_primary_N':len(p),'matched_primary_membership_sha256':fingerprint(p),
                      'source_counts':{str(s):len(g) for s,g in f.groupby('country')}}
    return cohorts,base_frames,report


def verify_h1_cells(base,reference_csv):
    expected={}
    with Path(reference_csv).open(encoding='utf-8-sig',newline='') as handle:
        for row in csv.DictReader(handle):expected[row['source'],int(row['state'])]=row
    checks=0;max_error=0.
    for source,g in base.groupby('country',sort=True):
        if not any(k[0]==source for k in expected):continue
        weights=g.base_wt.to_numpy(dtype=float)/float(g.base_wt.mean())
        event=g.event.to_numpy(dtype=bool)
        for state in range(1,6):
            mask=g.MOST5.to_numpy()==state
            row=expected[source,state]
            if int(mask.sum())!=int(row['n']) or int((mask&event).sum())!=int(row['n_cases']):raise ValueError('H1 event counts differ')
            checks+=2
            for column,value in [('weight_mass',math.fsum(weights[mask])),('case_mass',math.fsum(weights[mask&event]))]:
                error=abs(value-float(row[column]));max_error=max(max_error,error)
                if error>1e-9:raise ValueError('H1 cell mass differs')
                checks+=1
    return {'status':'PASS','comparisons':checks,'maximum_error':max_error}


def feature_frame(frame):
    out=pd.DataFrame(index=frame.index)
    out['sector']=[str(int(x)) if np.isfinite(x) and int(x)==x and int(x) in {*range(1,12),101,102} else 'UNKNOWN' for x in pd.to_numeric(frame.a5a,errors='coerce')]
    out['multi_establishment']=[str(int(x)) if np.isfinite(x) and x in (0,1) else 'UNKNOWN' for x in pd.to_numeric(frame.s4,errors='coerce')]
    out['foreign_owner']=['DOMESTIC' if x==0 else 'ANY_FOREIGN' if np.isfinite(x) and 0<x<=100 else 'UNKNOWN' for x in pd.to_numeric(frame.a3b,errors='coerce')]
    year=pd.to_numeric(frame.a6,errors='coerce').to_numpy(dtype=float)
    out['start_year']=np.where(np.isfinite(year)&(year>=1800)&(year<=2023),year,np.nan)
    out['MOST5']=frame.MOST5.astype(int).astype(str)
    out['MAX5']=frame.MAX5.astype(int).astype(str)
    return out


def fitting_weights(train):
    weights=np.zeros(len(train),dtype=float)
    source=train.country.to_numpy(dtype=str)
    reporting=train.reporting_country.to_numpy(dtype=str)
    raw=train.base_wt.to_numpy(dtype=float)
    for c in sorted(set(reporting)):
        sources=sorted(set(source[reporting==c]))
        for s in sources:
            mask=source==s
            weights[mask]=raw[mask]/math.fsum(raw[mask])/len(sources)
    weights*=len(train)/math.fsum(weights)
    country_totals={c:math.fsum(weights[reporting==c]) for c in sorted(set(reporting))}
    if max(country_totals.values())-min(country_totals.values())>1e-8:raise ValueError('Unequal fitted country totals')
    if abs(math.fsum(weights)-len(train))>1e-8:raise ValueError('Fit scale differs from N')
    return weights,country_totals


def independent_fit_predict(train,test,policy):
    cats=['sector','multi_establishment','foreign_owner']
    if policy=='B_MOST5':cats.append('MOST5')
    elif policy=='B_MAX5':cats.append('MAX5')
    elif policy!='B':raise ValueError('Unsupported independent policy')
    tr=feature_frame(train);te=feature_frame(test)
    encoder=OneHotEncoder(categories=[DOMAINS[k] for k in cats],handle_unknown='ignore',sparse_output=False,dtype=float)
    cat_train=encoder.fit_transform(tr[cats]);cat_test=encoder.transform(te[cats])
    values_train=tr[['start_year']].to_numpy(dtype=float);values_test=te[['start_year']].to_numpy(dtype=float)
    missing_train=~np.isfinite(values_train);missing_test=~np.isfinite(values_test)
    median=float(np.nanmedian(values_train)) if np.isfinite(values_train).any() else 0.
    filled_train=np.where(missing_train,median,values_train);filled_test=np.where(missing_test,median,values_test)
    scale=StandardScaler().fit(filled_train)
    X=np.concatenate([cat_train,scale.transform(filled_train),missing_train.astype(float)],axis=1)
    Xt=np.concatenate([cat_test,scale.transform(filled_test),missing_test.astype(float)],axis=1)
    weights,totals=fitting_weights(train)
    y=train.event.to_numpy(dtype=int)
    if len(np.unique(y))<2:
        scores=np.full(len(test),math.fsum(weights*y)/math.fsum(weights))
        params={'constant':float(scores[0])}
    else:
        model=LogisticRegression(penalty='l2',C=1.,solver='lbfgs',max_iter=2000,tol=1e-8)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always',ConvergenceWarning)
            model.fit(X,y,sample_weight=weights)
        if any(issubclass(w.category,ConvergenceWarning) for w in caught):raise RuntimeError('Independent fixed model did not converge')
        scores=model.predict_proba(Xt)[:,1]
        params={'intercept':float(model.intercept_[0]),'coefficient_n':int(model.coef_.size),'iterations':int(model.n_iter_[0])}
    return scores,{'train_n':len(train),'fit_weight_sum':math.fsum(weights),'country_fit_totals':totals,
                   'start_year_median':median,'start_year_scaler_mean':float(scale.mean_[0]),
                   'start_year_scaler_scale':float(scale.scale_[0]),'parameters':params}


def contact_probabilities(scores,weights,quota):
    # A separate group-by-score implementation; never break exact ties by rows.
    scores=np.asarray(scores,dtype=float);weights=np.asarray(weights,dtype=float)
    if not np.isfinite(scores).all() or not np.isfinite(weights).all() or np.any(weights<=0):raise ValueError('Invalid allocation inputs')
    probability=np.zeros(len(scores));remaining=quota*math.fsum(weights)
    for level in sorted(set(scores),reverse=True):
        mask=scores==level;mass=math.fsum(weights[mask])
        chance=min(1.,max(0.,remaining/mass));probability[mask]=chance;remaining-=chance*mass
    if abs(math.fsum(weights*probability)-quota*math.fsum(weights))>1e-8:raise ArithmeticError('Independent quota differs')
    return probability


def evaluate(test,scores,quota):
    w=test.eval_weight.to_numpy(dtype=float);e=test.event.to_numpy(dtype=bool)
    chance=contact_probabilities(scores,w,quota)
    contacts=math.fsum(w*chance);cases=math.fsum(w*chance*e)
    metrics={'expected_weighted_contacts':contacts,'expected_weighted_cases':cases,
             'eligible_weighted_mass':math.fsum(w),'cases_per_100_expected_contacts':100*cases/contacts,
             'event_prevalence_percent':100*math.fsum(w*e)/math.fsum(w)}
    # Row-order and response-perturbation checks concern allocation, not refits.
    order=np.arange(len(test))[::-1]
    reordered=contact_probabilities(scores[order],w[order],quota)[::-1]
    if not np.array_equal(chance,reordered):
        if np.max(np.abs(chance-reordered))>1e-12:raise ValueError('Row-order-dependent allocation')
    return metrics


def score_primary(planning,protocol):
    primary=planning.loc[planning.country.isin(protocol['primary_sources'])].copy()
    rows=[];fit_receipts=[];groups=[]
    for holdout in sorted(primary.reporting_country.unique()):
        train=primary.loc[primary.reporting_country!=holdout].copy()
        test=primary.loc[primary.reporting_country==holdout].copy()
        if set(train.reporting_country)&set(test.reporting_country):raise ValueError('Country leakage')
        for policy in ['B','B_MOST5','B_MAX5']:
            scores,receipt=independent_fit_predict(train,test,policy)
            receipt.update({'holdout_country':holdout,'policy':policy})
            fit_receipts.append(receipt)
            for source,indices in test.groupby('country',sort=True).groups.items():
                position=test.index.get_indexer(indices)
                metrics=evaluate(test.loc[indices],scores[position],.5)
                rows.append({'cohort':'planning','route':'country_holdout','source':source,'country':holdout,
                             'policy':policy,'quota':.5,**metrics})
                target=test.loc[indices]
                w=target.eval_weight.to_numpy(dtype=float)
                chances=contact_probabilities(scores[position],w,.5)
                sector=feature_frame(target).sector.to_numpy(dtype=str)
                employment=target.s7.to_numpy(dtype=float)
                size=np.select([np.isfinite(employment)&(employment>0)&(employment<20),
                                np.isfinite(employment)&(employment>=20)&(employment<100),
                                np.isfinite(employment)&(employment>=100)&(employment<250),
                                np.isfinite(employment)&(employment>=250)],
                               ['LT20','20_99','100_249','GE250'],default='UNKNOWN')
                for dimension,labels in [('sector',sector),('employment',size)]:
                    for label in sorted(set(labels)):
                        mask=labels==label
                        mass=math.fsum(w[mask]);contacts=math.fsum((w*chances)[mask])
                        groups.append({'cohort':'planning','route':'country_holdout','source':source,
                                       'country':holdout,'policy':policy,'quota':.5,'dimension':dimension,
                                       'group':label,'group_n':int(mask.sum()),
                                       'eligible_group_weight':mass,'group_expected_contacts':contacts,
                                       'contact_share_percent':100*contacts/metrics['expected_weighted_contacts'],
                                       'group_contact_rate_percent':100*contacts/mass})
    return rows,fit_receipts,groups


def compare(rows,canonical_dir):
    with (Path(canonical_dir)/'source_policy_quota_results.csv').open(encoding='utf-8-sig',newline='') as handle:
        source_rows=list(csv.DictReader(handle))
    maxima=Counter();checks=Counter();missing=[]
    for own in rows:
        candidates=[r for r in source_rows if r['cohort']=='planning' and r['source']==own['source'] and r['policy']==own['policy'] and abs(float(r['quota'])-.5)<1e-12 and r['route'] in {'country_holdout','leave_country_out','LOCO'}]
        if len(candidates)!=1:
            missing.append({k:own[k] for k in ['cohort','source','policy','quota']});continue
        actual=candidates[0]
        for key in ['expected_weighted_contacts','expected_weighted_cases','eligible_weighted_mass','cases_per_100_expected_contacts','event_prevalence_percent']:
            if key not in actual:continue
            error=abs(float(actual[key])-float(own[key]));maxima[key]=max(maxima[key],error);checks[key]+=1
            if error>1e-7:raise ValueError(f'Independent {key} differs for {own["source"]} / {own["policy"]}: {error}')
    if missing:raise ValueError('Missing/duplicate canonical key: '+json.dumps(missing))
    by={(r['source'],r['policy']):r['cases_per_100_expected_contacts'] for r in rows}
    contrasts={}
    for label,a,b in [('MOST5_vs_B','B_MOST5','B'),('MAX5_vs_MOST5','B_MAX5','B_MOST5')]:
        per_source={s:by[s,a]-by[s,b] for s in protocol_sources(by)}
        per_country={}
        for s,value in per_source.items():per_country.setdefault(country(s),[]).append(value)
        country_values={k:math.fsum(v)/len(v) for k,v in per_country.items()}
        contrasts[label]={'source_differences':per_source,'country_differences':country_values,
                          'equal_country_mean':math.fsum(country_values.values())/len(country_values)}
    return {'status':'PASS','comparisons':dict(checks),'maximum_errors':dict(maxima),'contrasts':contrasts}


def protocol_sources(by):return sorted({key[0] for key in by})


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--microdata',required=True,type=Path);ap.add_argument('--protocol',required=True,type=Path)
    ap.add_argument('--h1-cells',required=True,type=Path);ap.add_argument('--output',required=True,type=Path)
    ap.add_argument('--canonical-run',type=Path);ap.add_argument('--prepare-only',action='store_true')
    args=ap.parse_args()
    if digest(args.protocol)!=PROTOCOL_SHA:raise ValueError('H4 protocol identity differs')
    if args.output.exists():raise ValueError('Choose a new output directory')
    protocol=json.loads(args.protocol.read_text());raw=read_raw(args.microdata,protocol)
    cohorts,bases,cohort_qa=prepare(raw,protocol)
    h1qa=verify_h1_cells(bases['planning'],args.h1_cells)
    args.output.mkdir(parents=True)
    (args.output/'INDEPENDENT_COHORT_QA.json').write_text(json.dumps({'status':'PASS','cohorts':cohort_qa,'H1_parity':h1qa},indent=2)+'\n')
    if args.prepare_only:
        print(json.dumps({'status':'PASS','scope':'Independent raw cohort and H1-label checks; no H4 fits','cohorts':{k:v['matched_primary_N'] for k,v in cohort_qa.items()}}));return
    rows,fits,groups=score_primary(cohorts['planning'],protocol)
    with (args.output/'INDEPENDENT_PRIMARY_SOURCE_RESULTS.csv').open('w',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    with (args.output/'INDEPENDENT_PRIMARY_GROUP_RESULTS.csv').open('w',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(groups[0]));writer.writeheader();writer.writerows(groups)
    receipt={'status':'RECOMPUTED_PENDING_CANONICAL_COMPARISON','scope':'Independent same-raw-data planning B/B_MOST5/B_MAX5 q50 country exclusions',
             'raw_sha256':RAW_SHA,'protocol_sha256':PROTOCOL_SHA,'verifier_sha256':digest(Path(__file__)),
             'computational_H4_modules_imported':False,'fit_count':len(fits),'source_policy_rows':len(rows),
             'group_metric_rows':len(groups),
             'H1_parity':h1qa,'fit_receipts':fits,'individual_records_predictions_or_identifiers_saved':False,
             'environment':{'python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__,'sklearn':sklearn.__version__}}
    if args.canonical_run:
        receipt['canonical_comparison']=compare(rows,args.canonical_run);receipt['status']='PASS'
    (args.output/'INDEPENDENT_PRIMARY_QA.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({'status':receipt['status'],'fits':len(fits),'source_policy_rows':len(rows)}))

if __name__=='__main__':main()
