#!/usr/bin/env python3
"""Execute the locked retrospective H4 information-value pilot from original FAT.

No establishment records, identifiers or prediction vectors are written.
Outputs are private aggregate results and computational provenance only.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime,timezone
from hashlib import sha256
import io
import json
import math
import os
from pathlib import Path
import platform
import sys
import tempfile

import numpy as np
import pandas as pd
import scipy
import sklearn
from threadpoolctl import threadpool_limits

from pilot_data import (H1_SHA,PRIMARY_FP,RAW_SHA,add_event_labels,adopted_max_state,
                        digest,employment_groups,encode_routine,load_frozen,load_raw,onehot_state)
from pilot_primitives import (expected_contact_probabilities,fit_logistic_risk,
                              group_contact_rates,group_contact_shares,score_contacts,training_category_risks)

PROTOCOL_SHA='a62c851289541a00e387c68f8bcbc31c78677c18116c714f46c180af2858f777'
ADDENDUM_SHA='a642133ea710cf15db06ae172df4d718d15f7388820b0324d86938a6c5388fd1'
DOMAINS={'sector':[str(x) for x in [*range(1,12),101,102]]+['UNKNOWN'],
         'multi_establishment':['0','1','UNKNOWN'],
         'foreign_owner':['DOMESTIC','ANY_FOREIGN','UNKNOWN'],
         'MOST5':[str(x) for x in range(1,6)],'MAX5':[str(x) for x in range(1,6)],
         'MOST_binary':['0','1'],'MAX_binary':['0','1']}
ROUTINE_CATS=['sector','multi_establishment','foreign_owner']
BASE_SPEC={'B':([],False),'B_MOST_binary':(['MOST_binary'],False),'B_MOST5':(['MOST5'],False),
           'B_MAX_binary':(['MAX_binary'],False),'B_MAX5':(['MAX5'],False),
           'B_MOST5_MAX5':(['MOST5','MAX5'],False),'B_SIZE':([],True),
           'B_SIZE_MOST5':(['MOST5'],True),'B_SIZE_MAX5':(['MAX5'],True)}


def require(ok,message):
    if not ok:raise ValueError(message)


def atomic_bytes(path,payload):
    path.parent.mkdir(parents=True,exist_ok=True)
    descriptor,temp=tempfile.mkstemp(prefix='.'+path.name+'.',suffix='.tmp',dir=path.parent)
    temp=Path(temp)
    try:
        with os.fdopen(descriptor,'wb') as f:
            if f.write(payload)!=len(payload):raise OSError('Short output write')
            f.flush();os.fsync(f.fileno())
        require(temp.read_bytes()==payload,'Temporary output readback differs')
        os.replace(temp,path)
        require(path.read_bytes()==payload,'Final output readback differs')
    finally:
        if temp.exists():temp.unlink()


def write_json(path,value):
    atomic_bytes(path,(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n').encode())


def write_csv(path,rows):
    require(bool(rows),'Empty aggregate output: '+str(path))
    stream=io.StringIO(newline='')
    writer=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator='\n')
    writer.writeheader();writer.writerows(rows)
    atomic_bytes(path,stream.getvalue().encode())


def membership(frame):
    d=frame.sort_values(['country','firmid'],kind='stable')
    payload='\n'.join(str(s)+'|'+str(int(i)) for s,i in d[['country','firmid']].itertuples(index=False,name=None))+'\n'
    return sha256(payload.encode()).hexdigest()


def array_digest(values):return sha256(np.asarray(values,dtype='<f8').tobytes()).hexdigest()


def country(source):
    return {'India_Wave2_New':'India','BurkinaFaso':'Burkina Faso','Korea':'Republic of Korea','Vietnam':'Viet Nam'}.get(source,source)


def balanced_fit_weights(frame):
    out=frame.base_wt.astype(float)/frame.groupby('country').base_wt.transform('sum')
    source_country=frame[['country','reporting_country']].drop_duplicates()
    counts=source_country.groupby('reporting_country').size()
    out=out/frame.reporting_country.map(counts)
    out=out*(len(frame)/math.fsum(out))
    require(abs(math.fsum(out)-len(frame))<=1e-8,'Fit-weight global scale differs from Ntrain')
    masses=out.groupby(frame.reporting_country).sum()
    target=len(frame)/len(masses)
    require(np.max(np.abs(masses.to_numpy()-target))<1e-8,'Training countries not balanced')
    return out.to_numpy(float),{str(k):float(v) for k,v in masses.items()}


def prepare_cohorts(raw,frozen,protocol):
    sources=protocol['primary_sources']+protocol['secondary_targets']
    require(len(set(sources))==14,'Unexpected source contract')
    positive=np.isfinite(raw[['e6a','s7','base_wt']].to_numpy(float)).all(axis=1)&raw.e6a.gt(0)&raw.s7.gt(0)&raw.base_wt.gt(0)
    results={};qa={}
    for name,mp,ap in [('planning','ib9b','db9a'),('administration','ib8b','db8a')]:
        state,valid=onehot_state(raw,mp)
        base=raw.loc[positive&raw.country.isin(sources)&valid].copy()
        base['MOST']=state.loc[base.index]
        base=add_event_labels(base,frozen)
        primary_base=base.loc[base.country.isin(protocol['primary_sources'])]
        expected=protocol['cohorts'][name]
        require(len(primary_base)==expected['expected_primary_MOST_N'],name+' MOST base count differs')
        if name=='planning':require(membership(primary_base)==PRIMARY_FP,'H1 primary membership differs')
        maximum,adopt_valid=adopted_max_state(base,ap)
        matched=base.loc[adopt_valid].copy()
        matched['MAX']=maximum.loc[matched.index]
        array=matched[[ap+str(i) for i in range(1,6)]].to_numpy()
        require(np.all(array[np.arange(len(matched)),matched.MOST.to_numpy(int)-1]==1),name+' MOST/adoption contradiction')
        require(len(matched.loc[matched.country.isin(protocol['primary_sources'])])==expected['expected_primary_matched_N'],name+' matched count differs')
        matched['reporting_country']=matched.country.map(country)
        matched['eval_weight']=matched.base_wt/matched.groupby('country').base_wt.transform('mean')
        matched=matched.sort_values(['country','firmid'],kind='stable').reset_index(drop=True)
        results[name]=matched
        qa[name]={'MOST_base_primary_n':len(primary_base),'MOST_base_primary_membership_sha256':membership(primary_base),
                  'matched_primary_n':int(matched.country.isin(protocol['primary_sources']).sum()),
                  'matched_primary_membership_sha256':membership(matched.loc[matched.country.isin(protocol['primary_sources'])]),
                  'full_matched_n':len(matched),'labels_fixed_before_adoption_matching':True,
                  'MOST_adoption_contradictions':0}
    most,validmost=onehot_state(raw,'ib9b')
    maximum,validadopt=adopted_max_state(raw,'db9a')
    value=pd.to_numeric(raw.d3c,errors='coerce')
    known=np.isfinite(value)&value.ge(0)&value.eq(np.floor(value))&value.ne(2500000)
    base=(raw.country.isin(sources)&np.isfinite(raw.base_wt)&raw.base_wt.gt(0)&validmost&validadopt&known)
    for name,mask in [('finance_planning',base),('finance_planning_excluding99',base&value.ne(99))]:
        matched=raw.loc[mask].copy()
        matched['MOST']=most.loc[matched.index];matched['MAX']=maximum.loc[matched.index]
        a=matched[['db9a'+str(i) for i in range(1,6)]].to_numpy()
        require(np.all(a[np.arange(len(matched)),matched.MOST.to_numpy(int)-1]==1),name+' MOST/adoption contradiction')
        matched['event']=value.loc[matched.index].gt(0)
        matched['reporting_country']=matched.country.map(country)
        matched['eval_weight']=matched.base_wt/matched.groupby('country').base_wt.transform('mean')
        matched=matched.sort_values(['country','firmid'],kind='stable').reset_index(drop=True)
        results[name]=matched
        primary=matched.loc[matched.country.isin(protocol['primary_sources'])]
        qa[name]={'matched_primary_n':len(primary),'matched_primary_membership_sha256':membership(primary),
                  'full_matched_n':len(matched),'sales_or_employment_eligibility_restriction':False,
                  'excluded_2500000_n':int((raw.country.isin(sources)&value.eq(2500000)).sum()),
                  'excluded_99':name.endswith('excluding99'),'MOST_adoption_contradictions':0,
                  'outcome':'Reported unmet borrowing for production expansion; provisional cross-source harmonisation'}
    # A01 isolates objective choice from a change in the analytical population.
    planning=results['planning']
    finance_value=pd.to_numeric(planning.d3c,errors='coerce')
    paired=planning.loc[np.isfinite(finance_value)&finance_value.ge(0)&finance_value.eq(np.floor(finance_value))&finance_value.ne(2500000)].copy()
    paired['eval_weight']=paired.base_wt/paired.groupby('country').base_wt.transform('mean')
    paired=paired.sort_values(['country','firmid'],kind='stable').reset_index(drop=True)
    for name in ['paired_common_productivity','paired_common_finance']:
        current=paired.copy()
        if name.endswith('finance'):current['event']=pd.to_numeric(current.d3c).gt(0)
        results[name]=current
        primary=current.loc[current.country.isin(protocol['primary_sources'])]
        qa[name]={'matched_primary_n':len(primary),'matched_primary_membership_sha256':membership(primary),
                  'full_matched_n':len(current),'same_rows_both_objectives':True,
                  'productivity_labels_fixed_before_finance_restriction':True}
    for name,frame in results.items():
        require(set(frame.country)==set(sources),name+' lacks a required source')
        qa[name]['source_counts']={str(k):int(v) for k,v in frame.groupby('country').size().items()}
    return results,qa


def feature_frame(frame):
    result=encode_routine(frame)
    for label in ['MOST','MAX']:
        result[label+'5']=frame[label].astype(int).astype(str)
        result[label+'_binary']=frame[label].gt(1).astype(int).astype(str)
    return result


def fit_policy_scores(train,test,policy,protocol):
    w,country_masses=balanced_fit_weights(train)
    y=train.event.to_numpy(int)
    params={'policy':policy,'training_n':len(train),'training_countries':sorted(set(train.reporting_country)),
            'training_membership_sha256':membership(train),'training_country_fit_weight_mass':country_masses,
            'fit_weight_sum':math.fsum(w),'fit_weight_sha256':array_digest(w)}
    if policy=='lottery':return np.zeros(len(test)),params
    if policy.startswith('fixed_'):
        label=policy[len('fixed_'):]
        state=test['MOST' if label.startswith('MOST') else 'MAX'].to_numpy(float)
        scores=-(state>1).astype(float) if label.endswith('binary') else -state
        params['scoring_rule']='Original ascending technology priority; no outcomes used'
        return scores,params
    if policy.startswith('learned_'):
        field='MOST' if policy=='learned_MOST5' else 'MAX'
        risks,baseline=training_category_risks(train[field].astype(int).astype(str),y,w,smoothing_mass=5.)
        scores=test[field].astype(int).astype(str).map(risks).fillna(baseline).to_numpy(float)
        params.update(state_training_risks=risks,unseen_state_fallback=baseline,pseudo_observations=5.)
        return scores,params
    tech,add_size=BASE_SPEC[policy]
    categorical=[*ROUTINE_CATS,*tech]
    numeric=['start_year']+(['log_employment'] if add_size else [])
    train_features=feature_frame(train);test_features=feature_frame(test)
    model=fit_logistic_risk(train_features,y,w,categorical,numeric,C=protocol['model']['C'],
                            max_iter=protocol['model']['max_iter'],tol=protocol['model']['tolerance'],categorical_domains=DOMAINS)
    scores=model.predict(test_features)
    params.update(categorical_features=categorical,numeric_features=numeric,
                  always_unscaled_numeric_missing_indicators=True,one_class_fallback=model.constant)
    if model.pipeline is not None:
        encoded=model.pipeline.named_steps['features']
        num=encoded.named_transformers_['numeric']
        classifier=model.pipeline.named_steps['risk']
        params.update(feature_names=encoded.get_feature_names_out().tolist(),
                      numeric_training_medians=num.statistics_.tolist(),numeric_training_means=num.scaler_.mean_.tolist(),
                      numeric_training_scales=num.scaler_.scale_.tolist(),coefficients=classifier.coef_[0].tolist(),
                      intercept=float(classifier.intercept_[0]),solver_iterations=int(classifier.n_iter_[0]))
    # The declared target outcome may not influence model inputs or predictions.
    permuted=test_features.copy();permuted['event']=1-test.event.to_numpy(int)
    require(np.array_equal(scores,model.predict(permuted)),'Target label perturbation changed predictions')
    return scores,params


def run(raw_path,frozen_path,h1_path,protocol_path,addendum_path,output,prepare_only=False):
    require(digest(protocol_path)==PROTOCOL_SHA,'H4 locked protocol differs')
    require(digest(h1_path)==H1_SHA,'H1 identity differs')
    require(digest(addendum_path)==ADDENDUM_SHA,'H4 A01 addendum differs')
    require(not output.exists(),'Choose a new private output directory')
    protocol=json.loads(protocol_path.read_text())
    frozen=load_frozen(frozen_path)
    raw=load_raw(raw_path)
    cohorts,cohort_qa=prepare_cohorts(raw,frozen,protocol)
    output.mkdir(parents=True)
    write_json(output/'COHORT_QA.json',{'status':'PASS','H4_protocol_sha256':PROTOCOL_SHA,'A01_sha256':ADDENDUM_SHA,'cohorts':cohort_qa,
                                     'no_empirical_scores_computed':True})
    if prepare_only:return {'status':'COHORT_PREPARATION_PASS','output':str(output)}
    write_json(output/'RUN_STATUS.json',{'status':'RUNNING','protocol_sha256':PROTOCOL_SHA})
    all_results=[];all_groups=[];fit_records=[];invariance=[];paired_allocations={}
    timing={'run_started_utc':datetime.now(timezone.utc).isoformat(),'first_policy_score_utc':None,'first_empirical_fit_utc':None}
    try:
        for name,frame in cohorts.items():
            primary=frame.loc[frame.country.isin(protocol['primary_sources'])].copy()
            folds=[('country_holdout',ct,primary.loc[primary.reporting_country.ne(ct)].copy(),
                    primary.loc[primary.reporting_country.eq(ct)].copy()) for ct in sorted(primary.reporting_country.unique())]
            folds.append(('secondary_targets','all_primary_training',primary.copy(),frame.loc[frame.country.isin(protocol['secondary_targets'])].copy()))
            for route,heldout,train,test in folds:
                if route=='country_holdout':require(not set(train.reporting_country)&set(test.reporting_country),'Country overlap')
                if 'India' in set(test.reporting_country):require(set(test.country)=={'India','India_Wave2_New'},'India sources split')
                test=test.sort_values(['country','firmid'],kind='stable').reset_index(drop=True)
                fit_output=output/'fit_locks'/name/(heldout.replace(' ','_')+'.json')
                fold_records=[]
                # All scores are computed before the first target event enters a metric.
                policy_scores={}
                for policy in protocol['policies']:
                    changed=False
                    if timing['first_policy_score_utc'] is None:
                        timing['first_policy_score_utc']=datetime.now(timezone.utc).isoformat();changed=True
                    if timing['first_empirical_fit_utc'] is None and (policy.startswith('learned_') or policy in BASE_SPEC):
                        timing['first_empirical_fit_utc']=datetime.now(timezone.utc).isoformat();changed=True
                    if changed:write_json(output/'TIMING.json',timing)
                    scores,params=fit_policy_scores(train,test,policy,protocol)
                    require(np.isfinite(scores).all(),'Nonfinite score')
                    params.update(cohort=name,route=route,held_out_country=heldout,
                                  held_out_membership_sha256=membership(test),scores_sha256=array_digest(scores))
                    # Driver-level full target-label perturbation check, including fixed/learned rules.
                    altered=test.copy();altered['event']=~test.event.astype(bool)
                    scores2,params2=fit_policy_scores(train,altered,policy,protocol)
                    require(np.array_equal(scores,scores2),'Target events changed fitted or fixed scores')
                    require(params=={**params2,**{k:params[k] for k in ['cohort','route','held_out_country','held_out_membership_sha256','scores_sha256']}},'Target events changed fit parameters')
                    reversed_scores,_=fit_policy_scores(train,test.iloc[::-1].copy(),policy,protocol)
                    require(np.array_equal(scores,reversed_scores[::-1]),'Target row reordering changed score alignment')
                    policy_scores[policy]=scores;fold_records.append(params)
                write_json(fit_output,{'status':'FITTED_BEFORE_SCORING','protocol_sha256':PROTOCOL_SHA,'fits':fold_records})
                for source,indices in test.groupby('country',sort=True).groups.items():
                    idx=np.asarray(list(indices),dtype=int);part=test.loc[idx]
                    weights=part.eval_weight.to_numpy(float)
                    features=feature_frame(part)
                    groups={'sector':features.sector.to_numpy(str),'employment':employment_groups(part),
                            'MOST':part.MOST.astype(int).astype(str).to_numpy(),'MAX':part.MAX.astype(int).astype(str).to_numpy()}
                    for q in protocol['quotas']:
                        allocations={p:expected_contact_probabilities(s[idx],weights,q) for p,s in policy_scores.items()}
                        for policy,probs in allocations.items():
                            # Equal-score rows share one chance; probabilities are aligned under reversal.
                            reversed_probs=expected_contact_probabilities(policy_scores[policy][idx][::-1],weights[::-1],q)[::-1]
                            require(np.allclose(probs,reversed_probs,rtol=0,atol=1e-14),'Row order altered tied allocation')
                            metrics=score_contacts(part.event.to_numpy(),weights,probs)
                            row={'cohort':name,'route':route,'source':source,'country':country(source),'policy':policy,'quota':q,
                                 'n':len(part),'score_distinct_values':len(np.unique(policy_scores[policy][idx])),
                                 'target_membership_sha256':membership(part),**metrics}
                            lottery=score_contacts(part.event.to_numpy(),weights,allocations['lottery'])
                            baseline=score_contacts(part.event.to_numpy(),weights,allocations['B'])
                            row.update(yield_delta_vs_lottery=metrics['cases_per_100_expected_contacts']-lottery['cases_per_100_expected_contacts'],
                                       yield_delta_vs_B=metrics['cases_per_100_expected_contacts']-baseline['cases_per_100_expected_contacts'])
                            for group_name,labels in groups.items():
                                shares=group_contact_shares(labels,weights,probs);rates=group_contact_rates(labels,weights,probs)
                                baseline_shares=group_contact_shares(labels,weights,allocations['B'])
                                row[group_name+'_composition_tv_vs_B_pp']=sum(abs(shares[k]-baseline_shares[k]) for k in shares)/2
                                for label in shares:
                                    selected=labels==label
                                    all_groups.append({'cohort':name,'route':route,'source':source,'country':country(source),
                                                       'policy':policy,'quota':q,'dimension':group_name,'group':label,'group_n':int(selected.sum()),
                                                       'eligible_weighted_group_mass':math.fsum(weights[selected]),
                                                       'expected_contact_share_percent':shares[label],
                                                       'within_group_contact_rate_percent':rates[label]})
                            all_results.append(row)
                            if name.startswith('paired_common_'):
                                key=(route,source,policy,q)
                                paired_allocations.setdefault(key,{})[name]={'weights':weights,'probabilities':probs,
                                    'membership':membership(part),'groups':groups,'metrics':row}
                fit_records.extend(fold_records)
                invariance.append({'cohort':name,'route':route,'held_out_country':heldout,'policies_tested':len(protocol['policies']),
                                   'target_event_perturbation_scores_and_parameters_equal':True,'target_row_reordering_scores_equal':True,
                                   'allocation_reordering_tolerance':1e-14,'fit_lock_committed_before_metrics':True})
                print(json.dumps({'cohort':name,'fold':heldout,'status':'PASS'}),flush=True)
        write_csv(output/'source_policy_quota_results.csv',all_results)
        write_csv(output/'group_contact_results.csv',all_groups)
        cross=[];cross_groups=[]
        for (route,source,policy,q),pair in sorted(paired_allocations.items()):
            prod=pair['paired_common_productivity'];fin=pair['paired_common_finance']
            require(prod['membership']==fin['membership'],'Paired objective membership differs')
            require(np.array_equal(prod['weights'],fin['weights']),'Paired objective weights differ')
            wp=prod['weights']*prod['probabilities'];wf=fin['weights']*fin['probabilities']
            row={'route':route,'source':source,'country':country(source),'policy':policy,'quota':q,
                 'common_n':len(wp),'expected_allocation_tv_pp':50*float(np.abs(wp/math.fsum(wp)-wf/math.fsum(wf)).sum()),
                 'productivity_yield_per_100_contacts':prod['metrics']['cases_per_100_expected_contacts'],
                 'finance_yield_per_100_contacts':fin['metrics']['cases_per_100_expected_contacts'],
                 'productivity_yield_delta_vs_B':prod['metrics']['yield_delta_vs_B'],
                 'finance_yield_delta_vs_B':fin['metrics']['yield_delta_vs_B']}
            for dimension in ['sector','employment']:
                labels=prod['groups'][dimension]
                ps=group_contact_shares(labels,prod['weights'],prod['probabilities'])
                fs=group_contact_shares(labels,fin['weights'],fin['probabilities'])
                pr=group_contact_rates(labels,prod['weights'],prod['probabilities'])
                fr=group_contact_rates(labels,fin['weights'],fin['probabilities'])
                row[dimension+'_composition_tv_pp']=sum(abs(ps[k]-fs[k]) for k in ps)/2
                for group in ps:
                    cross_groups.append({'route':route,'source':source,'country':country(source),'policy':policy,'quota':q,
                                         'dimension':dimension,'group':group,'productivity_contact_share_percent':ps[group],
                                         'finance_contact_share_percent':fs[group],'finance_minus_productivity_share_pp':fs[group]-ps[group],
                                         'productivity_group_contact_rate_percent':pr[group],'finance_group_contact_rate_percent':fr[group],
                                         'finance_minus_productivity_group_rate_pp':fr[group]-pr[group]})
            if policy=='lottery' or policy.startswith('fixed_'):
                require(row['expected_allocation_tv_pp']<1e-10,'Outcome-independent policy changed across paired objectives')
            cross.append(row)
        write_csv(output/'cross_target_allocation.csv',cross)
        write_csv(output/'cross_target_group_differences.csv',cross_groups)
        write_json(output/'INVARIANCE_QA.json',{'status':'PASS','folds':invariance})
        write_json(output/'FIT_INVENTORY.json',{'status':'PASS','fitted_policy_records':len(fit_records),'records':fit_records})
        expected_rows=len(cohorts)*14*len(protocol['policies'])*len(protocol['quotas'])
        require(len(all_results)==expected_rows,'Model/source/quota inventory incomplete')
        # A result reader must recover every row, not merely observe exit status.
        for fname,rows in [('source_policy_quota_results.csv',all_results),('group_contact_results.csv',all_groups)]:
            with (output/fname).open(newline='') as f:require(len(list(csv.DictReader(f)))==len(rows),'Aggregate output truncated: '+fname)
        receipt={'status':'PASS','scope':'LOCKED_RETROSPECTIVE_H4_PRIVATE_PILOT','protocol_sha256':PROTOCOL_SHA,
                 'addendum_A01_sha256':ADDENDUM_SHA,'timing':timing,
                 'raw_zip_sha256':digest(raw_path),'frozen_e4_sha256':digest(frozen_path),'H1_protocol_sha256':digest(h1_path),
                 'cohort_count':len(cohorts),'source_policy_quota_rows':len(all_results),'private_group_rows':len(all_groups),
                 'fit_policy_records':len(fit_records),'country_folds_per_cohort':11,'secondary_target_fit_per_cohort':1,
                 'paired_objective_allocation_rows':len(cross),'paired_objective_group_difference_rows':len(cross_groups),
                 'policies':protocol['policies'],'quotas':protocol['quotas'],'all_required_rows_present':True,
                 'invariance_fold_checks':len(invariance),'row_records_identifiers_predictions_written':False,
                 'runtime':{'python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__,'scipy':scipy.__version__,'sklearn':sklearn.__version__},
                 'code_sha256':{p.name:digest(p) for p in [Path(__file__),Path(__file__).with_name('pilot_primitives.py'),Path(__file__).with_name('pilot_data.py')]},
                 'scientific_limits':protocol['uncertainty'],'finance_label':protocol['cohorts']['finance_planning']['event']}
        write_json(output/'RUN_STATUS.json',receipt)
        return receipt
    except Exception as exc:
        write_json(output/'RUN_STATUS.json',{'status':'FAILED_NO_COMPLETE_PILOT_CLAIM','reason':str(exc),'protocol_sha256':PROTOCOL_SHA})
        raise


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--microdata',type=Path,required=True)
    ap.add_argument('--frozen-e4',type=Path,required=True)
    ap.add_argument('--h1-protocol',type=Path,required=True)
    ap.add_argument('--protocol',type=Path,required=True)
    ap.add_argument('--addendum',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--prepare-only',action='store_true')
    args=ap.parse_args()
    with threadpool_limits(limits=1):
        result=run(args.microdata.resolve(),args.frozen_e4.resolve(),args.h1_protocol.resolve(),args.protocol.resolve(),args.addendum.resolve(),args.output.resolve(),args.prepare_only)
    print(json.dumps({'status':result['status'],'output':str(args.output.resolve())}))
