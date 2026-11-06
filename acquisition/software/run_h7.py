#!/usr/bin/env python3
"""Protocol-locked retrospective acquisition experiment; aggregate outputs only."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import itertools, json, math, platform, sys
from pathlib import Path
import numpy as np
import pandas as pd
import scipy, sklearn
from threadpoolctl import threadpool_limits
from pilot_data import load_raw, load_frozen, digest, employment_groups, encode_routine
from pilot_primitives import score_contacts, group_contact_shares, group_contact_rates
from run_h4_pilot import prepare_cohorts, membership, country, write_json, write_csv, require, array_digest
from run_h5_followup import fit
from acquisition_primitives import allocate, band_mask, selective_allocate, sector_fixed_allocate, capacity_equivalent

ROOT = Path(__file__).resolve().parent.parent
P_SHA = 'cb11771a5bb234c97fe1bc0297972d64272e25ae67555a9e440de4dea09b7ea8'
A_SHA = '9ebd34823e0bfa5bb2fcb71c8d4a6d145279b3a436da0577804d0442dfc163dd'
A02_SHA = 'a929627cd20b85b0323db7da2c33eebe956889ba186d30f5ec1abeea02a652d6'


def tv(a,b):
    return .5 * math.fsum(abs(a[k]-b[k]) for k in a)


def measure(part, scores, allocs, query, q, meta, rows, groups):
    w=part.eval_weight.to_numpy(float);y=part.event.to_numpy(bool)
    labels={'sector':encode_routine(part).sector.to_numpy(str),'employment':employment_groups(part)}
    b=allocs['B'];full=allocs['Full'];W=math.fsum(w)
    bcases=math.fsum(w*b*y)
    bq=capacity_equivalent(scores['B'],w,y,bcases)
    bshares={k:group_contact_shares(v,w,b) for k,v in labels.items()}
    fshares={k:group_contact_shares(v,w,full) for k,v in labels.items()}
    for policy,a in allocs.items():
        info=score_contacts(y,w,a)
        require(abs(info['expected_weighted_contacts']-q*W)<1e-8,'Total quota differs')
        target=info['expected_weighted_cases']
        eq=capacity_equivalent(scores['B'],w,y,target)
        eq_a=allocate(scores['B'],w,eq)
        require(abs(math.fsum(w*eq_a*y)-target)<1e-7,'Case curve inverse did not reconstruct')
        mask=query[policy]
        row={**meta,'policy':policy,'quota':q,'n':len(part),
             'target_membership_sha256':membership(part),**info,
             'yield_delta_vs_B':info['cases_per_100_expected_contacts']-100*bcases/(q*W),
             'yield_delta_vs_Full':info['cases_per_100_expected_contacts']-100*math.fsum(w*full*y)/(q*W),
             'query_weight_fraction':math.fsum(w*mask)/W,
             'query_firm_fraction':float(mask.mean()),'query_firms':int(mask.sum()),
             'B_inverse_at_B_cases':bq,'B_inverse_at_policy_cases':eq,
             'raw_B_capacity_difference_pp':100*(eq-q),
             'anchored_B_capacity_difference_pp':100*(eq-bq),
             'allocation_tv_vs_B_pp':50*math.fsum(w*np.abs(a-b))/(q*W)}
        for dim,lab in labels.items():
            sh=group_contact_shares(lab,w,a);rates=group_contact_rates(lab,w,a)
            eqsh=group_contact_shares(lab,w,eq_a) if eq>0 else {k:0. for k in sh}
            row[dim+'_tv_vs_B_pp']=tv(sh,bshares[dim])
            row[dim+'_tv_vs_Full_pp']=tv(sh,fshares[dim])
            row[dim+'_tv_vs_equivalent_B_pp']=tv(sh,eqsh) if eq>0 else None
            for group in sh:
                maskg=lab==group
                groups.append({**meta,'policy':policy,'quota':q,'dimension':dim,'group':group,
                    'group_n':int(maskg.sum()),'eligible_weighted_group_mass':math.fsum(w[maskg]),
                    'expected_contact_share_percent':sh[group],
                    'within_group_contact_rate_percent':rates[group],
                    'equivalent_B_contact_share_percent':eqsh[group] if eq>0 else None})
        rows.append(row)


def random_benchmark(part,scores,q,mask,meta,out_rows,rep_rows,out_groups):
    w=part.eval_weight.to_numpy(float);y=part.event.to_numpy(bool);W=math.fsum(w)
    b=allocate(scores['B'],w,q);full=allocate(scores['Full'],w,q)
    selected=selective_allocate(scores['B'],scores['Full'],w,q,mask)
    p=math.fsum(w*mask)/W
    labels={'sector':encode_routine(part).sector.to_numpy(str),'employment':employment_groups(part)}
    bsh={k:group_contact_shares(v,w,b) for k,v in labels.items()}
    ssh={k:group_contact_shares(v,w,selected) for k,v in labels.items()}
    allocations=[];ys=[];weighted=[];unweighted=[];tvs={k:[] for k in labels}
    for repeat in range(256):
        token=f"20261105|{meta['source']}|{meta['family']}|{q:.2f}|{repeat}"
        seed=int.from_bytes(sha256(token.encode()).digest()[:16],'little')
        rng=np.random.Generator(np.random.PCG64(seed))
        queried=rng.random(len(part))<p
        a=selective_allocate(scores['B'],scores['Full'],w,q,queried)
        require(abs(math.fsum(w*a)-q*W)<1e-8,'Random quota failed')
        value=100*math.fsum(w*a*y)/(q*W)
        qw=math.fsum(w*queried)/W;qn=float(queried.mean())
        row={**meta,'quota':q,'repeat':repeat,'query_probability':p,
             'query_weight_fraction':qw,'query_firm_fraction':qn,'query_firms':int(queried.sum()),
             'cases_per_100_expected_contacts':value}
        for dim,lab in labels.items():
            dist=tv(group_contact_shares(lab,w,a),bsh[dim]);row[dim+'_tv_vs_B_pp']=dist;tvs[dim].append(dist)
        rep_rows.append(row);allocations.append(a);ys.append(value);weighted.append(qw);unweighted.append(qn)
    mean_a=np.mean(allocations,axis=0)
    se=float(np.std(ys,ddof=1)/math.sqrt(len(ys)))
    out={**meta,'quota':q,'replicates':256,'band_query_weight_fraction':p,
         'band_query_firm_fraction':float(mask.mean()),'band_query_firms':int(mask.sum()),
         'random_query_weight_fraction_mean':float(np.mean(weighted)),
         'random_query_firm_fraction_mean':float(np.mean(unweighted)),
         'random_query_firms_expected':p*len(part),
         'random_query_weight_fraction_mc_se':float(np.std(weighted,ddof=1)/16),
         'random_query_firm_fraction_mc_se':float(np.std(unweighted,ddof=1)/16),
         'random_yield_mean':float(np.mean(ys)),'random_yield_mc_se':se,
         'selected_yield':100*math.fsum(w*selected*y)/(q*W),
         'selected_minus_random_yield':100*math.fsum(w*selected*y)/(q*W)-float(np.mean(ys))}
    for dim,lab in labels.items():
        sh=group_contact_shares(lab,w,mean_a)
        out[dim+'_tv_mean_allocation_vs_B_pp']=tv(sh,bsh[dim])
        out[dim+'_mean_replicate_tv_vs_B_pp']=float(np.mean(tvs[dim]))
        out[dim+'_tv_mean_allocation_vs_selected_pp']=tv(sh,ssh[dim])
        for group in sh:
            out_groups.append({**meta,'quota':q,'policy':'Random_mean_allocation','dimension':dim,'group':group,
                               'expected_contact_share_percent':sh[group]})
    out_rows.append(out)


def summarise(out):
    d=pd.read_csv(out/'source_policy_results.csv')
    numeric=[c for c in d.select_dtypes(include=np.number) if c not in ['quota','n','query_firms']]
    # Countries are averaged only after India sources are averaged.
    c=d[d.route.eq('country_holdout')].groupby(['family','policy','quota','country'],as_index=False)[numeric].mean()
    write_csv(out/'country_policy_results.csv',c.to_dict('records'))
    result=[]
    for key,a in c.groupby(['family','policy','quota'],sort=True):
        row=dict(zip(['family','policy','quota'],key));row['country_n']=len(a)
        for col in numeric:
            row[col+'_mean']=float(a[col].mean());row[col+'_min']=float(a[col].min());row[col+'_max']=float(a[col].max())
        for col in ['yield_delta_vs_B','yield_delta_vs_Full','anchored_B_capacity_difference_pp']:
            row[col+'_positive_country_n']=int((a[col]>1e-10).sum());row[col+'_negative_country_n']=int((a[col]<-1e-10).sum())
        result.append(row)
    write_csv(out/'equal_country_policy_summaries.csv',result)
    r=pd.read_csv(out/'random_comparisons.csv');r=r[r.route.eq('country_holdout')]
    metrics=[x for x in r.select_dtypes(include=np.number) if x not in ['quota','replicates'] and '_mc_se' not in x]
    rc=r.groupby(['family','quota','country'],as_index=False)[metrics].mean()
    write_csv(out/'country_random_comparisons.csv',rc.to_dict('records'))
    rs=[]
    for key,a in rc.groupby(['family','quota'],sort=True):
        row=dict(zip(['family','quota'],key));row['country_n']=len(a)
        for metric in metrics:row[metric+'_mean']=float(a[metric].mean())
        row['selected_beats_random_country_n']=int((a.selected_minus_random_yield>1e-10).sum())
        # Independent source simulations, with 1/2 India and 1/11 country weights.
        subset=r[(r.family==key[0])&(r.quota==key[1])]
        counts=subset.groupby('country').size()
        row['equal_country_random_yield_mc_se']=math.sqrt(math.fsum((x.random_yield_mc_se/(11*counts[x.country]))**2 for x in subset.itertuples()))
        rs.append(row)
    write_csv(out/'equal_country_random_summaries.csv',rs)


def run(raw_path,out):
    require(digest(ROOT/'protocol/H7_PROTOCOL.json')==P_SHA,'H7 protocol changed')
    require(digest(ROOT/'protocol/H7_ADDENDUM_A01.json')==A_SHA,'H7 A01 changed')
    require(digest(ROOT/'protocol/H7_ADDENDUM_A02.json')==A02_SHA,'H7 A02 changed')
    require(not out.exists(),'Choose new output directory')
    p=json.loads((ROOT/'protocol/H7_PROTOCOL.json').read_text());h4=json.loads((ROOT/'protocol/H4_PROTOCOL.json').read_text())
    require(digest(ROOT/'protocol/H4_PROTOCOL.json')=='a62c851289541a00e387c68f8bcbc31c78677c18116c714f46c180af2858f777','H4 protocol changed')
    raw=load_raw(raw_path);frozen=load_frozen(ROOT/'inputs/run_e4_frozen_analysis_v1.0.2.py')
    cohorts,qa=prepare_cohorts(raw,frozen,h4);frame=cohorts['planning'];frame['plan_MOST']=frame.MOST
    primary=frame[frame.country.isin(p['primary_sources'])].copy()
    countries=sorted(primary.reporting_country.unique())
    out.mkdir(parents=True);write_json(out/'COHORT_QA.json',qa['planning'])
    timing={'run_started_utc':datetime.now(timezone.utc).isoformat(),'first_h7_fit_utc':None,'protocol_locked_utc':p['locked_utc']}
    write_json(out/'RUN_STATUS.json',{'status':'RUNNING','protocol_sha256':P_SHA,'addendum_sha256':A_SHA,'numerical_addendum_sha256':A02_SHA})
    code_before={x.name:digest(x) for x in sorted((ROOT/'software').glob('*.py'))}
    cache={};fitcount=0;inner=[];selectors=[];rows=[];groups=[];rr=[];rep=[];rg=[];checks=[]
    try:
        exclusions=[(),*[(ct,) for ct in countries],*itertools.combinations(countries,2)]
        for excluded in exclusions:
            train=primary[~primary.reporting_country.isin(excluded)].copy()
            test=(primary[primary.reporting_country.isin(excluded)] if excluded else frame[frame.country.isin(p['secondary_sources'])]).copy()
            test=test.sort_values(['country','firmid'],kind='stable').reset_index(drop=True)
            require(not set(train.reporting_country)&set(test.reporting_country),'Fit-country overlap')
            if 'India' in set(test.reporting_country):require(set(test[test.reporting_country.eq('India')].country)=={'India','India_Wave2_New'},'India split')
            saved=[];scores={}
            for family in ['logistic','tree']:
                scores[family]={}
                for name,policy in [('B',family+'_B'),('Full',family+'_B_plan_MOST5')]:
                    if timing['first_h7_fit_utc'] is None:
                        timing['first_h7_fit_utc']=datetime.now(timezone.utc).isoformat();write_json(out/'TIMING.json',timing)
                    values,params=fit(train,test,policy);fitcount+=1
                    params.update(excluded_countries=list(excluded),target_membership_sha256=membership(test),score_sha256=array_digest(values))
                    saved.append(params);scores[family][name]=values
            label='__'.join(excluded).replace(' ','_') if excluded else 'all_primary_for_secondary'
            write_json(out/'fit_locks'/(label+'.json'),{'status':'FIT_COMPLETE','protocol_sha256':P_SHA,'fits':saved})
            cache[excluded]={'test':test,'scores':scores}
            print(f'FITS {len(cache)}/{len(exclusions)} models={fitcount}',flush=True)
        # No selector ever sees outer-target rows, values or labels.
        for held in [*countries,'SECONDARY']:
            outer_train=[ct for ct in countries if ct!=held]
            outer=cache[()] if held=='SECONDARY' else cache[(held,)]
            for family in ['logistic','tree']:
                for q in p['quotas']:
                    validation={r:[] for r in p['band_menu']}
                    for valid in outer_train:
                        ex=tuple(sorted([valid] if held=='SECONDARY' else [held,valid]))
                        item=cache[ex];alltest=item['test']
                        val=alltest[alltest.reporting_country.eq(valid)]
                        for source,idx in val.groupby('country',sort=True).groups.items():
                            idx=np.asarray(idx,dtype=int);part=alltest.loc[idx];w=part.eval_weight.to_numpy(float);y=part.event.to_numpy(bool)
                            b=item['scores'][family]['B'][idx];rich=item['scores'][family]['Full'][idx]
                            for r in p['band_menu']:
                                mask=band_mask(b,w,q,r);a=selective_allocate(b,rich,w,q,mask)
                                value=score_contacts(y,w,a)['cases_per_100_expected_contacts']
                                record={'outer_heldout':held,'inner_heldout':valid,'source':source,'country':country(source),'family':family,'quota':q,'nominal_band':r,
                                        'yield':value,'query_weight_fraction':math.fsum(w*mask)/math.fsum(w),'query_firm_fraction':float(mask.mean()),
                                        'fit_exclusions':'|'.join(ex),'target_membership_sha256':membership(part)}
                                inner.append(record);validation[r].append(record)
                    means={r:float(pd.DataFrame(v).groupby('country')['yield'].mean().mean()) for r,v in validation.items()}
                    selected=next(r for r in p['band_menu'] if means[r]>=means[1]-.25-1e-12)
                    selectors.append({'outer_heldout':held,'family':family,'quota':q,'selected_nominal_band':selected,
                                      'full_inner_mean_yield':means[1],'selected_inner_mean_yield':means[selected],
                                      'allowed_absolute_yield_loss':.25,'inner_country_n':len(outer_train),
                                      **{f'inner_mean_r_{r:g}':v for r,v in means.items()}})
                    test=outer['test']
                    for source,idx in test.groupby('country',sort=True).groups.items():
                        idx=np.asarray(idx,dtype=int);part=test.loc[idx];w=part.eval_weight.to_numpy(float)
                        scores={name:outer['scores'][family][name][idx] for name in ['B','Full']}
                        allocs={'B':allocate(scores['B'],w,q),'Full':allocate(scores['Full'],w,q)}
                        queries={'B':np.zeros(len(part),bool),'Full':np.ones(len(part),bool)}
                        for r in [.1,.25,.5]:
                            key=f'Band_{r:g}';queries[key]=band_mask(scores['B'],w,q,r)
                            allocs[key]=selective_allocate(scores['B'],scores['Full'],w,q,queries[key])
                        queries['Selected']=band_mask(scores['B'],w,q,selected)
                        allocs['Selected']=selective_allocate(scores['B'],scores['Full'],w,q,queries['Selected'])
                        queries['SectorFixed']=np.ones(len(part),bool)
                        sectors=encode_routine(part).sector.to_numpy(str)
                        allocs['SectorFixed']=sector_fixed_allocate(scores['B'],scores['Full'],w,q,sectors)
                        mask=queries['Selected'];hidden=scores['Full'].copy();hidden[~mask]=np.nan
                        require(np.array_equal(allocs['Selected'],selective_allocate(scores['B'],hidden,w,q,mask)),'Unqueried rich feature influenced allocation')
                        for r in p['band_menu']:
                            m=band_mask(scores['B'],w,q,r);rev=band_mask(scores['B'][::-1],w[::-1],q,r)[::-1]
                            require(np.array_equal(m,rev),'Band not row invariant')
                            a=selective_allocate(scores['B'],scores['Full'],w,q,m)
                            ar=selective_allocate(scores['B'][::-1],scores['Full'][::-1],w[::-1],q,rev[::-1])[::-1]
                            require(np.array_equal(a,ar),'Selective allocation not row invariant')
                        for sector in sorted(set(sectors)):
                            m=sectors==sector
                            require(abs(math.fsum(w[m]*allocs['B'][m])-math.fsum(w[m]*allocs['SectorFixed'][m]))<1e-8,'Sector contact mass differs')
                        meta={'route':'secondary_targets' if held=='SECONDARY' else 'country_holdout','source':source,'country':country(source),'family':family,'outer_heldout':held}
                        measure(part,scores,allocs,queries,q,meta,rows,groups)
                        random_benchmark(part,scores,q,mask,meta,rr,rep,rg)
                        checks.append({**meta,'quota':q,'selected_band':selected,'quota_tie_hidden_row_sector_checks':'PASS'})
            # Retain aggregate progress, so a subsequent interruption is inspectable.
            write_csv(out/'source_policy_results.csv',rows);write_csv(out/'inner_validation_results.csv',inner)
            write_csv(out/'selector_decisions.csv',selectors);write_csv(out/'random_comparisons.csv',rr)
            print('OUTER COMPLETE '+held,flush=True)
        write_csv(out/'source_group_composition.csv',groups);write_csv(out/'random_replicates.csv',rep);write_csv(out/'random_mean_group_composition.csv',rg)
        write_csv(out/'allocation_invariance_checks.csv',checks)
        summarise(out)
        code_after={x.name:digest(x) for x in sorted((ROOT/'software').glob('*.py'))}
        require(code_before==code_after,'Code changed during execution')
        timing['finished_utc']=datetime.now(timezone.utc).isoformat();write_json(out/'TIMING.json',timing)
        receipt={'status':'PASS','protocol_sha256':P_SHA,'addendum_sha256':A_SHA,'numerical_addendum_sha256':A02_SHA,'fit_count':fitcount,'fit_sets':len(cache),
                 'primary_n':len(primary),'all_n':len(frame),'native_platform':platform.platform(),'python':sys.version,
                 'numpy':np.__version__,'pandas':pd.__version__,'scipy':scipy.__version__,'sklearn':sklearn.__version__,
                 'source_policy_rows':len(rows),'inner_rows':len(inner),'selector_rows':len(selectors),'random_replicate_rows':len(rep),
                 'allocation_check_rows':len(checks),'code_sha256':code_after,'raw_sha256':digest(raw_path),
                 'no_individual_records_predictions_or_identifiers_written':True,**timing}
        receipt['result_sha256']={x.name:digest(x) for x in sorted(out.glob('*.csv'))}
        write_json(out/'RUN_STATUS.json',receipt);return receipt
    except Exception as e:
        write_json(out/'RUN_STATUS.json',{'status':'FAILED','error':repr(e),'fit_count':fitcount,'timing':timing})
        raise


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--microdata',required=True,type=Path);ap.add_argument('--output',required=True,type=Path)
    args=ap.parse_args()
    with threadpool_limits(limits=1):result=run(args.microdata.resolve(),args.output.resolve())
    print(json.dumps(result,indent=2))
