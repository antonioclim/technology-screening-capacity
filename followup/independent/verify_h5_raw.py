#!/usr/bin/env python3
"""Independent H5 raw-data verifier; no H5 engine functions imported.

Checks descriptive computational results, not mathematical validity or survey inference.
All row data and predictions stay in memory; output is private aggregate evidence.
"""
from __future__ import annotations
import argparse, csv, hashlib, io, json, math, os, platform, tempfile, zipfile
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import sklearn
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from threadpoolctl import threadpool_limits

RAW_SHA='6d77d3ffb9dcef2ca4534e1c438ddd2e0b357eb852e6c5b48aa5fa6c3cbe2f0e'
MEMBER_SHA='f61a2c6e09f4763818ae1d4db8b330e97bffd8bb0824c2d833b79d728152bd17'
PRIMARY=['Bangladesh','Brazil','Croatia','Ethiopia','Georgia','Ghana','India','India_Wave2_New','Kenya','Korea','Senegal','Vietnam']
TARGETS=['BurkinaFaso','Cambodia']
COUNTRY={'India_Wave2_New':'India','Korea':'Republic of Korea','Vietnam':'Viet Nam','BurkinaFaso':'Burkina Faso'}
DOMAINS={'sector':[str(i) for i in [*range(1,12),101,102]]+['UNKNOWN'],
 'multi_establishment':['0','1','UNKNOWN'],'foreign_owner':['DOMESTIC','ANY_FOREIGN','UNKNOWN'],
 'plan_MOST5':[str(i) for i in range(1,6)],'admin_MOST5':[str(i) for i in range(1,6)]}

def atomic(path:Path,b:bytes):
 path.parent.mkdir(parents=True,exist_ok=True)
 fd,name=tempfile.mkstemp(prefix='.'+path.name,dir=path.parent)
 try:
  with os.fdopen(fd,'wb') as f: assert f.write(b)==len(b);f.flush();os.fsync(f.fileno())
  assert Path(name).read_bytes()==b
  os.replace(name,path);assert path.read_bytes()==b
 finally:
  if Path(name).exists():Path(name).unlink()

def write_json(p,o):atomic(p,(json.dumps(o,indent=2,sort_keys=True,allow_nan=False)+'\n').encode())
def write_csv(p,rows):
 s=io.StringIO(newline='');w=csv.DictWriter(s,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows);atomic(p,s.getvalue().encode())
def fingerprint(d):
 s=d.sort_values(['country','firmid'],kind='stable');return hashlib.sha256(('\n'.join(str(c)+'|'+str(int(i)) for c,i in s[['country','firmid']].itertuples(index=False,name=None))+'\n').encode()).hexdigest()
def onehot(d,p):
 a=d[[p+str(i) for i in range(1,6)]].to_numpy(float);valid=np.isin(a,[0,1]).all(axis=1)&(a.sum(axis=1)==1)
 return pd.Series(np.where(valid,np.argmax(a,axis=1)+1,np.nan),index=d.index),pd.Series(valid,index=d.index)
def adoption(d,p):
 a=d[[p+str(i) for i in range(1,6)]].to_numpy(float);valid=np.isin(a,[0,1]).all(axis=1)&(a.sum(axis=1)>=1)
 return pd.Series(np.where(valid,np.max(a*np.arange(1,6),axis=1),np.nan),index=d.index),pd.Series(valid,index=d.index)

