#!/usr/bin/env python3
"""Read-only numeric document audit against existing canonical scientific outputs."""
from pathlib import Path
import hashlib,io,csv,json,re
from datetime import datetime,timezone
import pandas as pd
from docx import Document
R=Path(__file__).resolve().parents[2]
O=Path(__file__).resolve().parent
MAIN=R/'manuscript/Manuscript_Identified.docx';SUPP=R/'supplement/Supplement.docx'
docs={'main':Document(MAIN),'supplement':Document(SUPP)}
files={};register=[];prose=[];failures=[]
def load(rel):
 p=R/rel
 if rel not in files:files[rel]=pd.read_csv(p)
 return files[rel]
def subset(rel,**filters):
 d=load(rel)
 for k,v in filters.items():d=d.loc[d[k].eq(v)]
 return d
def value(rel,field,**filters):
 d=subset(rel,**filters);assert len(d)==1,(rel,filters,len(d));return float(d.iloc[0][field])
def fmt(v,digits=2,sign=False,integer=False):
 if integer:return f'{int(v):,}'
 return format(v,('+' if sign else '')+'.'+str(digits)+'f')
def cell(doc,ti,ri,ci,v,source,filters,field,digits=2,sign=False,integer=False,custom=None):
 actual=docs[doc].tables[ti-1].cell(ri-1,ci-1).text
 expected=custom if custom is not None else fmt(v,digits,sign,integer)
 ok=actual==expected
 row={'document':str(MAIN if doc=='main' else SUPP),'table':ti,'row':ri,'column':ci,'actual':actual,'expected':expected,'source':source,'selector':filters,'field_or_calculation':field,'unrounded_expected':float(v),'pass':ok};register.append(row)
 if not ok:failures.append(row)
def pnum(doc,pi,v,source,selector,field,digits=2,sign=False,integer=False,literal=None):
 text=docs[doc].paragraphs[pi-1].text;expected=literal if literal is not None else fmt(v,digits,sign,integer)
 normal=text.replace('−','-');ok=expected.replace('−','-') in normal
 row={'document':str(MAIN if doc=='main' else SUPP),'paragraph':pi,'expected_printed_number':expected,'source':source,'selector':selector,'field_or_calculation':field,'unrounded_expected':float(v),'pass':ok,'actual_paragraph':text};prose.append(row)
 if not ok:failures.append(row)
H4S='baseline_h4/reference/results/source_policy_quota_results.csv';H4C='baseline_h4/reference/summaries/country_policy_quota_results.csv';H4A='baseline_h4/reference/summaries/equal_country_policy_summaries.csv';H4D='baseline_h4/reference/summaries/equal_country_contrast_summaries.csv';H4T='baseline_h4/reference/summaries/MAX_MOST_source_composition_distance.csv';H4G='baseline_h4/reference/summaries/MAX_MOST_group_differences.csv';H4P='baseline_h4/reference/summaries/paired_objectives_equal_country_summaries.csv'
H5A='empirical/results/equal_country_policy_summaries.csv';H5F='empirical/results/equal_country_function_summaries.csv';H5S='empirical/results/source_policy_quota_results.csv'
COUNTRIES=['Bangladesh','Brazil','Croatia','Ethiopia','Georgia','Ghana','India','Kenya','Republic of Korea','Senegal','Viet Nam']
SRC=['Bangladesh','Brazil','Croatia','Ethiopia','Georgia','Ghana','India','India_Wave2_New','Kenya','Korea','Senegal','Vietnam','BurkinaFaso','Cambodia']
Y='cases_per_100_expected_contacts'
for ri,c in enumerate(COUNTRIES,2):
 for ci,policy in [(2,'B'),(3,'B_MOST5')]:
  f={'cohort':'planning','route':'country_holdout','country':c,'policy':policy,'quota':.5};cell('main',1,ri,ci,value(H4C,Y,**f),H4C,f,Y)
 f={'cohort':'planning','route':'country_holdout','country':c,'policy':'B_MOST5','quota':.5};cell('main',1,ri,4,value(H4C,'yield_delta_vs_B',**f),H4C,f,'yield_delta_vs_B',sign=True)
for ci,pol in [(2,'B'),(3,'B_MOST5')]:
 f={'cohort':'planning','policy':pol,'quota':.5};cell('main',1,13,ci,value(H4A,Y+'_country_mean',**f),H4A,f,Y+'_country_mean')
