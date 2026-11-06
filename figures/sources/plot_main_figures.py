"""Plot Paper E H5 figures from H4 summaries or three extracted figure CSVs.

No raw data are used. Indian source distances are
averaged within country before the equal-country summary; no lists are pooled.
"""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import platform
import tempfile
import PIL
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp=None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as f:
            tmp=Path(f.name)
            if f.write(data)!=len(data):raise OSError('Short plot output write')
            f.flush(); os.fsync(f.fileno())
        if tmp.read_bytes()!=data:raise OSError('Temporary plot readback differs')
        os.replace(tmp,path)
        if path.read_bytes()!=data:raise OSError('Final plot readback differs')
    finally:
        if tmp is not None and tmp.exists():tmp.unlink()

NAMES=['Bangladesh','Brazil','Croatia','Ethiopia','Georgia','Ghana','India','Kenya','Republic of Korea','Senegal','Viet Nam']
INPUT_NAMES=['Figure_1_primary.csv','Figure_1_secondary.csv','Figure_2_construct.csv']

def extract_h4_inputs(baseline):
    c=pd.read_csv(baseline/'reference/summaries/country_paired_contrasts.csv')
    c=c[(c.cohort=='planning') & (c.quota==.5)]
    d=pd.read_csv(baseline/'reference/summaries/MAX_MOST_source_composition_distance.csv')
    d=d[(d.cohort=='planning') & (d.quota==.5) & (d.dimension=='sector')]
    d=d.groupby(['route','country'],as_index=False).composition_tv_pp.mean()
    names=NAMES
    primary=c[(c.route=='country_holdout') & (c.contrast=='MOST5_increment')].set_index('country').loc[names].reset_index()
    secondary=c[(c.route!='country_holdout') & (c.contrast=='MOST5_increment')].copy()
    construct=c[(c.route=='country_holdout') & (c.contrast=='MAX5_vs_MOST5')].merge(d,on=['route','country'],validate='one_to_one').set_index('country').loc[names].reset_index()
    return primary,secondary,construct

def validate_inputs(primary,secondary,construct):
    for frame,contrast in [(primary,'MOST5_increment'),(secondary,'MOST5_increment'),(construct,'MAX5_vs_MOST5')]:
        required={'country','cohort','route','quota','contrast','paired_yield_difference'}
        if not required.issubset(frame.columns):raise ValueError('Figure CSV lacks required fields')
        if not frame.cohort.eq('planning').all() or not frame.quota.eq(.5).all() or not frame.contrast.eq(contrast).all():
            raise ValueError('Figure CSV cohort, quota or contrast differs')
        if frame.country.duplicated().any() or not np.isfinite(frame.paired_yield_difference).all():
            raise ValueError('Duplicate country or nonfinite figure estimate')
    for frame in [primary,construct]:
        if frame.country.tolist()!=NAMES or not frame.route.eq('country_holdout').all():
            raise ValueError('Primary figure requires the ordered eleven country estimates')
    if len(secondary)!=2 or set(secondary.country)!={'Burkina Faso','Cambodia'} or not secondary.route.eq('secondary_targets').all():
        raise ValueError('Both separately labelled secondary targets are required')
    if 'composition_tv_pp' not in construct or not np.isfinite(construct.composition_tv_pp).all() or not construct.composition_tv_pp.between(0,100).all():
        raise ValueError('Invalid sector contact-share total variation')

