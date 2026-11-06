#!/usr/bin/env python3
"""Locked retrospective H5 follow-up. No row records or predictions are saved."""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
from hashlib import sha256
import json,math,platform,sys
from pathlib import Path
import numpy as np
import pandas as pd
import sklearn
from sklearn.tree import DecisionTreeClassifier
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from threadpoolctl import threadpool_limits
from pilot_data import load_raw,load_frozen,digest,encode_routine,employment_groups
from pilot_primitives import FixedNumericEncoder,fit_logistic_risk,expected_contact_probabilities,score_contacts,group_contact_shares,group_contact_rates
from run_h4_pilot import (prepare_cohorts,balanced_fit_weights,DOMAINS,ROUTINE_CATS,
                          membership,country,write_json,write_csv,require,array_digest)

PROTOCOL_SHA='6a2fe9d4fcc2ff83d960681c10881ea78060614b43383f857733558e96c73874'
ROOT=Path(__file__).resolve().parent.parent
H4_SHA='a62c851289541a00e387c68f8bcbc31c78677c18116c714f46c180af2858f777'
DOMAINS={**DOMAINS,'plan_MOST5':[str(x) for x in range(1,6)],'admin_MOST5':[str(x) for x in range(1,6)]}

def prepare(raw,frozen,h4):
    old,qa=prepare_cohorts(raw,frozen,h4)
    planning=old['planning'].copy()
    admin=old['administration'][['country','firmid','MOST']].rename(columns={'MOST':'admin_MOST'})
    common=planning.merge(admin,on=['country','firmid'],how='inner',validate='one_to_one')
    common['eval_weight']=common.base_wt/common.groupby('country').base_wt.transform('mean')
    common=common.sort_values(['country','firmid'],kind='stable').reset_index(drop=True)
    # The intersection carries the planning event; administration event is never merged.
    for f in [planning,common]:f['plan_MOST']=f.MOST
    qa2={}
    for name,f in [('planning_H4',planning),('common_functions',common)]:
        p=f.loc[f.country.isin(h4['primary_sources'])]
        qa2[name]={'primary_n':len(p),'all_n':len(f),'primary_membership_sha256':membership(p),
                   'source_counts':{str(k):int(v) for k,v in f.groupby('country').size().items()},
                   'planning_event_preserved':True,'weight_normalisation':'mean-one within matched source'}
    # Match every retained event against H4 planning by exact firm key.
    linked=common[['country','firmid','event']].merge(planning[['country','firmid','event']],on=['country','firmid'],suffixes=('_h5','_h4'),validate='one_to_one')
    require(linked.event_h5.equals(linked.event_h4),'Planning event changed in common cohort')
    return {'planning_H4':planning,'common_functions':common}, {'status':'PASS','H4_cohorts':qa,'H5_cohorts':qa2,'common_event_comparisons':len(linked),'common_event_mismatches':0}

def features(frame):
    f=encode_routine(frame)
    f['plan_MOST5']=frame.plan_MOST.astype(int).astype(str)
    if 'admin_MOST' in frame:f['admin_MOST5']=frame.admin_MOST.astype(int).astype(str)
    return f