def prepare(path):
 b=path.read_bytes();assert hashlib.sha256(b).hexdigest()==RAW_SHA
 with zipfile.ZipFile(io.BytesIO(b)) as z:
  assert z.testzip() is None;b=z.read('fat0_raw_data_qje.csv')
 assert hashlib.sha256(b).hexdigest()==MEMBER_SHA
 d=pd.read_csv(io.BytesIO(b),low_memory=False);assert d.shape==(21055,723) and not d.firmid.duplicated().any()
 p,pv=onehot(d,'ib9b');a,av=onehot(d,'ib8b');pm,pad=adoption(d,'db9a');am,aad=adoption(d,'db8a')
 positive=np.isfinite(d[['e6a','s7','base_wt']].to_numpy(float)).all(axis=1)&d.e6a.gt(0)&d.s7.gt(0)&d.base_wt.gt(0)
 base=d.loc[positive&d.country.isin(PRIMARY+TARGETS)&pv].copy()
 base['plan_MOST5']=p.loc[base.index].astype(int).astype(str)
 base['admin_MOST5']=a.loc[base.index].map(lambda x:str(int(x)) if pd.notna(x) else 'UNKNOWN')
 base=base.sort_values(['country','firmid'],kind='stable').reset_index(drop=False).rename(columns={'index':'raw_index'})
 base['event']=False
 for s,ii in base.groupby('country',sort=True).groups.items():
  g=base.loc[ii];value=np.log(g.e6a.to_numpy(float)/g.s7.to_numpy(float));w=g.base_wt.to_numpy(float)/g.base_wt.mean()
  order=np.argsort(value,kind='mergesort');cum=np.cumsum(w[order]);k=int(np.searchsorted(cum,.2*cum[-1],side='left'))
  threshold=value[order[min(k,len(order)-1)]];base.loc[ii,'event']=value<=threshold
 assert len(base.loc[base.country.isin(PRIMARY)])==14412
 assert fingerprint(base.loc[base.country.isin(PRIMARY)])=='59d49ff980b98de612b32d721ed35dc80a92fb3175be2e1ddfcf8d36168c6f76'
 planning=base.loc[base.raw_index.map(pad)].copy()
 planning['plan_MAX5']=planning.raw_index.map(pm).astype(int).astype(str)
 # Validate actual declared MOST was among adoptions, do not silently drop contradictions.
 for pre,cohort,label in [('db9a',planning,'plan_MOST5')]:
  vals=cohort[[pre+str(i) for i in range(1,6)]].to_numpy();assert np.all(vals[np.arange(len(cohort)),cohort[label].astype(int)-1]==1)
 matched=planning.loc[planning.raw_index.map(av)&planning.raw_index.map(aad)].copy()
 vals=matched[['db8a'+str(i) for i in range(1,6)]].to_numpy();assert np.all(vals[np.arange(len(matched)),matched.admin_MOST5.astype(int)-1]==1)
 matched['admin_MAX5']=matched.raw_index.map(am).astype(int).astype(str)
 out={}
 for name,x in [('planning',planning),('matched_functions',matched)]:
  x=x.sort_values(['country','firmid'],kind='stable').reset_index(drop=True)
  x['reporting_country']=x.country.map(lambda s:COUNTRY.get(s,s));x['eval_weight']=x.base_wt/x.groupby('country').base_wt.transform('mean');out[name]=x
 return out

class Numeric(TransformerMixin,BaseEstimator):
 def fit(self,X,y=None):
  a=np.asarray(X,float);missing=~np.isfinite(a);self.medians=np.array([np.median(a[~missing[:,i],i]) if (~missing[:,i]).any() else 0. for i in range(a.shape[1])]);self.scale=StandardScaler().fit(np.where(missing,self.medians,a));return self
 def transform(self,X):
  a=np.asarray(X,float);missing=~np.isfinite(a);return np.column_stack([self.scale.transform(np.where(missing,self.medians,a)),missing.astype(float)])

def features(d):
 x=pd.DataFrame(index=d.index)
 x['sector']=d.a5a.map(lambda v:str(int(v)) if pd.notna(v) and v in [*range(1,12),101,102] else 'UNKNOWN')
 x['multi_establishment']=d.s4.map(lambda v:str(int(v)) if pd.notna(v) and v in [0,1] else 'UNKNOWN')
 x['foreign_owner']=d.a3b.map(lambda v:'DOMESTIC' if v==0 else ('ANY_FOREIGN' if pd.notna(v) and 0<v<=100 else 'UNKNOWN'))
 x['start_year']=d.a6.where(np.isfinite(d.a6)&d.a6.between(1800,2023))
 x['plan_MOST5']=d.plan_MOST5;x['admin_MOST5']=d.admin_MOST5
 return x