def run(baseline, out, inputs=None):
    out.mkdir(parents=True,exist_ok=True)
    if (baseline is None)==(inputs is None):raise ValueError('Choose exactly one source: H4 summaries or figure CSVs')
    input_receipts={}
    if inputs is None:
        tables=extract_h4_inputs(baseline)
        for name,table in zip(INPUT_NAMES,tables):
            data=table.to_csv(index=False,float_format='%.17g').encode()
            atomic(out/'inputs'/name,data)
            input_receipts[name]={'bytes':len(data),'sha256':sha256(data).hexdigest()}
        origin='H4 country/source summaries; no new fitted estimates'
    else:
        tables=[]
        for name in INPUT_NAMES:
            data=(inputs/name).read_bytes()
            # Round-trip parsing retains the exact values written with 17 digits.
            table=pd.read_csv(BytesIO(data),float_precision='round_trip')
            tables.append(table)
            atomic(out/'inputs'/name,data)
            input_receipts[name]={'bytes':len(data),'sha256':sha256(data).hexdigest()}
        origin='Three figure CSV inputs; no H4 archive or raw data accessed; no new fitted estimates'
    primary,secondary,construct=tables
    validate_inputs(primary,secondary,construct)
    names=NAMES
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'axes.titlesize':10,'axes.labelsize':9,'svg.fonttype':'none','pdf.fonttype':42,'axes.spines.top':False,'axes.spines.right':False,'axes.spines.left':False})
    figs=[]
    fig,ax=plt.subplots(figsize=(7.05,5.5))
    allrows=pd.concat([primary,secondary],ignore_index=True)
    labels=allrows.country.tolist(); labels=[x.replace('Republic of Korea','Korea') for x in labels]
    y=np.arange(len(allrows),dtype=float);y[11:]+=.65
    x=allrows.paired_yield_difference.to_numpy()
    ax.axvline(0,color='.5',linewidth=.7)
    for j,(xx,yy) in enumerate(zip(x,y)):
        ax.plot([0,xx],[yy,yy],color='#b4b4b4',linewidth=1,zorder=1)
        ax.scatter(xx,yy,color=('#234e70' if j<11 else '#9b462d'),s=31,marker=('o' if j<11 else 's'),zorder=3)
        ax.annotate(f'{xx:+.2f}',(xx,yy),xytext=(6 if xx>=0 else -6,0),textcoords='offset points',va='center',ha=('left' if xx>=0 else 'right'),fontsize=8)
    ax.axhline(10.8,color='.75',linewidth=.7,linestyle='--')
    ax.set_yticks(y,labels);ax.invert_yaxis();ax.set_xlim(min(x)-2,max(x)+2)
    ax.tick_params(axis='y',length=0);ax.set_xlabel('MOST5 added to firm characteristics\nDifference in cases per 100 expected weighted contacts')
    ax.set_title('Planning information at a 50% quota in each source',loc='left',pad=12)
    fig.subplots_adjust(left=.19,right=.97,top=.91,bottom=.14)
    figs.append(('Figure_1',fig))
    fig,axes=plt.subplots(1,2,figsize=(7.05,4.8),sharey=True,gridspec_kw={'width_ratios':[1.2,1]})
    yy=np.arange(11)
    for ax in axes:
        ax.set_yticks(yy,[n.replace('Republic of Korea','Korea') for n in names]);ax.tick_params(axis='y',length=0)
    z=construct.paired_yield_difference.to_numpy();v=construct.composition_tv_pp.to_numpy()
    axes[0].axvline(0,color='.5',linewidth=.7)
    axes[0].scatter(z,yy,s=30,color='#234e70',zorder=3)
    for xx,j in zip(z,yy):axes[0].plot([0,xx],[j,j],color='.75',linewidth=.8,zorder=1)
    axes[0].set_xlim(min(z)-1,max(z)+1)
    axes[0].set_title('A  Yield difference',loc='left');axes[0].set_xlabel('MAX5 minus MOST5\nCases per 100 weighted contacts')
    axes[1].scatter(v,yy,s=30,color='#806028',zorder=3)
    for xx,j in zip(v,yy):axes[1].plot([0,xx],[j,j],color='.75',linewidth=.8,zorder=1)
    axes[1].set_xlim(0,max(v)*1.15);axes[1].set_title('B  Sector composition distance',loc='left');axes[1].set_xlabel('Total variation in contact shares\nPercentage points')
    axes[0].invert_yaxis();fig.suptitle('Changing the planning construct at the same 50% quota',x=.02,ha='left',fontsize=10)
    fig.subplots_adjust(left=.19,right=.98,top=.87,bottom=.17,wspace=.18)
    figs.append(('Figure_2',fig))
    outputs={}
    export_metadata={}
    for name,fig in figs:
        creation_utc=datetime.now(timezone.utc)
        export_metadata[name]={'creation_utc':creation_utc.isoformat(),'PDF_timezone':'UTC explicit','SVG_Date':'UTC ISO8601'}
        for fmt in ['pdf','svg','png']:
            buf=BytesIO()
            md={'Creator':f'Matplotlib {matplotlib.__version__}'} if fmt!='png' else {'Software':f'Matplotlib {matplotlib.__version__}'}
            if fmt=='pdf':md.update({'Author':'Antonio Clim','Title':name+' Paper E screening comparisons','CreationDate':creation_utc})
            elif fmt=='svg':md['Date']=creation_utc.isoformat()
            fig.savefig(buf,format=fmt,dpi=220,metadata=md)
            b=buf.getvalue();atomic(out/(name+'.'+fmt),b);outputs[name+'.'+fmt]={'bytes':len(b),'sha256':sha256(b).hexdigest()}
        plt.close(fig)
    qa={'created_utc':datetime.now(timezone.utc).isoformat(),'source':origin,'export_metadata':export_metadata,'input_files':input_receipts,'primary_countries':len(primary),'secondary_targets':len(secondary),'primary_increment_mean':float(primary.paired_yield_difference.mean()),'MAX_minus_MOST_mean':float(construct.paired_yield_difference.mean()),'sector_distance_mean_pp':float(construct.composition_tv_pp.mean()),'country_aggregation':'Indian source distances averaged within country before equal-country means; no lists pooled','runtime':{'python':platform.python_version(),'matplotlib':matplotlib.__version__,'numpy':np.__version__,'pandas':pd.__version__,'Pillow':PIL.__version__},'outputs':outputs}
    atomic(out/'FIGURE_BUILD_QA.json',(json.dumps(qa,indent=2)+'\n').encode());print(json.dumps(qa,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    group=p.add_mutually_exclusive_group(required=True)
    group.add_argument('--h4',type=Path,help='H4 capsule root containing reference/summaries')
    group.add_argument('--inputs',type=Path,help='Directory containing the three Figure_*.csv inputs')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.h4.resolve() if a.h4 else None,a.output.resolve(),a.inputs.resolve() if a.inputs else None)
