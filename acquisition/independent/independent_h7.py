#!/usr/bin/env python3
"""Independent H7 allocation, acquisition and inverse checks.

Does not import production acquisition primitives. No firm records or prediction
vectors are written. Inherited raw/cohort/model routines may be reused only by
explicit empirical check mode; numerical allocation logic is separate.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
import math
from pathlib import Path
import sys
from datetime import datetime,timezone
from hashlib import sha256
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]


def _vectors(scores,weights):
    s=np.asarray(scores,dtype=float);w=np.asarray(weights,dtype=float)
    if s.ndim!=1 or len(s)==0 or w.shape!=s.shape or not np.isfinite(s).all() or not np.isfinite(w).all() or np.any(w<=0):
        raise ValueError('Require matching nonempty finite scores and positive weights')
    return s,w


def _blocks(scores):
    # Separately enumerate equality classes, rather than splitting a sorted array.
    s=np.asarray(scores,dtype=float)
    return [np.flatnonzero(s==value) for value in sorted(set(s.tolist()),reverse=True)]


def allocation(scores,weights,quota):
    s,w=_vectors(scores,weights)
    if not math.isfinite(quota) or not 0<=quota<=1:raise ValueError('Quota outside [0,1]')
    target=float(quota)*math.fsum(w)
    p=np.zeros(len(s),dtype=float)
    consumed=0.
    for ix in _blocks(s):
        mass=math.fsum(w[ix])
        fill=max(0.,min(1.,(target-consumed)/mass))
        p[ix]=fill
        consumed=math.fsum([consumed,fill*mass])
    return p


def band(scores,weights,quota,radius):
    s,w=_vectors(scores,weights)
    if not 0<=quota<=1 or not 0<=radius<=1:raise ValueError('Invalid q or radius')
    if radius==0:return np.zeros(len(s),dtype=bool)
    if radius==1:return np.ones(len(s),dtype=bool)
    total=math.fsum(w)
    left=quota*(1-radius)*total
    right=(quota+(1-quota)*radius)*total
    p=np.zeros(len(s),dtype=bool)
    previous=0.
    for ix in _blocks(s):
        following=math.fsum([previous,math.fsum(w[ix])])
        if min(following,right)>max(previous,left):p[ix]=True
        previous=following
    return p


def selective(base_scores,rich_scores,weights,quota,queried):
    b,w=_vectors(base_scores,weights);r=np.asarray(rich_scores,dtype=float)
    m=np.asarray(queried,dtype=bool)
    if r.shape!=b.shape or m.shape!=b.shape:raise ValueError('Mismatched rich/mask')
    p=allocation(b,w,quota)
    if not m.any():return p
    if not np.isfinite(r[m]).all():raise ValueError('Nonfinite queried rich score')
    if m.all():return allocation(r,w,quota)
    mass=math.fsum(w[m]);reserved=math.fsum(w[m]*p[m])
    p[m]=allocation(r[m],w[m],reserved/mass)
    return p


def sector_fixed(base_scores,rich_scores,weights,quota,sector):
    b,w=_vectors(base_scores,weights);r=np.asarray(rich_scores,dtype=float);g=np.asarray(sector,dtype=str)
    if g.shape!=b.shape or r.shape!=b.shape:raise ValueError('Mismatched sector/rich')
    baseline=allocation(b,w,quota);p=np.zeros(len(b))
    for value in sorted(set(g.tolist())):
        ix=np.flatnonzero(g==value)
        mass=math.fsum(w[ix]);contacts=math.fsum(w[ix]*baseline[ix])
        p[ix]=allocation(r[ix],w[ix],contacts/mass)
    return p


def inverse(base_scores,weights,events,target_cases):
    b,w=_vectors(base_scores,weights);y=np.asarray(events,dtype=float)
    if y.shape!=b.shape or not np.isfinite(y).all() or not np.isin(y,[0.,1.]).all():raise ValueError('Invalid binary events')
    goal=float(target_cases);total=math.fsum(w);allcases=math.fsum(w*y)
    tol=1e-10*max(1.,allcases)
    if not math.isfinite(goal) or goal < -tol or goal > allcases+tol:raise ValueError('Target case mass unreachable')
    goal=min(allcases,max(0.,goal))
    if goal==0:return 0.
    contacts=0.;cases=0.;case_values=[];weight_values=[]
    tol=64*np.finfo(float).eps*max(1.,allcases)
    for ix in _blocks(b):
        blockmass=math.fsum(w[ix]);blockcases=math.fsum(w[ix]*y[ix])
        beforecases=math.fsum(case_values)
        beforeweight=math.fsum(weight_values)
        case_values.extend((w[ix]*y[ix]).tolist())
        weight_values.extend(w[ix].tolist())
        aftercases=math.fsum(case_values)
        if blockcases>0 and goal<=aftercases+tol:
            fraction=1. if abs(goal-aftercases)<=tol else (goal-beforecases)/blockcases
            return min(1.,max(0.,math.fsum([beforeweight,min(1.,max(0.,fraction))*blockmass])/total))
        cases=aftercases;contacts=math.fsum(weight_values)
    if abs(cases-goal)<=tol:return contacts/total
    raise ArithmeticError('Inverse did not reach target')


def yield_value(y,w,p):
    return 100*math.fsum(np.asarray(y,dtype=float)*w*p)/math.fsum(w*p)


def shares(g,w,p):
    g=np.asarray(g,dtype=str);t=math.fsum(w*p)
    return {key:100*math.fsum((w*p)[g==key])/t for key in sorted(set(g))}


def _load_prod():
    path=ROOT/'software/acquisition_primitives.py'
    spec=importlib.util.spec_from_file_location('h7_production_acquisition_for_comparison',path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod


def synthetic():
    prod=_load_prod()
    rng=np.random.default_rng(83971)
    errors=[];checks=0
    # Production API aliases are resolved explicitly from actual source by check caller.
    for trial in range(45):
        n=17+trial
        b=rng.integers(0,7,n).astype(float);r=rng.integers(0,9,n).astype(float)
        w=rng.uniform(.03,8.,n);y=rng.integers(0,2,n);g=rng.integers(0,4,n).astype(str)
        for q in [.2,.35,.5,.75]:
            p=allocation(b,w,q)
            a=prod.allocate(b,w,q)
            errors.append(float(np.max(np.abs(p-a))));checks+=1
            for radius in [0.,.1,.25,.5,1.]:
                m=band(b,w,q,radius);pm=prod.band_mask(b,w,q,radius)
                if not np.array_equal(m,pm):raise AssertionError('Band mask differs')
                a=prod.selective_allocate(b,r,w,q,m);ip=selective(b,r,w,q,m)
                errors.append(float(np.max(np.abs(a-ip))));checks+=1
            a=prod.sector_fixed_allocate(b,r,w,q,g);ip=sector_fixed(b,r,w,q,g)
            errors.append(float(np.max(np.abs(a-ip))));checks+=1
            goal=math.fsum(w*y*allocation(r,w,q))
            x=prod.capacity_equivalent(b,w,y,goal);ix=inverse(b,w,y,goal)
            errors.append(abs(x-ix));checks+=1
            if abs(math.fsum(w*y*allocation(b,w,ix))-goal)>1e-8:raise AssertionError('Inverse case mass fails')
    plateau_rng=np.random.default_rng(422)
    plateau_errors=[]
    for trial in range(10000):
        b=np.array([10,10,9,9,8,8,7,7,6,6,5,5],dtype=float)
        w=10.**plateau_rng.uniform(-5,5,12)
        y=np.array([1,1,1,1,0,0,0,0,1,1,0,1])
        goal=math.fsum(w[:4]);expected=math.fsum(w[:4])/math.fsum(w)
        pv=prod.capacity_equivalent(b,w,y,goal);iv=inverse(b,w,y,goal)
        plateau_errors.extend([abs(pv-expected),abs(iv-expected)])
        if abs(pv-expected)>1e-10 or abs(iv-expected)>1e-10:raise AssertionError('Leftmost plateau regression')
    maximum=max(errors)

    if maximum>1e-10:raise AssertionError('Independent primitive error '+str(maximum))
    return {'status':'PASS','independent_scalar_comparisons':checks,'max_absolute_difference':maximum,'plateau_regression_trials':10000,'plateau_max_absolute_quota_error':max(plateau_errors),'inverse_case_boundary_tolerance':'64*float64 epsilon*max(1,total_case_mass); no score rounding','score_ties':'exact score equality; no score rounding','fit_execution':False,'checked_utc':datetime.now(timezone.utc).isoformat()}


def outer_refits(raw_path,output,production):
    global PRODUCTION
    PRODUCTION=production
    """Refit all outer logistic models; independently compute every menu policy."""
    from threadpoolctl import threadpool_limits
    sys.path.insert(0,str(ROOT/'software'))
    from pilot_data import load_raw,load_frozen,employment_groups,encode_routine
    from run_h4_pilot import prepare_cohorts,country,membership
    from run_h5_followup import fit
    protocol=json.loads((ROOT/'protocol/H7_PROTOCOL.json').read_text())
    expected=protocol['input']['raw_zip_sha256']
    if sha256(raw_path.read_bytes()).hexdigest()!=expected:raise ValueError('Raw identity mismatch')
    h4=json.loads((ROOT/'protocol/H4_PROTOCOL.json').read_text())
    raw=load_raw(raw_path);frozen=load_frozen(ROOT/'inputs/run_e4_frozen_analysis_v1.0.2.py')
    cohorts,cohort_qa=prepare_cohorts(raw,frozen,h4)
    frame=cohorts['planning'].copy();frame['plan_MOST']=frame.MOST
    primary=frame.loc[frame.country.isin(protocol['primary_sources'])].copy()
    countries=sorted(primary.reporting_country.unique())
    contexts=[(ct,primary.loc[primary.reporting_country.ne(ct)].copy(),primary.loc[primary.reporting_country.eq(ct)].copy()) for ct in countries]
    contexts.append(('all_primary_training',primary.copy(),frame.loc[frame.country.isin(protocol['secondary_sources'])].copy()))
    output.mkdir(parents=True,exist_ok=False)
    records=[];fit_records=[];random_checks=[];random_inputs=[]
    start=datetime.now(timezone.utc).isoformat()
    with threadpool_limits(limits=1):
        for held,train,test in contexts:
            if set(train.reporting_country)&set(test.reporting_country):raise AssertionError('Outer country overlap')
            test=test.sort_values(['country','firmid'],kind='stable').reset_index(drop=True)
            B,bparam=fit(train,test,'logistic_B');R,rparam=fit(train,test,'logistic_B_plan_MOST5')
            fit_records.append({'held':held,'baseline':bparam,'rich':rparam,'score_B_sha256':sha256(np.asarray(B,dtype='<f8').tobytes()).hexdigest(),'score_rich_sha256':sha256(np.asarray(R,dtype='<f8').tobytes()).hexdigest()})
            for source,ix in test.groupby('country',sort=True).groups.items():
                ix=np.asarray(ix,dtype=int);part=test.loc[ix];b=B[ix];r=R[ix]
                w=part.eval_weight.to_numpy(float);y=part.event.to_numpy(int)
                sectors=encode_routine(part).sector.to_numpy(str);size=employment_groups(part)
                for q in protocol['quotas']:
                    bp=allocation(b,w,q);bcase=math.fsum(w*y*bp);bq=inverse(b,w,y,bcase)
                    by=yield_value(y,w,bp);bs=shares(sectors,w,bp);be=shares(size,w,bp)
                    policies=[]
                    for radius in protocol['band_menu']:
                        m=band(b,w,q,radius);p=selective(b,r,w,q,m)
                        policies.append(('band',radius,p,m))
                    policies.append(('sector_fixed',-1,sector_fixed(b,r,w,q,sectors),np.ones(len(w),dtype=bool)))
                    for policy,radius,p,m in policies:
                        case=math.fsum(w*y*p);qstar=inverse(b,w,y,case)
                        sy=shares(sectors,w,p);em=shares(size,w,p)
                        expanded=allocation(b,w,qstar)
                        expanded_s=shares(sectors,w,expanded) if qstar>0 else {k:0. for k in sy};expanded_e=shares(size,w,expanded) if qstar>0 else {k:0. for k in em}
                        row={'held_out':held,'source':source,'country':country(source),'family':'logistic','quota':q,'policy':policy,'band_r':radius,'target_n':len(w),'target_membership_sha256':membership(part),
                            'yield':yield_value(y,w,p),'yield_delta_vs_B':yield_value(y,w,p)-by,
                            'query_weight_fraction':math.fsum(w[m])/math.fsum(w),'query_n_fraction':float(m.mean()),'query_n':int(m.sum()),
                            'cases':case,'contacts':math.fsum(w*p),'B_inverse_at_B':bq,'B_inverse_at_policy':qstar,
                            'capacity_raw_pp':100*(qstar-q),'capacity_anchored_pp':100*(qstar-bq),
                            'sector_tv_vs_B_pp':sum(abs(sy[k]-bs[k]) for k in bs)/2,'employment_tv_vs_B_pp':sum(abs(em[k]-be[k]) for k in be)/2,
                            'sector_tv_vs_inverse_B_pp':sum(abs(sy[k]-expanded_s[k]) for k in bs)/2,'employment_tv_vs_inverse_B_pp':sum(abs(em[k]-expanded_e[k]) for k in be)/2}
                        records.append(row)
                    random_inputs.append((held,source,q,b,r,w,y))
            print(json.dumps({'independent_outer_completed':held,'fit_count':2*len(fit_records)}),flush=True)
    df=pd.DataFrame(records);df.to_csv(output/'independent_outer_results.csv',index=False)
    # All models and deterministic results above are already computed. Keep only
    # transient arrays in memory while waiting for production selector completion.
    import time
    while True:
        state=json.loads((PRODUCTION/'RUN_STATUS.json').read_text())
        if state['status']=='PASS':break
        if state['status']=='FAILED':raise RuntimeError('Production run failed; no comparison')
        time.sleep(1)
    selectors=pd.read_csv(PRODUCTION/'selector_decisions.csv')
    for held,source,q,b,r,w,y in random_inputs:
        selector_held='SECONDARY' if held=='all_primary_training' else held
        selected_row=selectors[(selectors.outer_heldout==selector_held)&(selectors.family=='logistic')&np.isclose(selectors.quota,q)]
        if len(selected_row)!=1:raise AssertionError('Selector row not unique')
        sr=float(selected_row.iloc[0].selected_nominal_band)
        sm=band(b,w,q,sr);prob=math.fsum(w[sm])/math.fsum(w)
        for repeat in [0,1,127,255]:
            token=f'20261105|{source}|logistic|{q:.2f}|{repeat}'
            seed=int.from_bytes(sha256(token.encode()).digest()[:16],'little')
            rg=np.random.Generator(np.random.PCG64(seed));rm=rg.random(len(w))<prob
            rp=selective(b,r,w,q,rm)
            random_checks.append({'source':source,'family':'logistic','quota':q,'repeat':repeat,'query_probability':prob,'query_weight_fraction':math.fsum(w[rm])/math.fsum(w),'query_firm_fraction':float(rm.mean()),'query_firms':int(rm.sum()),'cases_per_100_expected_contacts':yield_value(y,w,rp)})
    pd.DataFrame(random_checks).to_csv(output/'independent_random_subset.csv',index=False)
    (output/'INDEPENDENT_FIT_RECORDS.json').write_text(json.dumps(fit_records,indent=2)+'\n')
    qa={'status':'REFITS_COMPLETE_PENDING_COMPARISON','outer_context_n':len(contexts),'independent_logistic_fits':2*len(contexts),'aggregate_rows':len(records),'cohort_primary_n':len(primary),'cohort_all_n':len(frame),'cohort_primary_membership_sha256':membership(primary),'started_utc':start,'finished_utc':datetime.now(timezone.utc).isoformat(),'raw_sha256':expected,'no_row_records_written':True,'scope':'Inherited authenticated reader/cohort/logistic fitting; independent numerical allocation/acquisition/sector/inverse and aggregate metrics.'}
    (output/'REFIT_QA.json').write_text(json.dumps(qa,indent=2)+'\n')
    return qa

def compare(production,independent,output):
    """Compare independently refitted outer values and all saved selector/means."""
    d=pd.read_csv(production/'source_policy_results.csv')
    own=pd.read_csv(independent/'independent_outer_results.csv')
    sel=pd.read_csv(production/'selector_decisions.csv')
    inner=pd.read_csv(production/'inner_validation_results.csv')
    errors=[];counts={};problems=[]
    def close(a,b,label,tol=1e-8):
        if pd.isna(a) and pd.isna(b):return
        if pd.isna(a) or pd.isna(b):problems.append(label+': null mismatch');return
        e=abs(float(a)-float(b));errors.append(e)
        if e>tol:problems.append(label+': '+str(e))
    metrics={'cases_per_100_expected_contacts':'yield','yield_delta_vs_B':'yield_delta_vs_B','query_weight_fraction':'query_weight_fraction','query_firm_fraction':'query_n_fraction','query_firms':'query_n','expected_weighted_cases':'cases','expected_weighted_contacts':'contacts','B_inverse_at_B_cases':'B_inverse_at_B','B_inverse_at_policy_cases':'B_inverse_at_policy','raw_B_capacity_difference_pp':'capacity_raw_pp','anchored_B_capacity_difference_pp':'capacity_anchored_pp','sector_tv_vs_B_pp':'sector_tv_vs_B_pp','employment_tv_vs_B_pp':'employment_tv_vs_B_pp','sector_tv_vs_equivalent_B_pp':'sector_tv_vs_inverse_B_pp','employment_tv_vs_equivalent_B_pp':'employment_tv_vs_inverse_B_pp'}
    for row in d[d.family.eq('logistic')].itertuples():
        if row.policy=='B':pol='band';radius=0.
        elif row.policy=='Full':pol='band';radius=1.
        elif row.policy.startswith('Band_'):pol='band';radius=float(row.policy.split('_')[1])
        elif row.policy=='SectorFixed':pol='sector_fixed';radius=-1.
        elif row.policy=='Selected':
            selected=sel[(sel.outer_heldout==row.outer_heldout)&(sel.family==row.family)&np.isclose(sel.quota,row.quota)]
            pol='band';radius=float(selected.iloc[0].selected_nominal_band)
        else:raise AssertionError('Unrecognised production policy')
        match=own[(own.source==row.source)&np.isclose(own.quota,row.quota)&(own.policy==pol)&np.isclose(own.band_r,radius)]
        if len(match)!=1:raise AssertionError('Independent row not unique')
        ref=match.iloc[0]
        if row.target_membership_sha256!=ref.target_membership_sha256:problems.append('Membership '+row.source)
        for prodcol,owncol in metrics.items():close(getattr(row,prodcol),ref[owncol],str((row.source,row.quota,row.policy,prodcol)))
    counts['outer_logistic_policy_rows']=int(d.family.eq('logistic').sum())
    # Recalculate selector means independently from per-source validation rows.
    for row in sel.itertuples():
        a=inner[(inner.outer_heldout==row.outer_heldout)&(inner.family==row.family)&np.isclose(inner.quota,row.quota)]
        means={}
        for radius in [0.,.1,.25,.5,1.]:
            v=a[np.isclose(a.nominal_band,radius)]
            country_values=[]
            for country,part in v.groupby('country'):
                if country==row.outer_heldout:problems.append('Outer target in selector')
                values=part['yield'].tolist();country_values.append(math.fsum(values)/len(values))
                for vr in part.itertuples():
                    excludes=vr.fit_exclusions.split('|')
                    intended={vr.inner_heldout} if row.outer_heldout=='SECONDARY' else {row.outer_heldout,vr.inner_heldout}
                    if set(excludes)!=intended:problems.append('Wrong inner fit exclusions')
            means[radius]=math.fsum(country_values)/len(country_values)
            close(means[radius],getattr(row,'_0',means[radius]),'unused') if False else None
            close(means[radius],sel.loc[row.Index,f'inner_mean_r_{radius:g}'],'Selector mean')
        picked=next(radius for radius in [0.,.1,.25,.5,1.] if means[radius]>=means[1.]-.25-1e-12)
        close(picked,row.selected_nominal_band,'Selected band',tol=0)
        close(means[1.],row.full_inner_mean_yield,'Inner full mean')
        close(means[picked],row.selected_inner_mean_yield,'Inner selected mean')
    counts['selector_rows']=len(sel)
    counts['inner_rows_exclusion_checked']=len(inner)
    # Every fit's country set is disjoint from excluded/target country set.
    protocols=json.loads((ROOT/'protocol/H7_PROTOCOL.json').read_text());allct=set(['India' if x=='India_Wave2_New' else {'Korea':'Republic of Korea','Vietnam':'Viet Nam'}.get(x,x) for x in protocols['primary_sources']])
    fit_count=0
    for path in sorted((production/'fit_locks').glob('*.json')):
        saved=json.loads(path.read_text())
        for fit in saved['fits']:
            ex=set(fit['excluded_countries']);tr=set(fit['training_countries'])
            if ex&tr or tr!=allct-ex:problems.append('Wrong train-country membership '+path.name)
            masses=fit['training_country_weight_masses'];expected=fit['train_n']/len(tr)
            for country,mass in masses.items():close(mass,expected,'Train equal-country weight',tol=1e-7)
            fit_count+=1
    counts['fit_provenance_rows']=fit_count
    # Independently regenerate four random repeats for each source/quota.
    rnd=pd.read_csv(production/'random_replicates.csv');ro=pd.read_csv(independent/'independent_random_subset.csv')
    for row in ro.itertuples():
        m=rnd[(rnd.source==row.source)&(rnd.family==row.family)&np.isclose(rnd.quota,row.quota)&(rnd.repeat==row.repeat)]
        if len(m)!=1:raise AssertionError('Random replicate not unique')
        for col in ['query_probability','query_weight_fraction','query_firm_fraction','query_firms','cases_per_100_expected_contacts']:
            close(getattr(row,col),m.iloc[0][col],'Independent random '+col)
    counts['independent_random_replicates']=len(ro)
    # Every random mean/SE, as distinct from randomisation refits, is recalculated.
    rc=pd.read_csv(production/'random_comparisons.csv')
    for row in rc.itertuples():
        a=rnd[(rnd.source==row.source)&(rnd.family==row.family)&np.isclose(rnd.quota,row.quota)]
        if len(a)!=256:problems.append('Wrong random repeat count')
        y=a.cases_per_100_expected_contacts.to_numpy(float)
        mean=math.fsum(y)/len(y);se=math.sqrt(math.fsum((y-mean)**2)/(len(y)-1)/len(y))
        close(mean,row.random_yield_mean,'Random mean');close(se,row.random_yield_mc_se,'Random MCSE')
        for col,target in [('query_weight_fraction','random_query_weight_fraction_mean'),('query_firm_fraction','random_query_firm_fraction_mean')]:close(math.fsum(a[col])/len(a),getattr(row,target),'Random query mean')
    counts['random_summary_rows']=len(rc)
    # R01: numerical roundoff around zero must not become a positive-country
    # narrative. Apply the same 1e-10 sign threshold used for other counts.
    random_summary=pd.read_csv(production/'equal_country_random_summaries.csv')
    for row in random_summary.itertuples():
        primary_rc=rc[(rc.route=='country_holdout')&(rc.family==row.family)&np.isclose(rc.quota,row.quota)]
        country_delta=[]
        for country,part in primary_rc.groupby('country'):
            values=part.selected_minus_random_yield.to_numpy(float)
            country_delta.append(math.fsum(values)/len(values))
        expected_positive=sum(value>1e-10 for value in country_delta)
        close(expected_positive,row.selected_beats_random_country_n,'R01 selected beats random country count',tol=0)
    counts['equal_country_random_count_rows']=len(random_summary)
    # Check equal-country aggregation, including averaging both India sources first.
    c=pd.read_csv(production/'country_policy_results.csv');su=pd.read_csv(production/'equal_country_policy_summaries.csv')
    numeric=[col for col in d.select_dtypes(include=np.number) if col not in ['quota','n','query_firms']]
    primary=d[d.route.eq('country_holdout')]
    for row in c.itertuples():
        a=primary[(primary.family==row.family)&(primary.policy==row.policy)&np.isclose(primary.quota,row.quota)&(primary.country==row.country)]
        for col in numeric:close(float(a[col].mean()),getattr(row,col),'Country metric '+col)
    for row in su.itertuples():
        a=c[(c.family==row.family)&(c.policy==row.policy)&np.isclose(c.quota,row.quota)]
        if len(a)!=11:problems.append('Primary country count')
        for col in numeric:
            for suffix,fun in [('mean','mean'),('min','min'),('max','max')]:close(float(getattr(a[col],fun)()),getattr(row,col+'_'+suffix),'Equal-country '+col+'_'+suffix)
    counts['country_policy_rows']=len(c);counts['equal_country_summary_rows']=len(su)
    reporting_revision={}
    historical=production.parent/'historical/results_native'
    if historical.exists():
        oldfiles={p.name:p for p in historical.glob('*.csv')};newfiles={p.name:p for p in production.glob('*.csv')}
        if set(oldfiles)!=set(newfiles):problems.append('R01 CSV file set changed')
        changed=[]
        for name,oldpath in oldfiles.items():
            if oldpath.read_bytes()!=newfiles[name].read_bytes():changed.append(name)
        if changed!=['equal_country_random_summaries.csv']:problems.append('R01 unexpected aggregate CSV changes '+str(changed))
        oldsummary=pd.read_csv(oldfiles['equal_country_random_summaries.csv'])
        newsummary=pd.read_csv(newfiles['equal_country_random_summaries.csv'])
        othercols=[c for c in oldsummary if c!='selected_beats_random_country_n']
        try:pd.testing.assert_frame_equal(oldsummary[othercols],newsummary[othercols],check_exact=True)
        except AssertionError:problems.append('R01 changed non-count scientific values')
        reporting_revision={'csv_files_compared':len(oldfiles),'csv_files_changed':changed,'only_changed_column':'selected_beats_random_country_n','old_logistic_q50_positive_count':int(oldsummary[(oldsummary.family=='logistic')&np.isclose(oldsummary.quota,.5)].selected_beats_random_country_n.iloc[0]),'new_logistic_q50_positive_count':int(newsummary[(newsummary.family=='logistic')&np.isclose(newsummary.quota,.5)].selected_beats_random_country_n.iloc[0])}
    qa={'status':'PASS' if not problems else 'FAIL','checked_utc':datetime.now(timezone.utc).isoformat(),'scalar_comparisons':len(errors),'max_absolute_difference':max(errors) if errors else None,'counts':counts,'problems':problems,'reporting_sign_threshold':1e-10,'post_fit_reporting_revision':reporting_revision,'post_fit_reporting_check':'R01 selected-beats-random country counts independently recomputed; 1e-10 threshold suppresses floating-point zeros','scope':'24 independent outer logistic refits using inherited reader/cohort/model fitting; all main-logistic acquisition/menu/selected/sector/inverse metrics independently calculated; four seeded random repeats per source/quota independently recalculated; all selector means/exclusions and saved random means/SE and country aggregates recalculated. Tree numerical fits not independently rerun.'}
    output.write_text(json.dumps(qa,indent=2)+'\n')
    return qa

def main():
    p=argparse.ArgumentParser();p.add_argument('--synthetic',action='store_true');p.add_argument('--empirical',action='store_true');p.add_argument('--compare',action='store_true');p.add_argument('--microdata',type=Path);p.add_argument('--production',type=Path);p.add_argument('--independent',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.synthetic:result=synthetic();a.output.write_text(json.dumps(result,indent=2)+'\n')
    elif a.empirical:result=outer_refits(a.microdata.resolve(),a.output.resolve(),a.production.resolve())
    elif a.compare:result=compare(a.production.resolve(),a.independent.resolve(),a.output.resolve())
    else:raise SystemExit('Choose synthetic/empirical/compare')
    print(json.dumps(result))
    if result.get('status')=='FAIL':raise SystemExit(1)

if __name__=='__main__':main()
