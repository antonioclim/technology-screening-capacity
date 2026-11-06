#!/usr/bin/env python3
"""Plot Figure S4 from two pinned aggregate CSVs; no fitting or microdata access.

The prespecified band path is descriptive and is not an optimal frontier.
The original H7 plotting source is preserved under historical/.
This export changes page layout for print legibility only.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import platform
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def digest(path):return sha256(path.read_bytes()).hexdigest()

PINS={'mean_acquisition.csv': '044a3827d93b4bf9943ca22802dee66eca02dee13d5bdd88ef462a74ac3712dc', 'country_sector_fixed.csv': '8ad7608aff990b154b4d695a775252b5a25714b6de7e72987a344a9eeff9f6a4'}

def main(inputs,output):
    inputs=inputs.resolve();output=output.resolve()
    for name,expected in PINS.items():
        if digest(inputs/name)!=expected:raise ValueError('Figure S4 input differs: '+name)
    a=pd.read_csv(inputs/'mean_acquisition.csv')
    b=pd.read_csv(inputs/'country_sector_fixed.csv')
    path_policies=['B','Band_0.1','Band_0.25','Band_0.5','Full']
    families=['logistic','tree'];q=.5
    if len(a)!=12 or not a.country_n.eq(11).all():raise ValueError('Unexpected equal-country scope')
    countries=sorted(b.country.unique())
    if len(countries)!=11 or len(b)!=22 or not b.family.eq('logistic').all():raise ValueError('Unexpected country scope')
    output.mkdir(parents=True,exist_ok=True)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8.5,
                         'axes.spines.top':False,'axes.spines.right':False,
                         'pdf.fonttype':42,'ps.fonttype':42,'svg.fonttype':'none',
                         'axes.titleweight':'normal'})
    fig=plt.figure(figsize=(6.65,8.2))
    left=fig.add_axes([.21,.61,.76,.265])
    right=fig.add_axes([.21,.18,.76,.265])
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
    left.set_title('(a) Actual acquisition burden and mean yield',loc='left',fontsize=9,pad=10)
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
    right.set_title('(b) Holding sector contact masses fixed',loc='left',fontsize=9,pad=10)
    right.grid(axis='x',color='#E4E4E4',linewidth=.6,zorder=0)
    right.legend(loc='lower right',ncol=1,
                 frameon=False,fontsize=7.7,handletextpad=.5,labelspacing=.55)
    fig.suptitle('Retrospective diagnostics at a 50% contact quota',x=.075,ha='left',y=.977,fontsize=11)
    fig.text(.075,.94,'Country holdouts; 11-country means in (a); both India sources averaged within country.',
             fontsize=8.1,color='#333333')
    fig.text(.075,.071,'Lines in (a) connect B, 10%, 25%, 50% and full nominal acquisition.',
             fontsize=7.5,color='#333333')
    fig.text(.075,.048,'Exact score ties expand actual coverage. Stars use training-country nested selection.',
             fontsize=7.5,color='#333333')
    fig.text(.075,.025,'Panel (b) uses the logistic model. Points are descriptive estimates without confidence intervals.',
             fontsize=7.5,color='#333333')
    stem=output/'Figure_S4'
    title='Technology acquisition and fixed sector allocations'
    creation_utc=datetime.now(timezone.utc)
    fig.savefig(stem.with_suffix('.pdf'),metadata={'Title':title,'Author':'Antonio Clim','CreationDate':creation_utc})
    fig.savefig(stem.with_suffix('.svg'),metadata={'Title':title,'Creator':'Matplotlib','Date':creation_utc.isoformat()})
    fig.savefig(stem.with_suffix('.png'),dpi=180)
    plt.close(fig)
    artifacts={p.name:{'sha256':digest(p),'bytes':p.stat().st_size} for p in [stem.with_suffix('.pdf'),stem.with_suffix('.svg'),stem.with_suffix('.png')]}
    qa={'status':'PLOTTED_AWAITING_VISUAL_QA','scope':'AGGREGATE_CSV_TO_FIGURE_ONLY','contact_quota':q,'country_n':11,
        'microdata_accessed':False,'models_fitted':0,'creation_utc':creation_utc.isoformat(),'PDF_timezone':'UTC explicit','SVG_Date':'UTC ISO8601','inputs':PINS,'source_sha256':digest(Path(__file__)),
        'artifacts':artifacts,'python':platform.python_version(),'matplotlib':matplotlib.__version__,
        'layout':'Portrait stacked panels for print readability; exact H7 values and comparisons retained',
        'limits':'No confidence intervals, optimality, causal effects or prospective validation are asserted.'}
    (output/'FIGURE_S4_QA.json').write_text(json.dumps(qa,indent=2)+'\n')
    print(json.dumps(qa,indent=2))

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--inputs',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();main(args.inputs,args.output)
