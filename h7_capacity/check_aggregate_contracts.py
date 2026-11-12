"""Check archived H7 country aggregation, capacity units and linear-cost arithmetic.

This checker uses only published aggregate CSVs. It does not import the H7
generator or any fitted-model code. Country rows already average India's two
sources; this check does not claim to recover source rows from those means.
"""
from __future__ import annotations
import argparse
import csv
from fractions import Fraction as F
from hashlib import sha256
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
COUNTRIES={'Bangladesh','Brazil','Croatia','Ethiopia','Georgia','Ghana','India','Kenya','Republic of Korea','Senegal','Viet Nam'}
FAMILIES=('logistic','tree')
QUOTAS=tuple(F(x) for x in ('0.2','0.35','0.5','0.75'))
MENU=('B','Band_0.1','Band_0.25','Band_0.5','Full','Selected')
POLICIES=MENU+('SectorFixed',)
TOL=F('5e-10')


def run(source:Path, report:Path, cost_table:Path):
    provenance=json.loads((ROOT/'INTEGRATION_PROVENANCE.json').read_text())
    inputs={}
    for filename,pin in provenance['input_hashes'].items():
        path=source/'reported_results/H7'/filename
        if sha256(path.read_bytes()).hexdigest()!=pin:
            raise ValueError(f'Pinned aggregate identity differs: {filename}')
        with path.open(newline='',encoding='utf-8') as stream:inputs[filename]=list(csv.DictReader(stream))
    summaries=inputs['equal_country_policy_summaries.csv']; countries=inputs['country_policy_results.csv']
    expected={(f,q,p) for f in FAMILIES for q in QUOTAS for p in POLICIES}
    summary={(r['family'],F(r['quota']),r['policy']):r for r in summaries}
    if len(summary)!=56 or len(summary)!=len(summaries) or set(summary)!=expected:
        raise ValueError('Incomplete or duplicated summary policy grid')
    country={(r['family'],F(r['quota']),r['policy'],r['country']):r for r in countries}
    if len(country)!=616 or len(country)!=len(countries) or set(country)!={(*key,c) for key in expected for c in COUNTRIES}:
        raise ValueError('Incomplete or duplicated country policy grid')
    comparisons=[]
    def close(label,observed,expected_value):
        error=abs(F(observed)-expected_value)
        if error>TOL:raise ValueError(f'{label}: difference {float(error)} exceeds {float(TOL)}')
        comparisons.append({'check':label,'absolute_error':float(error)})
    mean_fields=[name[:-5] for name in summaries[0] if name.endswith('_mean')]
    for key,row in summary.items():
        if int(row['country_n'])!=11:raise ValueError('Country count differs')
        members=[country[*key,c] for c in sorted(COUNTRIES)]
        for field in mean_fields:
            values=[F(member[field]) for member in members]
            for statistic,value in [('mean',sum(values)/11),('min',min(values)),('max',max(values))]:
                close(f'{key} {field}_{statistic}',row[f'{field}_{statistic}'],value)
        for field in ('yield_delta_vs_B','yield_delta_vs_Full','anchored_B_capacity_difference_pp'):
            values=[F(member[field]) for member in members]
            for sign,expected_count in [('positive',sum(x>F('1e-10') for x in values)),('negative',sum(x<-F('1e-10') for x in values))]:
                observed=int(row[f'{field}_{sign}_country_n'])
                if observed!=expected_count:raise ValueError(f'Country sign count differs: {key} {field} {sign}')
    aggregation_count=len(comparisons)
    for key,row in country.items():
        q=key[1]; eq=F(row['B_inverse_at_policy_cases']);own=F(row['B_inverse_at_B_cases'])
        close(f'{key} raw definition',row['raw_B_capacity_difference_pp'],100*(eq-q))
        close(f'{key} anchored definition',row['anchored_B_capacity_difference_pp'],100*(eq-own))
    for key,row in summary.items():
        q=key[1];eq=F(row['B_inverse_at_policy_cases_mean']);own=F(row['B_inverse_at_B_cases_mean'])
        close(f'{key} mean raw definition',row['raw_B_capacity_difference_pp_mean'],100*(eq-q))
        close(f'{key} mean anchored definition',row['anchored_B_capacity_difference_pp_mean'],100*(eq-own))
    costs=[]
    for family in FAMILIES:
        for quota in QUOTAS:
            for policy in MENU:
                row=summary[family,quota,policy]
                raw=F(row['raw_B_capacity_difference_pp_mean']); anchored=F(row['anchored_B_capacity_difference_pp_mean'])
                share=F(row['query_weight_fraction_mean'])
                costs.append({'family':family,'quota':str(float(quota)),'policy':policy,
                  'raw_capacity_pp':str(float(raw)),'anchored_capacity_pp':str(float(anchored)),
                  'weighted_query_fraction':str(float(share)),
                  'illustrative_raw_cost_ratio_percent':str(float(raw/share)) if share else '',
                  'anchored_sensitivity_slope_percent':str(float(anchored/share)) if share else '',
                  'positive_query_share':bool(share>0),
                  'nonnegative_query_cost_feasible':bool(raw>=-F('1e-10')),
                  'scope':'Equal-country mean normalised weighted mass; common hypothetical unit costs; no monetary observations'})
    with cost_table.open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(costs[0]));writer.writeheader();writer.writerows(costs)
    example=next(x for x in costs if x['family']=='logistic' and x['quota']=='0.5' and x['policy']=='Band_0.5')
    close('Band50 raw cost ratio',example['illustrative_raw_cost_ratio_percent'],F('6.743835603666936'))
    if float(example['anchored_sensitivity_slope_percent'])<=float(example['illustrative_raw_cost_ratio_percent']):
        raise ValueError('Expected separate anchored and raw sensitivity quantities')
    # A minimal counterexample: baseline outcomes (1,0,0,1), quota 1/2,
    # policy selects the two cases; q*=1 and B-own inverse=1/4.
    # At query/contact price 3/5, anchored threshold 3/4 incorrectly implies
    # saving although policy cost 11/10 exceeds B equivalent cost 1.
    q=F(1,2);equivalent=F(1);own=F(1,4);price=F(3,5)
    raw_threshold=equivalent-q;anchored_threshold=equivalent-own
    policy_cost=q+price
    if not (price<=anchored_threshold and price>raw_threshold and policy_cost>equivalent):
        raise AssertionError('Synthetic anchored-cost counterexample failed')
    synthetic_cost={'quota':float(q),'baseline_equivalent_quota':float(equivalent),'baseline_own_minimum':float(own),
                    'raw_threshold':float(raw_threshold),'anchored_threshold':float(anchored_threshold),'query_contact_price_ratio':float(price),
                    'policy_cost':float(policy_cost),'baseline_equivalent_cost':float(equivalent),'anchored_rule_would_be_wrong':True}
    result={'status':'PASS','scope':'Archived country aggregates and capacity/cost definitions; no source-row or microdata recomputation',
        'country_rows':len(country),'summary_rows':len(summary),'mean_fields':len(mean_fields),
        'country_mean_min_max_comparisons':aggregation_count,'country_sign_count_checks':56*6,
        'capacity_identity_comparisons':len(comparisons)-aggregation_count-1,
        'total_numeric_comparisons':len(comparisons),'maximum_absolute_difference':max(x['absolute_error'] for x in comparisons),
        'acquisition_policy_cost_rows':len(costs),'cost_feasibility_zero_tolerance_pp':1e-10,'q50_logistic_band50':example,
        'synthetic_counterexample_to_anchored_cost_rule':synthetic_cost,
        'input_hashes':provenance['input_hashes'],'models_fitted':0,'microdata_accessed':False}
    report.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-repository',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--cost-table',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(run(args.source_repository,args.report,args.cost_table),indent=2))

if __name__=='__main__':main()
