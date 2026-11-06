"""Plot prespecified H4 country contrasts from aggregate result CSVs only."""
import argparse
from hashlib import sha256
import io, json, os, tempfile
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def verified_write(path,data):
    fd,name=tempfile.mkstemp(prefix='.'+path.name+'.',suffix='.tmp',dir=path.parent)
    tmp=Path(name)
    try:
        with os.fdopen(fd,'wb') as f:
            if f.write(data)!=len(data):raise OSError('Short graphical write')
            f.flush();os.fsync(f.fileno())
        if tmp.read_bytes()!=data:raise OSError('Temporary readback differs')
        os.replace(tmp,path)
        if path.read_bytes()!=data:raise OSError('Final readback differs')
    finally:
        if tmp.exists():tmp.unlink()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    a=p.parse_args()
    if json.loads((a.run/'RUN_STATUS.json').read_text())['status']!='PASS':
        raise ValueError('H4 empirical run is incomplete')
    if a.output.exists():raise ValueError('Choose a new graphical output directory')
    a.output.mkdir(parents=True)
    csv=a.run/'source_policy_quota_results.csv'
    d=pd.read_csv(csv)
    d=d.loc[d.route.eq('country_holdout') & np.isclose(d.quota,.5)]
    country=d.groupby(['cohort','country','policy'],sort=True).mean(numeric_only=True)
    countries=sorted(d.country.unique())
    if len(countries)!=11:raise ValueError('Expected eleven primary countries')
    def series(cohort,policy):
        return np.array([country.loc[(cohort,c,policy),'cases_per_100_expected_contacts'] for c in countries])
    panels=[
      ('planning','B_MOST5','B','A  Planning: predominantly used detail beyond B'),
      ('planning','B_MAX5','B_MOST5','B  Planning: adopted MAX versus used MOST'),
      ('administration','B_MOST5','B','C  Administration replication: detail beyond B'),
    ]
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'svg.fonttype':'none',
                         'svg.hashsalt':'papere-h4-locked-pilot','axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(2,2,figsize=(12.4,9.6))
    fig.subplots_adjust(left=.14,right=.97,bottom=.14,top=.86,wspace=.65,hspace=.38)
    y=np.arange(len(countries))
    labels=[{'Republic of Korea':'Korea','Viet Nam':'Viet Nam'}.get(c,c) for c in countries]
    plotted={}
    for ax,(cohort,policy,base,title) in zip(axes.flat,panels):
        values=series(cohort,policy)-series(cohort,base)
        ax.axvline(0,color='#626970',linewidth=.8)
        ax.scatter(values,y,color='#007c78',s=27,zorder=3)
        ax.axvline(values.mean(),color='#007c78',linestyle='--',linewidth=1)
        ax.set_yticks(y,labels);ax.invert_yaxis();ax.grid(axis='x',color='#e2e6e9',linewidth=.6)
        ax.set_title(title,loc='left',fontsize=10,fontweight='bold',pad=10)
        ax.set_xlabel('Paired yield difference\n(cases per 100 expected weighted contacts)')
        plotted[title]={'country_values':dict(zip(countries,map(float,values))),
                        'equal_country_mean':float(values.mean())}
    ax=axes.flat[3]
    for cohort,offset,colour,label in [('paired_common_productivity',-.13,'#007c78','Relative low sales per worker'),
                                     ('paired_common_finance',.13,'#a24f22','Reported unmet expansion borrowing')]:
        values=series(cohort,'B_MOST5')-series(cohort,'B')
        ax.scatter(values,y+offset,color=colour,s=25,label=label,zorder=3)
        plotted[cohort]={'country_values':dict(zip(countries,map(float,values))),
                         'equal_country_mean':float(values.mean())}
    ax.axvline(0,color='#626970',linewidth=.8);ax.set_yticks(y,labels);ax.invert_yaxis()
    ax.grid(axis='x',color='#e2e6e9',linewidth=.6)
    ax.set_title('D  Same firms, two objectives: used detail beyond B',loc='left',fontsize=10,fontweight='bold',pad=10)
    ax.set_xlabel('Within-objective paired yield difference\n(cases per 100 expected weighted contacts)')
    ax.legend(loc='lower left',bbox_to_anchor=(-.05,-.40),frameon=False,fontsize=8)
    fig.text(.14,.955,'H4 decision-value pilot',fontsize=18,fontweight='bold')
    fig.text(.14,.915,'Separate 50% expected weighted quota in each source; training excludes the evaluated country.',fontsize=10)
    fig.text(.14,.075,'B uses sector, establishment start year, multi-establishment status and foreign ownership. No employment in B.',fontsize=8)
    fig.text(.14,.052,'India averages its two source scores. Dashed lines in A–C are equal-country means. No sampling intervals are shown.',fontsize=8)
    fig.text(.14,.029,'Panel D holds firms fixed. The two event types are different outcomes and do not measure comparable welfare.',fontsize=8)
    for ext in ['png','svg']:
        memory=io.BytesIO()
        metadata=({'Software':'Matplotlib '+matplotlib.__version__,'Title':'H4 decision-value pilot','Author':'Antonio Clim'}
                  if ext=='png' else {'Date':'2026-11-05','Title':'H4 decision-value pilot','Creator':'Matplotlib '+matplotlib.__version__})
        fig.savefig(memory,format=ext,dpi=200,metadata=metadata)
        verified_write(a.output/('H4_DECISION_VALUE_OVERVIEW.'+ext),memory.getvalue())
    plt.close(fig)
    result={'status':'PASS','source_csv_sha256':sha256(csv.read_bytes()).hexdigest(),
            'countries':11,'quota':.5,'sampling_intervals_shown':False,'plot_values':plotted,
            'exports':{p.name:sha256(p.read_bytes()).hexdigest() for p in a.output.iterdir() if p.is_file()}}
    verified_write(a.output/'H4_OVERVIEW_QA.json',(json.dumps(result,indent=2)+'\n').encode())
    print(json.dumps({'status':'PASS','output':str(a.output)}))

if __name__=='__main__':main()