f={'cohort':'planning','quota':.5,'contrast':'MOST5_increment'};cell('main',1,13,4,value(H4D,'equal_country_mean',**f),H4D,f,'equal_country_mean',sign=True)
for ri,s in [(14,'BurkinaFaso'),(15,'Cambodia')]:
 for ci,pol,field in [(2,'B',Y),(3,'B_MOST5',Y),(4,'B_MOST5','yield_delta_vs_B')]:
  f={'cohort':'planning','source':s,'policy':pol,'quota':.5};cell('main',1,ri,ci,value(H4S,field,**f),H4S,f,field,sign=ci==4)
contrasts=['MOST5_increment','MOST5_increment_with_size','MAX5_vs_MOST5','MOST_detail_vs_binary','MAX_addition_to_MOST']
for ri,co in enumerate(contrasts,2):
 f={'cohort':'planning','quota':.5,'contrast':co}
 for ci,field in [(2,'equal_country_mean'),(3,'positive_countries'),(4,'negative_countries')]:cell('main',2,ri,ci,value(H4D,field,**f),H4D,f,field,sign=ci==2,integer=ci>2)
for ri,family in [(2,'logistic'),(3,'tree')]:
 for ci,spec in [(2,'plan'),(3,'admin')]:
  f={'cohort':'common_functions','policy':family+'_B_'+spec+'_MOST5','quota':.5};cell('main',3,ri,ci,value(H5A,'yield_delta_vs_B_mean',**f),H5A,f,'yield_delta_vs_B_mean',sign=True)
 f={'cohort':'common_functions','family':family,'quota':.5};cell('main',3,ri,4,value(H5F,'admin_minus_plan_yield_mean',**f),H5F,f,'admin_minus_plan_yield_mean',sign=True)
# New SI tables S8-S12, physical table numbers8-12.
qa4=json.loads((R/'baseline_h4/reference/results/COHORT_QA.json').read_text())['cohorts'];qa5=json.loads((R/'empirical/results/COHORT_QA.json').read_text())['H5_cohorts']
for ri,s in enumerate(SRC,2):
 for ci,co in [(2,'planning'),(3,'administration'),(4,'finance_planning'),(5,'paired_common_productivity'),(6,'common_functions')]:
  q=qa5[co] if ci==6 else qa4[co];cell('supplement',8,ri,ci,q['source_counts'][s],'empirical/results/COHORT_QA.json' if ci==6 else 'baseline_h4/reference/results/COHORT_QA.json',{'cohort':co,'source':s},'source_counts',integer=True)
for ci,co in [(2,'planning'),(3,'administration'),(4,'finance_planning'),(5,'paired_common_productivity'),(6,'common_functions')]:
 q=qa5[co] if ci==6 else qa4[co];v=q['primary_n'] if ci==6 else q['matched_primary_n'];cell('supplement',8,16,ci,v,'empirical/results/COHORT_QA.json' if ci==6 else 'baseline_h4/reference/results/COHORT_QA.json',{'cohort':co},'primary_n',integer=True)
for ri,s in enumerate(SRC[:12],2):
 for ci,pol,field in [(2,'B',Y),(3,'B_MOST5',Y),(4,'B_MOST5','yield_delta_vs_B')]:
  f={'cohort':'planning','source':s,'policy':pol,'quota':.5};cell('supplement',9,ri,ci,value(H4S,field,**f),H4S,f,field,digits=3)
 f={'cohort':'planning','source':s,'quota':.5};v=value(H4S,Y,policy='B_MAX5',**f)-value(H4S,Y,policy='B_MOST5',**f);cell('supplement',9,ri,5,v,H4S,f,'B_MAX5 yield minus B_MOST5 yield',digits=3)
 f={'cohort':'planning','source':s,'quota':.5,'dimension':'sector'};cell('supplement',9,ri,6,value(H4T,'composition_tv_pp',**f),H4T,f,'composition_tv_pp',digits=3)
for ri,co in enumerate(contrasts+['MOST_learned_vs_fixed'],2):
 for ci,q in enumerate([.2,.35,.5,.75],2):
  f={'cohort':'planning','contrast':co,'quota':q};cell('supplement',10,ri,ci,value(H4D,'equal_country_mean',**f),H4D,f,'equal_country_mean',digits=3)