def fit(train,kind,policy):
 cats=['sector','multi_establishment','foreign_owner']+({'B':[],'B_plan_MOST5':['plan_MOST5'],'B_admin_MOST5':['admin_MOST5'],'B_both_MOST5':['plan_MOST5','admin_MOST5']}[policy])
 tf=ColumnTransformer([('categorical',Pipeline([('impute',SimpleImputer(strategy='constant',fill_value='UNKNOWN',keep_empty_features=True)),('onehot',OneHotEncoder(categories=[DOMAINS[c] for c in cats],handle_unknown='ignore',sparse_output=False,dtype=float))]),cats),('numeric',Numeric(),['start_year'])])
 x=features(train);y=train.event.astype(int).to_numpy();w=train.base_wt/train.groupby('country').base_wt.transform('sum')
 source_count=train[['country','reporting_country']].drop_duplicates().groupby('reporting_country').size()
 w=w/train.reporting_country.map(source_count);w=w*(len(train)/math.fsum(w));assert abs(math.fsum(w)-len(train))<1e-8
 masses=w.groupby(train.reporting_country).sum();assert np.max(abs(masses-len(train)/len(masses)))<1e-8
 estimator=LogisticRegression(penalty='l2',C=1,solver='lbfgs',max_iter=2000,tol=1e-8) if kind=='logistic' else DecisionTreeClassifier(max_depth=3,min_samples_leaf=50,criterion='gini',splitter='best',random_state=20261105,ccp_alpha=0)
 pipe=Pipeline([('features',tf),('classifier',estimator)]);pipe.fit(x,y,classifier__sample_weight=w.to_numpy(float))
 if kind=='logistic':assert int(estimator.n_iter_[0])<2000
 return pipe,{'train_n':len(train),'train_weight_sum':math.fsum(w),'countries':sorted(set(train.reporting_country)),'train_membership_sha256':fingerprint(train),'medians':tf.named_transformers_['numeric'].medians.tolist()}

def predict(pipe,d,kind):
 x=pipe.named_steps['features'].transform(features(d));model=pipe.named_steps['classifier']
 if kind=='tree':return model.predict_proba(x)[:,list(model.classes_).index(1)]
 logits=[math.fsum(row*model.coef_[0])+float(model.intercept_[0]) for row in x]
 return np.array([1/(1+math.exp(-v)) if v>=0 else math.exp(v)/(1+math.exp(v)) for v in logits])

def allocate(s,w,q):
 # Independent grouped implementation; score values, not IDs, define all ties.
 p=np.zeros(len(s));remaining=q*math.fsum(w)
 for value in sorted(set(s),reverse=True):
  at=s==value;mass=math.fsum(w[at]);chance=min(1.,max(0.,remaining/mass));p[at]=chance;remaining-=chance*mass
 assert abs(math.fsum(w*p)-q*math.fsum(w))<1e-8
 return p

def groups(d):
 sector=features(d).sector.to_numpy(str);v=d.s7.to_numpy(float)
 size=np.select([v<20,v<100,v<250,v>=250],['LT20','20_99','100_249','GE250'],default='UNKNOWN')
 return {'sector':sector,'employment':size}

def score(d,s,q):
 w=d.eval_weight.to_numpy(float);p=allocate(s,w,q);mass=math.fsum(w*p)
 return {'n':len(d),'expected_weighted_contacts':mass,'expected_weighted_cases':math.fsum(w*p*d.event.to_numpy(bool)),'cases_per_100_expected_contacts':100*math.fsum(w*p*d.event.to_numpy(bool))/mass,'event_prevalence_percent':100*math.fsum(w*d.event.to_numpy(bool))/math.fsum(w)},p