def fit(train,test,policy):
    family,spec=policy.split('_',1)
    tech={'B':[],'B_plan_MOST5':['plan_MOST5'],'B_admin_MOST5':['admin_MOST5'],
          'B_both_MOST5':['plan_MOST5','admin_MOST5']}[spec]
    cats=ROUTINE_CATS+tech;nums=['start_year']
    w,masses=balanced_fit_weights(train);y=train.event.to_numpy(int)
    tr=features(train);te=features(test)
    fitted=fit_logistic_risk(tr,y,w,cats,nums,C=1.,max_iter=2000,tol=1e-8,categorical_domains=DOMAINS) if family=='logistic' else None
    constant=float(y[0]) if len(np.unique(y))==1 else None
    params={'policy':policy,'train_n':len(train),'train_membership_sha256':membership(train),
            'training_countries':sorted(train.reporting_country.unique()),'training_country_weight_masses':masses,
            'fit_weight_sum':math.fsum(w),'fit_weight_sha256':array_digest(w),'categorical_features':cats,'numeric_features':nums,
            'one_class_constant':constant}
    if constant is not None:
        def predict(f):return np.full(len(f),constant,dtype=float)
        scores=predict(te)
    else:
        if family=='logistic':enc=fitted.pipeline.named_steps['features']
        else:
            cat=Pipeline([('impute',SimpleImputer(strategy='constant',fill_value='UNKNOWN',keep_empty_features=True)),('encode',OneHotEncoder(categories=[DOMAINS[x] for x in cats],handle_unknown='ignore',sparse_output=False,dtype=float))])
            enc=ColumnTransformer([('categorical',cat,cats),('numeric',FixedNumericEncoder(),nums)],remainder='drop')
            enc.fit(tr[[*cats,*nums]])
        num=enc.named_transformers_['numeric']
        params.update(feature_names=enc.get_feature_names_out().tolist(),numeric_training_medians=num.statistics_.tolist(),
                      numeric_training_means=num.scaler_.mean_.tolist(),numeric_training_scales=num.scaler_.scale_.tolist())
        if family=='logistic':
            clf=fitted.pipeline.named_steps['risk'];predict=fitted.predict;scores=predict(te)
            params.update(coefficients=clf.coef_[0].tolist(),intercept=float(clf.intercept_[0]),solver_iterations=int(clf.n_iter_[0]))
        else:
            clf=DecisionTreeClassifier(criterion='gini',splitter='best',max_depth=3,min_samples_leaf=50,min_samples_split=2,
                                       random_state=20261105,ccp_alpha=0.,class_weight=None,max_features=None)
            clf.fit(enc.transform(tr[[*cats,*nums]]),y,sample_weight=w)
            def predict(f):return clf.predict_proba(enc.transform(f[[*cats,*nums]]))[:,list(clf.classes_).index(1)]
            scores=predict(te)
            params.update(tree_depth=int(clf.get_depth()),tree_leaves=int(clf.get_n_leaves()),
                          tree_children_left=clf.tree_.children_left.tolist(),tree_children_right=clf.tree_.children_right.tolist(),
                          tree_feature=clf.tree_.feature.tolist(),tree_threshold=clf.tree_.threshold.tolist(),
                          tree_value=clf.tree_.value.tolist(),tree_weighted_n_node_samples=clf.tree_.weighted_n_node_samples.tolist())
    require(np.array_equal(scores,predict(te.iloc[::-1])[::-1]),'Score changed under target reversal')
    changed=te.copy();changed['event']=1-test.event.to_numpy(int)
    require(np.array_equal(scores,predict(changed)),'Target event changed score')
    # Extra irrelevant target fields must be ignored by the retained fitted model.
    changed=te.copy();changed['e6a']=1e99;changed['s7']=-1;changed['country']='WRONG';changed['firmid']=-1
    require(np.array_equal(scores,predict(changed)),'Excluded field influenced model')
    params['target_prediction_invariances']=['row reversal exact','target event ignored','excluded fields ignored']
    return scores,params

def summarise(results,groups,pairs,out):
    # Every primary source contributes once per policy/quota, with equal-source India averaging.
    d=pd.DataFrame(results);g=pd.DataFrame(groups);p=pd.DataFrame(pairs)
    primary=d.loc[d.route.eq('country_holdout')]
    dims=['cohort','policy','quota','country'];metrics=['cases_per_100_expected_contacts','yield_delta_vs_B','yield_delta_vs_lottery','sector_tv_vs_B_pp','employment_tv_vs_B_pp']
    c=primary.groupby(dims,as_index=False)[metrics].mean()
    write_csv(out/'country_policy_quota_results.csv',c.to_dict('records'))
    sums=[]
    for key,a in c.groupby(['cohort','policy','quota'],sort=True):
        row=dict(zip(['cohort','policy','quota'],key));row['country_n']=len(a)
        for metric in metrics:
            v=a[metric].to_numpy(float);row[metric+'_mean']=float(v.mean());row[metric+'_min']=float(v.min());row[metric+'_max']=float(v.max())
        row['positive_increment_country_n']=int((a.yield_delta_vs_B>1e-10).sum());row['negative_increment_country_n']=int((a.yield_delta_vs_B<-1e-10).sum())
        sums.append(row)
    write_csv(out/'equal_country_policy_summaries.csv',sums)
    if len(p):
        num=[x for x in p.columns if x not in ['cohort','route','source','country','family','quota','n','target_membership_sha256']]
        pc=p.loc[p.route.eq('country_holdout')].groupby(['cohort','family','quota','country'],as_index=False)[num].mean()
        write_csv(out/'country_function_contrasts.csv',pc.to_dict('records'))
        s=[]
        for key,a in pc.groupby(['cohort','family','quota'],sort=True):
            row=dict(zip(['cohort','family','quota'],key));row['country_n']=len(a)
            for metric in num:
                v=a[metric].to_numpy(float);row[metric+'_mean']=float(v.mean());row[metric+'_min']=float(v.min());row[metric+'_max']=float(v.max())
                if metric=='admin_minus_plan_yield':row['admin_positive_country_n']=int((v>1e-10).sum());row['admin_negative_country_n']=int((v<-1e-10).sum());row['admin_zero_country_n']=int((np.abs(v)<=1e-10).sum())
            s.append(row)
        write_csv(out/'equal_country_function_summaries.csv',s)

