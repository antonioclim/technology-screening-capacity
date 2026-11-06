#!/usr/bin/env python3
"""Plot candidate H7 diagnostics from completed aggregate results only.

No model is fitted and no firm-level observations are read. The connected
prespecified bands are a diagnostic path, not an estimated efficient frontier.
"""
from __future__ import annotations
import argparse
from hashlib import sha256
import json
from pathlib import Path
import platform
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def main(results, output):
    results=results.resolve();output=output.resolve()
    status=json.loads((results/'RUN_STATUS.json').read_text())
    if status['status']!='PASS':
        raise ValueError('Plotting requires completed PASS results')
    names=['equal_country_policy_summaries.csv','country_policy_results.csv']
    for name in names:
        if digest(results/name)!=status['result_sha256'][name]:
            raise ValueError('Completed result identity differs: '+name)
    summary=pd.read_csv(results/names[0])
    country=pd.read_csv(results/names[1])
    q=.5
    path_policies=['B','Band_0.1','Band_0.25','Band_0.5','Full']
    families=['logistic','tree']
    a=summary.loc[summary.quota.eq(q)&summary.policy.isin(path_policies+['Selected'])].copy()
    if len(a)!=12 or not a.country_n.eq(11).all():
        raise ValueError('Unexpected equal-country plotting scope')
    a=a[['family','policy','country_n','query_weight_fraction_mean','yield_delta_vs_B_mean']]
    a['query_weight_percent']=100*a.query_weight_fraction_mean
    b=country.loc[country.quota.eq(q)&country.family.eq('logistic')&country.policy.isin(['Full','SectorFixed'])].copy()
    countries=sorted(b.country.unique())
    if len(countries)!=11 or len(b)!=22:
        raise ValueError('Unexpected per-country plotting scope')
    b=b[['country','family','policy','yield_delta_vs_B','sector_tv_vs_B_pp']]
    output.mkdir(parents=True,exist_ok=True)
    a.to_csv(output/'acquisition_plot_inputs.csv',index=False)
    b.to_csv(output/'sector_fixed_plot_inputs.csv',index=False)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,
                         'axes.spines.top':False,'axes.spines.right':False,
                         'pdf.fonttype':42,'ps.fonttype':42,'svg.fonttype':'none',
                         'axes.titleweight':'normal'})
    fig,(left,right)=plt.subplots(1,2,figsize=(12,5.6),gridspec_kw={'width_ratios':[1,1.18]})
    fig.subplots_adjust(left=.075,right=.985,top=.84,bottom=.25,wspace=.49)
    colours={'logistic':'#1764A0','tree':'#C06620'}
    markers={'logistic':'o','tree':'s'}
    for family in families:
        part=a.loc[a.family.eq(family)].set_index('policy')
        ordered=part.loc[path_policies]
        left.plot(ordered.query_weight_percent,ordered.yield_delta_vs_B_mean,
                  color=colours[family],marker=markers[family],markersize=5,
                  linewidth=1.35,label='Logistic' if family=='logistic' else 'Fixed depth-3 tree')
        selected=part.loc['Selected']
        left.scatter(selected.query_weight_percent,selected.yield_delta_vs_B_mean,
                     color=colours[family],marker='*',s=155,edgecolor='#202020',
                     linewidth=.65,zorder=5)
    left.plot([],[],linestyle='none',marker='*',markersize=11,color='#777777',
              markeredgecolor='#202020',markeredgewidth=.65,label='Nested-selected rule')
    left.axhline(0,color='#777777',linewidth=.65,zorder=0)
    left.set_xlim(-3,104);left.set_ylim(-.10,2.27)
    left.set_xticks([0,25,50,75,100])
    left.set_xlabel('Firms queried (% of eligible survey-weighted mass)',labelpad=8)
    left.set_ylabel('Yield change vs B\n(cases per 100 expected weighted contacts)',labelpad=8)
    left.set_title('(a) Actual acquisition burden and mean yield',loc='left',fontsize=10,pad=13)
    left.grid(axis='y',color='#E4E4E4',linewidth=.6,zorder=0)
    left.legend(loc='upper left',frameon=False,fontsize=8.5,handlelength=2.1,borderpad=.2)
    # The order follows the locked diagnostic band menu. Full acquisition is
    # the endpoint; the train-selected point is not joined into that path.
    for i,ct in enumerate(countries):
        rows=b.loc[b.country.eq(ct)].set_index('policy')
        full=float(rows.loc['Full','yield_delta_vs_B'])
        fixed=float(rows.loc['SectorFixed','yield_delta_vs_B'])
        right.plot([full,fixed],[i,i],color='#B7B7B7',linewidth=1.2,zorder=1)
        right.scatter(full,i,color=colours['logistic'],marker='o',s=28,zorder=3,
                      label='Full technology ranking' if i==0 else None)
        right.scatter(fixed,i,color='#8B3F7D',marker='D',s=25,zorder=3,
                      label='Sector-fixed reranking' if i==0 else None)
    labels=[{'Republic of Korea':'Republic of Korea','Viet Nam':'Viet Nam'}.get(c,c) for c in countries]
    right.set_yticks(np.arange(len(countries)),labels)
    right.invert_yaxis()
    right.axvline(0,color='#777777',linewidth=.7,zorder=0)
    right.set_xlabel('Yield change vs B\n(cases per 100 expected weighted contacts)',labelpad=8)
    right.set_title('(b) Holding sector contact masses fixed',loc='left',fontsize=10,pad=13)
    right.grid(axis='x',color='#E4E4E4',linewidth=.6,zorder=0)
    right.legend(loc='upper center',bbox_to_anchor=(.48,-.22),ncol=2,
                 frameon=False,fontsize=8.5,handletextpad=.5,labelspacing=.55)
    fig.suptitle('Retrospective diagnostics at a 50% contact quota',x=.075,ha='left',y=.965,fontsize=13)
    fig.text(.075,.905,'Country holdouts; 11-country means in (a); both India sources averaged within country.',
             fontsize=9,color='#333333')
    fig.text(.075,.055,'Lines in (a) connect B, 10%, 25%, 50% and full nominal acquisition; exact score ties expand actual query coverage.',
             fontsize=8.25,color='#333333')
    fig.text(.075,.025,'Stars use training-country nested selection. Panel (b) uses the logistic model. Points show descriptive estimates without confidence intervals.',
             fontsize=8.25,color='#333333')
    stem=output/'H7_Acquisition_Diagnostics'
    fig.savefig(stem.with_suffix('.pdf'),metadata={'Title':'H7 acquisition diagnostics','Author':'Antonio Clim'})
    fig.savefig(stem.with_suffix('.svg'),metadata={'Title':'H7 acquisition diagnostics','Creator':'Matplotlib'})
    fig.savefig(stem.with_suffix('.png'),dpi=180)
    plt.close(fig)
    generated=[output/'acquisition_plot_inputs.csv',output/'sector_fixed_plot_inputs.csv',
               stem.with_suffix('.pdf'),stem.with_suffix('.svg'),stem.with_suffix('.png')]
    qa={'status':'PLOTTED_AWAITING_VISUAL_QA','candidate_not_canonical_article_figure':True,
        'contact_quota':q,'country_n':11,'microdata_read':False,'model_fits':0,
        'source_hashes':{name:digest(results/name) for name in ['RUN_STATUS.json',*names]},
        'generated_sha256':{p.name:digest(p) for p in generated},
        'plot_code_sha256':digest(Path(__file__).resolve()),
        'python':platform.python_version(),'matplotlib':matplotlib.__version__,
        'notes':['Actual query burden reflects full exact-score blocks.',
                 'Acquisition bands are prespecified diagnostics, not an optimal frontier.',
                 'The selected rule is fitted within training-country nested validation.',
                 'India is averaged across its two sources before country comparisons.',
                 'No confidence intervals or generative-image model were used.']}
    (output/'H7_FIGURE_QA.json').write_text(json.dumps(qa,indent=2)+'\n')
    print(json.dumps({'status':qa['status'],'output':str(output),'files':[p.name for p in generated]}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results',type=Path,default=Path(__file__).resolve().parents[1]/'results_native')
    parser.add_argument('--output',type=Path,default=Path(__file__).resolve().parent)
    args=parser.parse_args();main(args.results,args.output)