def run(args):
 protocol_bytes=args.protocol.read_bytes();receipt=json.loads(args.receipt.read_text());protocol_hash=hashlib.sha256(protocol_bytes).hexdigest()
 assert protocol_hash in json.dumps(receipt),'Lock receipt does not contain current protocol hash'
 protocol=json.loads(protocol_bytes);assert '20261105' in json.dumps(protocol)
 assert not args.output.exists();args.output.mkdir(parents=True)
 started=datetime.now(timezone.utc).isoformat();cohorts=prepare(args.raw)
 qa={name:{'n':len(d),'primary_n':int(d.country.isin(PRIMARY).sum()),'primary_membership_sha256':fingerprint(d.loc[d.country.isin(PRIMARY)]),'source_counts':{str(k):int(v) for k,v in d.groupby('country').size().items()}} for name,d in cohorts.items()}
 rows=[];grows=[];fits=[];checks=[]
 for cohort,d in cohorts.items():
  primary=d.loc[d.country.isin(PRIMARY)].copy();tasks=[(c,primary.loc[primary.reporting_country.ne(c)],primary.loc[primary.reporting_country.eq(c)]) for c in sorted(set(primary.reporting_country))]
  tasks.append(('all_primary_training',primary,d.loc[d.country.isin(TARGETS)]))
  policies=['B','B_plan_MOST5'] if cohort=='planning' else ['B','B_plan_MOST5','B_admin_MOST5']
  for kind in ['logistic','tree']:
   for heldout,train,test in tasks:
    test=test.sort_values(['country','firmid'],kind='stable').reset_index(drop=True)
    if heldout!='all_primary_training':assert not set(train.reporting_country)&set(test.reporting_country)
    scores={}
    for policy in policies:
     pipe,lock=fit(train,kind,policy);scores[policy]=predict(pipe,test,kind)
     changed=test.copy();changed['event']=~changed.event
     assert np.array_equal(scores[policy],predict(pipe,changed,kind))
     assert np.array_equal(scores[policy],predict(pipe,test.iloc[::-1],kind)[::-1])
     # An extreme unrelated target row may not fit/recompute preprocessing.
     extreme=test.iloc[:1].copy();extreme['a6']=1800.;extreme['e6a']=1e25;extreme['s7']=1e20
     extended=pd.concat([test,extreme],ignore_index=True)
     assert np.array_equal(scores[policy],predict(pipe,extended,kind)[:len(test)])
     fits.append({'cohort':cohort,'learner':kind,'held_out_country':heldout,'policy':policy,**lock})
    for source,indices in test.groupby('country',sort=True).groups.items():
     ii=np.asarray(list(indices));part=test.loc[ii];baseline_metric,baselinep=score(part,scores['B'][ii],.5)
     allocations={};metrics={}
     for policy in policies:
      metric,p=score(part,scores[policy][ii],.5);metric.update(cohort=cohort,learner=kind,held_out_country=heldout,source=source,country=COUNTRY.get(source,source),policy=policy,quota=.5,membership_sha256=fingerprint(part),yield_delta_vs_B=metric['cases_per_100_expected_contacts']-baseline_metric['cases_per_100_expected_contacts'])
      w=part.eval_weight.to_numpy(float);assert np.allclose(p,allocate(scores[policy][ii][::-1],w[::-1],.5)[::-1],rtol=0,atol=1e-14)
      for dimension,labels in groups(part).items():
       shares={k:100*math.fsum((w*p)[labels==k])/math.fsum(w*p) for k in sorted(set(labels))}
       baseline_shares={k:100*math.fsum((w*baselinep)[labels==k])/math.fsum(w*baselinep) for k in sorted(set(labels))}
       metric[dimension+'_composition_tv_vs_B_pp']=sum(abs(shares[k]-baseline_shares[k]) for k in shares)/2
       for k in shares:
        at=labels==k;grows.append({'cohort':cohort,'learner':kind,'source':source,'country':COUNTRY.get(source,source),'policy':policy,'quota':.5,'dimension':dimension,'group':k,'eligible_weighted_group_mass':math.fsum(w[at]),'expected_contact_share_percent':shares[k],'within_group_contact_rate_percent':100*math.fsum((w*p)[at])/math.fsum(w[at])})
      rows.append(metric);allocations[policy]=p;metrics[policy]=metric
     if cohort=='matched_functions':
      pp=allocations['B_plan_MOST5'];pa=allocations['B_admin_MOST5'];w=part.eval_weight.to_numpy(float)
      checks.append({'learner':kind,'source':source,'country':COUNTRY.get(source,source),'yield_admin_minus_planning':metrics['B_admin_MOST5']['cases_per_100_expected_contacts']-metrics['B_plan_MOST5']['cases_per_100_expected_contacts'],'expected_allocation_tv_pp':50*math.fsum(abs(w*pa/math.fsum(w*pa)-w*pp/math.fsum(w*pp)))})
    print(cohort,kind,heldout,'PASS',flush=True)
 write_csv(args.output/'INDEPENDENT_SOURCE_Q50.csv',rows);write_csv(args.output/'INDEPENDENT_GROUP_Q50.csv',grows);write_csv(args.output/'INDEPENDENT_FUNCTION_CONTRASTS_Q50.csv',checks)
 write_json(args.output/'COHORT_QA.json',qa);write_json(args.output/'FIT_INVENTORY.json',fits)
 write_json(args.output/'RAW_REESTIMATION_QA.json',{'status':'PASS','started_utc':started,'completed_utc':datetime.now(timezone.utc).isoformat(),'protocol_sha256':protocol_hash,'independent_implementation':'This program independently implements raw cohort preparation, anchored labels, feature encoding, preprocessing, fitting, tie allocation, yields and composition. No H4/H5 scientific functions imported.','fits':len(fits),'source_policy_rows':len(rows),'group_rows':len(grows),'functions_contrast_rows':len(checks),'target_event_perturbation_pass':True,'target_row_order_pass':True,'extreme_extra_target_row_pass':True,'quota_accounting_pass':True,'limits':'q50 only; not all four quotas. No formal verification, survey uncertainty or prospective validation. Same numerical libraries as canonical engine.','environment':{'python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__,'sklearn':sklearn.__version__}})

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--raw',type=Path,required=True);p.add_argument('--protocol',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
 with threadpool_limits(limits=1):run(args)