def run(raw_path,out,prepare_only=False):
    protocol_path=ROOT/'protocol/H5_PROTOCOL.json';h4_path=ROOT/'protocol/H4_PROTOCOL.json'
    require(digest(protocol_path)==PROTOCOL_SHA,'H5 protocol hash mismatch');require(digest(h4_path)==H4_SHA,'H4 protocol hash mismatch')
    require(not out.exists(),'Output must be a new directory')
    protocol=json.loads(protocol_path.read_text());h4=json.loads(h4_path.read_text())
    raw=load_raw(raw_path);frozen=load_frozen(ROOT/'inputs/run_e4_frozen_analysis_v1.0.2.py')
    cohorts,qa=prepare(raw,frozen,h4);out.mkdir(parents=True)
    write_json(out/'COHORT_QA.json',qa)
    if prepare_only:return {'status':'COHORT_PREPARATION_ONLY_NO_EMPIRICAL_SCORES'}
    timing={'run_started_utc':datetime.now(timezone.utc).isoformat(),'first_fit_utc':None}
    rows=[];groups=[];pairs=[];fit_count=0;invariances=[]
    try:
        for name,frame in cohorts.items():
            primary=frame.loc[frame.country.isin(h4['primary_sources'])].copy()
            folds=[('country_holdout',ct,primary.loc[primary.reporting_country.ne(ct)].copy(),primary.loc[primary.reporting_country.eq(ct)].copy()) for ct in sorted(primary.reporting_country.unique())]
            folds.append(('secondary_targets','all_primary_training',primary.copy(),frame.loc[frame.country.isin(h4['secondary_targets'])].copy()))
            for route,held,train,test in folds:
                require(not set(train.reporting_country)&set(test.reporting_country),'Country contamination')
                test=test.sort_values(['country','firmid'],kind='stable').reset_index(drop=True)
                fits=[];scores={}
                for policy in protocol['policies'][name]:
                    if timing['first_fit_utc'] is None:
                        timing['first_fit_utc']=datetime.now(timezone.utc).isoformat();write_json(out/'TIMING.json',timing)
                    score,params=fit(train,test,policy);require(np.isfinite(score).all(),'Nonfinite score')
                    scores[policy]=score;params.update(cohort=name,held_out_country=held,target_membership_sha256=membership(test),score_sha256=array_digest(score));fits.append(params);fit_count+=1
                write_json(out/'fit_locks'/name/(held.replace(' ','_')+'.json'),{'status':'SCORES_LOCKED_BEFORE_METRICS','protocol_sha256':PROTOCOL_SHA,'fits':fits})
                for source,indices in test.groupby('country',sort=True).groups.items():
                    idx=np.asarray(indices,dtype=int);part=test.loc[idx];w=part.eval_weight.to_numpy(float);feat=features(part)
                    labels={'sector':feat.sector.to_numpy(str),'employment':employment_groups(part)}
                    for q in protocol['quotas']:
                        alloc={policy:expected_contact_probabilities(score[idx],w,q) for policy,score in scores.items()}
                        lottery=score_contacts(part.event.to_numpy(),w,np.full(len(part),q));metrics={p:score_contacts(part.event.to_numpy(),w,a) for p,a in alloc.items()}
                        shares={};rates={}
                        for policy,a in alloc.items():
                            require(np.array_equal(a,expected_contact_probabilities(scores[policy][idx][::-1],w[::-1],q)[::-1]),'Allocation changed under reversal')
                            baseline=policy.split('_',1)[0]+'_B'
                            row={'cohort':name,'route':route,'source':source,'country':country(source),'policy':policy,'quota':q,'n':len(part),
                                 'score_distinct_values':len(np.unique(scores[policy][idx])),'target_membership_sha256':membership(part),**metrics[policy],
                                 'yield_delta_vs_B':metrics[policy]['cases_per_100_expected_contacts']-metrics[baseline]['cases_per_100_expected_contacts'],
                                 'yield_delta_vs_lottery':metrics[policy]['cases_per_100_expected_contacts']-lottery['cases_per_100_expected_contacts']}
                            shares[policy]={};rates[policy]={}
                            for dimension,label in labels.items():
                                sh=group_contact_shares(label,w,a);ra=group_contact_rates(label,w,a);bsh=group_contact_shares(label,w,alloc[baseline])
                                shares[policy][dimension]=sh;rates[policy][dimension]=ra
                                row[dimension+'_tv_vs_B_pp']=sum(abs(sh[k]-bsh[k]) for k in sh)/2
                                for group in sh:
                                    mask=label==group
                                    groups.append({'cohort':name,'route':route,'source':source,'country':country(source),'policy':policy,'quota':q,'dimension':dimension,'group':group,
                                                   'group_n':int(mask.sum()),'eligible_weighted_group_mass':math.fsum(w[mask]),'expected_contact_share_percent':sh[group],
                                                   'within_group_contact_rate_percent':ra[group]})
                            rows.append(row)
                        if name=='common_functions':
                            for family in ['logistic','tree']:
                                plan=family+'_B_plan_MOST5';admin=family+'_B_admin_MOST5';base=family+'_B';both=family+'_B_both_MOST5'
                                wp=w*alloc[plan];wa=w*alloc[admin]
                                row={'cohort':name,'route':route,'source':source,'country':country(source),'family':family,'quota':q,'n':len(part),'target_membership_sha256':membership(part),
                                     'admin_minus_plan_yield':metrics[admin]['cases_per_100_expected_contacts']-metrics[plan]['cases_per_100_expected_contacts'],
                                     'plan_minus_B_yield':metrics[plan]['cases_per_100_expected_contacts']-metrics[base]['cases_per_100_expected_contacts'],
                                     'admin_minus_B_yield':metrics[admin]['cases_per_100_expected_contacts']-metrics[base]['cases_per_100_expected_contacts'],
                                     'both_minus_B_yield':metrics[both]['cases_per_100_expected_contacts']-metrics[base]['cases_per_100_expected_contacts'],
                                     'function_expected_allocation_tv_pp':50*math.fsum(np.abs(wp/math.fsum(wp)-wa/math.fsum(wa)))}
                                for dim in labels:
                                    row[dim+'_function_tv_pp']=sum(abs(shares[plan][dim][k]-shares[admin][dim][k]) for k in shares[plan][dim])/2
                                pairs.append(row)
                invariances.append({'cohort':name,'held_out_country':held,'policies':len(fits),'score_target_event_ignored':True,'score_reversal_exact':True,'irrelevant_fields_ignored':True,'allocation_reversal_exact':True,'scores_locked_before_metrics':True})
                print(json.dumps({'cohort':name,'fold':held,'status':'PASS'}),flush=True)
        write_csv(out/'source_policy_quota_results.csv',rows);write_csv(out/'group_contact_results.csv',groups);write_csv(out/'source_function_contrasts.csv',pairs)
        summarise(rows,groups,pairs,out)
        require(len(rows)==(4+8)*14*4,'Incomplete source/policy/quota rows')
        write_json(out/'INVARIANCE_QA.json',{'status':'PASS','folds':invariances})
        # Baseline parity is tested separately against the archived H4 original results.
        status={'status':'PASS','scope':'LOCKED_RETROSPECTIVE_H5_FOLLOWUP','protocol_sha256':PROTOCOL_SHA,'raw_zip_sha256':digest(raw_path),
                'timing':timing,'fit_policy_records':fit_count,'fold_tasks':len(invariances),'source_policy_quota_rows':len(rows),'group_rows':len(groups),
                'function_contrast_rows':len(pairs),'row_records_or_identifiers_or_predictions_saved':False,
                'runtime':{'python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__,'sklearn':sklearn.__version__},
                'code_sha256':{p.name:digest(p) for p in Path(__file__).parent.glob('*.py')}}
        write_json(out/'RUN_STATUS.json',status);return status
    except Exception as e:
        write_json(out/'RUN_STATUS.json',{'status':'FAILED','reason':str(e),'protocol_sha256':PROTOCOL_SHA});raise

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--microdata',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--prepare-only',action='store_true');a=ap.parse_args()
    with threadpool_limits(limits=1):r=run(a.microdata.resolve(),a.output.resolve(),a.prepare_only)
    print(json.dumps(r,sort_keys=True))