for ri,co in enumerate(['planning','administration','finance_planning','finance_planning_excluding99','paired_common_productivity','paired_common_finance'],2):
 cell('supplement',11,ri,2,qa4[co]['matched_primary_n'],'baseline_h4/reference/results/COHORT_QA.json',{'cohort':co},'matched_primary_n',integer=True)
 for ci,pol,field in [(3,'B',Y+'_country_mean'),(4,'B_MOST5',Y+'_country_mean'),(5,'B_MOST5','yield_delta_vs_B_country_mean')]:
  f={'cohort':co,'policy':pol,'quota':.5};cell('supplement',11,ri,ci,value(H4A,field,**f),H4A,f,field,digits=3)
 f={'cohort':co,'contrast':'MOST_detail_vs_binary','quota':.5};cell('supplement',11,ri,6,value(H4D,'equal_country_mean',**f),H4D,f,'equal_country_mean',digits=3)
for ri,(fam,q) in enumerate([(fam,q) for fam in ['logistic','tree'] for q in [.2,.35,.5,.75]],2):
 cell('supplement',12,ri,2,100*q,'empirical/protocol/H5_PROTOCOL.json',{'family':fam,'quota':q},'quota',custom=str(int(q*100))+'%')
 f={'cohort':'common_functions','family':fam,'quota':q}
 for ci,field in [(3,'plan_minus_B_yield_mean'),(4,'admin_minus_B_yield_mean'),(5,'admin_minus_plan_yield_mean'),(6,'function_expected_allocation_tv_pp_mean')]:cell('supplement',12,ri,ci,value(H5F,field,**f),H5F,f,field,digits=3)
# Named new quantitative claims in the main prose.
def mean(co='planning',pol='B_MOST5',field='yield_delta_vs_B_country_mean',q=.5):return value(H4A,field,cohort=co,policy=pol,quota=q)
def con(co='MOST5_increment',q=.5,field='equal_country_mean',cohort='planning'):return value(H4D,field,cohort=cohort,contrast=co,quota=q)
for pi in [6,12,42]:
 for v,field in [(mean(pol='B',field=Y+'_country_mean'),'B mean yield'),(mean(field=Y+'_country_mean'),'B_MOST5 mean yield')]:
  if pi!=12:pnum('main',pi,v,H4A,{'cohort':'planning','quota':.5},field)
 if pi!=6:pnum('main',pi,con(),H4D,{'cohort':'planning','contrast':'MOST5_increment','quota':.5},'equal_country_mean')
for pi in [6,12,63]:
 f={'cohort':'planning','source':'BurkinaFaso','policy':'B_MOST5','quota':.5};pnum('main',pi,abs(value(H4S,'yield_delta_vs_B',**f)),H4S,f,'absolute reduction vs B')
for pi in [6,13,52]:
 x=subset(H4T,cohort='planning',quota=.5,dimension='sector',route='country_holdout').groupby('country').composition_tv_pp.mean().mean();pnum('main',pi,x,H4T,{'cohort':'planning','quota':.5,'dimension':'sector'},'equal-source within country then equal-country mean')
for pi in [6,20,60]:pnum('main',pi,qa4['planning']['matched_primary_n'],'baseline_h4/reference/results/COHORT_QA.json',{'cohort':'planning'},'matched_primary_n',integer=True)
for pi in [21,47]:
 if pi==21:pnum('main',pi,qa4['administration']['matched_primary_n'],'baseline_h4/reference/results/COHORT_QA.json',{'cohort':'administration'},'matched_primary_n',integer=True)
 else:pnum('main',pi,con(cohort='administration'),H4D,{'cohort':'administration','quota':.5},'MOST5_increment')
for pi in [27]:
 for co in ['finance_planning','finance_planning_excluding99','paired_common_productivity']:pnum('main',pi,qa4[co]['matched_primary_n'],'baseline_h4/reference/results/COHORT_QA.json',{'cohort':co},'matched_primary_n',integer=True)
for pi in [57,59]:pnum('main',pi,qa5['common_functions']['primary_n'],'empirical/results/COHORT_QA.json',{'cohort':'common_functions'},'primary_n',integer=True)
# Additional means, country-specific effects and composition examples.
pc=subset(H4C,cohort='planning',policy='B_MOST5',quota=.5,route='country_holdout')
for c in ['Brazil','Bangladesh','Georgia','Viet Nam','India']:
 v=float(pc.loc[pc.country==c].yield_delta_vs_B.iloc[0]);pnum('main',42,abs(v),H4C,{'country':c,'cohort':'planning','policy':'B_MOST5','quota':.5},'absolute yield_delta_vs_B')
for s in ['India','India_Wave2_New']:
 f={'cohort':'planning','source':s,'policy':'B_MOST5','quota':.5};pnum('main',42,value(H4S,'yield_delta_vs_B',**f),H4S,f,'yield_delta_vs_B')
influence=float(pc.loc[~pc.country.isin(['Bangladesh','Brazil'])].yield_delta_vs_B.mean());pnum('main',46,influence,H4C,{'cohort':'planning','policy':'B_MOST5','quota':.5,'exclude_countries':['Bangladesh','Brazil']},'post-hoc mean of other nine countries')
for q in [.2,.35,.75]:pnum('main',46,con(q=q),H4D,{'contrast':'MOST5_increment','quota':q,'cohort':'planning'},'equal_country_mean')
pnum('main',47,mean(pol='B_SIZE',field=Y+'_country_mean'),H4A,{'cohort':'planning','policy':'B_SIZE','quota':.5},'mean yield');pnum('main',47,con('MOST5_increment_with_size'),H4D,{'contrast':'MOST5_increment_with_size','quota':.5},'equal_country_mean')
pnum('main',49,abs(con('MAX5_vs_MOST5')),H4D,{'contrast':'MAX5_vs_MOST5','quota':.5},'absolute mean loss');pnum('main',49,con('MAX5_vs_MOST5',q=.75),H4D,{'contrast':'MAX5_vs_MOST5','quota':.75},'equal_country_mean')
v=value(H4S,Y,cohort='planning',source='Brazil',policy='B_MAX5',quota=.5)-value(H4S,Y,cohort='planning',source='Brazil',policy='B_MOST5',quota=.5);pnum('main',49,abs(v),H4S,{'cohort':'planning','source':'Brazil','quota':.5},'absolute MAX minus MOST yield')
x=subset(H4T,cohort='planning',quota=.5,dimension='employment',route='country_holdout').groupby('country').composition_tv_pp.mean().mean();pnum('main',52,x,H4T,{'cohort':'planning','quota':.5,'dimension':'employment'},'equal-country mean composition TV')
for group in ['LT20','20_99']:
 for field in ['MOST_group_contact_rate_percent','MAX_group_contact_rate_percent']:
  f={'cohort':'planning','source':'Brazil','quota':.5,'dimension':'employment','group':group};pnum('main',52,value(H4G,field,**f),H4G,f,field)
for field in ['sector_composition_tv_vs_B_pp_country_mean','employment_composition_tv_vs_B_pp_country_mean']:pnum('main',52,mean(field=field),H4A,{'cohort':'planning','policy':'B_MOST5','quota':.5},field)
pnum('main',54,con('MOST_detail_vs_binary'),H4D,{'contrast':'MOST_detail_vs_binary','quota':.5},'equal_country_mean');pnum('main',54,abs(con('MAX_addition_to_MOST')),H4D,{'contrast':'MAX_addition_to_MOST','quota':.5},'absolute mean loss')
v=value(H4S,Y,cohort='planning',source='Brazil',policy='B_MOST5',quota=.5)-value(H4S,Y,cohort='planning',source='Brazil',policy='B_MOST_binary',quota=.5);pnum('main',54,v,H4S,{'cohort':'planning','source':'Brazil','quota':.5},'MOST5 minus binary yield')
for policy in ['logistic_B','logistic_B_plan_MOST5','logistic_B_admin_MOST5','logistic_B_both_MOST5']:
 f={'cohort':'common_functions','policy':policy,'quota':.5};pnum('main',57,value(H5A,Y+'_mean',**f),H5A,f,Y+'_mean')
for pi,fam in [(57,'logistic'),(60,'tree')]:
 f={'cohort':'common_functions','family':fam,'quota':.5}
 for field in ['admin_minus_plan_yield_mean','function_expected_allocation_tv_pp_mean']:pnum('main',pi,value(H5F,field,**f),H5F,f,field)
for spec in ['plan','admin']:
 f={'cohort':'common_functions','policy':'tree_B_'+spec+'_MOST5','quota':.5};pnum('main',60,value(H5A,'yield_delta_vs_B_mean',**f),H5A,f,'yield_delta_vs_B_mean')
f={'cohort':'common_functions','family':'logistic','quota':.35};pnum('main',57,value(H5F,'admin_minus_plan_yield_mean',**f),H5F,f,'admin_minus_plan_yield_mean')
f={'cohort':'planning_H4','policy':'tree_B_plan_MOST5','quota':.5};pnum('main',60,value(H5A,'yield_delta_vs_B_mean',**f),H5A,f,'yield_delta_vs_B_mean')
for co in ['planning_H4','common_functions']:
 for source in ['BurkinaFaso','Cambodia']:
  for family in ['logistic','tree']:
   f={'cohort':co,'source':source,'policy':family+'_B_plan_MOST5','quota':.5};v=value(H5S,'yield_delta_vs_B',**f);pnum('main',61,v,H5S,f,'yield_delta_vs_B',sign=True)
for pol in ['lottery','B','B_MOST5','fixed_MOST5']:
 f={'cohort':'planning','source':'BurkinaFaso','policy':pol,'quota':.5};pnum('main',63,value(H4S,Y,**f),H4S,f,Y)
for co in ['finance_planning','finance_planning_excluding99','paired_common_productivity','paired_common_finance']:pnum('main',64,con(cohort=co),H4D,{'cohort':co,'quota':.5,'contrast':'MOST5_increment'},'equal_country_mean')
for co in ['paired_common_productivity','paired_common_finance']:pnum('main',64,con('MOST_detail_vs_binary',cohort=co),H4D,{'cohort':co,'quota':.5,'contrast':'MOST_detail_vs_binary'},'equal_country_mean')
for pol in ['B','B_MOST5']:
 f={'policy':pol,'quota':.5};pnum('main',65,value(H4P,'expected_allocation_tv_pp_country_mean',**f),H4P,f,'expected_allocation_tv_pp_country_mean')
f={'cohort':'paired_common_finance','source':'Cambodia','policy':'B_MOST5','quota':.5};pnum('main',65,value(H4S,'yield_delta_vs_B',**f),H4S,f,'yield_delta_vs_B')
# Verify seven retained historical editable tables are byte-identical XML.
old=Document(R/'h3_kits/PAPERE_IEP_H3_01_SUBMISSION_20261105/01_UPLOAD/Supplement.docx')
oldmain=Document(R/'h3_kits/PAPERE_IEP_H3_01_SUBMISSION_20261105/01_UPLOAD/Manuscript_Identified.docx')
oldtables=list(old.tables)+list(oldmain.tables)
historical=[]
for i in range(7):
 xml=docs['supplement'].tables[i]._tbl.xml;match=[j+1 for j,t in enumerate(oldtables) if xml==t._tbl.xml];historical.append({'new_table':i+1,'matches_historical_combined_table_indices':match,'pass':bool(match)})
 if not match:failures.append({'table':i+1,'problem':'historical table XML differs'})
# Snapshot whole documents and numeric paragraph inventories for precise locators.
inputs=[MAIN,SUPP,R/'editorial/EDITORIAL_TEXT.json']+[R/p for p in files]
snap=[{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in inputs if p.exists()]
inventory={k:[{'paragraph':i+1,'text':p.text} for i,p in enumerate(d.paragraphs) if re.search(r'\d',p.text)] for k,d in docs.items()}
for name,obj in [('TABLE_CELL_REGISTER.json',register),('PROSE_NUMERIC_REGISTER.json',prose),('NUMERIC_PARAGRAPH_INVENTORY.json',inventory),('INPUT_SNAPSHOT.json',snap),('HISTORICAL_TABLE_XML_QA.json',historical)]:
 (O/name).write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n')
qa={'status':'PASS' if not failures else 'FAIL','checked_utc':datetime.now(timezone.utc).isoformat(),'table_numeric_cells_checked':len(register),'named_main_prose_number_checks':len(prose),'historical_editable_tables_exact_XML':sum(x['pass'] for x in historical),'failures':failures,'limits':['Read-only comparison with archived H4/H5 outputs; no new empirical fit.','External references, dates, affiliation, author personal declarations and instrument semantics not externally reverified in this focused task.','Full paragraph inventory supplied; paragraph-number checks explicitly recorded in PROSE_NUMERIC_REGISTER. Supplement prose verified separately in additional register.']}
(O/'DOCUMENT_NUMERIC_QA.json').write_text(json.dumps(qa,indent=2,ensure_ascii=False)+'\n');print(json.dumps(qa,indent=2,ensure_ascii=False))
