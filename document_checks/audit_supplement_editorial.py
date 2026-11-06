#!/usr/bin/env python3
"""Additional read-only checks of final SI prose and editorial numerical fields."""
from pathlib import Path
import hashlib,json
import audit_document_numbers as a

for pi,co,key in [(58,'planning','MOST_base_primary_n'),(58,'planning','matched_primary_n'),(58,'administration','MOST_base_primary_n'),(58,'administration','matched_primary_n')]:
 a.pnum('supplement',pi,a.qa4[co][key],'baseline_h4/reference/results/COHORT_QA.json',{'cohort':co},key,integer=True)
for pi in [68]:
 a.pnum('supplement',pi,a.con(),a.H4D,{'cohort':'planning','contrast':'MOST5_increment','quota':.5},'equal_country_mean',digits=3)
 a.pnum('supplement',pi,a.influence,a.H4C,{'cohort':'planning','quota':.5,'exclude_countries':['Bangladesh','Brazil']},'post-hoc equal-country mean',digits=3)
for field in ['sector_composition_tv_vs_B_pp_country_mean','employment_composition_tv_vs_B_pp_country_mean']:
 a.pnum('supplement',71,a.mean(field=field),a.H4A,{'cohort':'planning','policy':'B_MOST5','quota':.5},field,digits=3)
for dimension in ['sector','employment']:
 d=a.subset(a.H4T,cohort='planning',quota=.5,dimension=dimension,route='country_holdout');v=d.groupby('country').composition_tv_pp.mean().mean();a.pnum('supplement',71,v,a.H4T,{'cohort':'planning','quota':.5,'dimension':dimension},'equal-country mean',digits=3)
for pi,source in [(72,'BurkinaFaso'),(73,'Cambodia')]:
 a.pnum('supplement',pi,a.qa4['planning']['source_counts'][source],'baseline_h4/reference/results/COHORT_QA.json',{'cohort':'planning','source':source},'source_counts',integer=True)
 for policy in ['B','B_MOST5','fixed_MOST5','lottery']:
  f={'cohort':'planning','source':source,'policy':policy,'quota':.5};a.pnum('supplement',pi,a.value(a.H4S,a.Y,**f),a.H4S,f,a.Y,digits=3)
 f={'cohort':'planning','source':source,'policy':'B_MOST5','quota':.5};a.pnum('supplement',pi,a.value(a.H4S,'yield_delta_vs_B',**f),a.H4S,f,'yield_delta_vs_B',digits=3)
for policy in ['B','B_MOST5']:
 f={'policy':policy,'quota':.5};a.pnum('supplement',80,a.value(a.H4P,'expected_allocation_tv_pp_country_mean',**f),a.H4P,f,'expected_allocation_tv_pp_country_mean',digits=3)
for field in ['sector_composition_tv_pp_country_mean','employment_composition_tv_pp_country_mean']:
 f={'policy':'B_MOST5','quota':.5};a.pnum('supplement',80,a.value(a.H4P,field,**f),a.H4P,f,field,digits=3)
a.pnum('supplement',85,a.qa5['common_functions']['primary_n'],'empirical/results/COHORT_QA.json',{'cohort':'common_functions'},'primary_n',integer=True)
for s in ['BurkinaFaso','Cambodia']:a.pnum('supplement',85,a.qa5['common_functions']['source_counts'][s],'empirical/results/COHORT_QA.json',{'cohort':'common_functions','source':s},'source_counts',integer=True)
for family in ['logistic','tree']:
 f={'cohort':'common_functions','family':family,'quota':.5}
 for field in ['admin_minus_plan_yield_mean','function_expected_allocation_tv_pp_mean','admin_positive_country_n','admin_negative_country_n']:
  a.pnum('supplement',86,a.value(a.H5F,field,**f),a.H5F,f,field,digits=3,integer=field.endswith('_n'))
for family in ['logistic','tree']:
 f={'cohort':'planning_H4','policy':family+'_B_plan_MOST5','quota':.5}
 a.pnum('supplement',87,a.value(a.H5A,'yield_delta_vs_B_mean',**f),a.H5A,f,'yield_delta_vs_B_mean',digits=3)
 for field in ['positive_increment_country_n','negative_increment_country_n']:a.pnum('supplement',87,a.value(a.H5A,field,**f),a.H5A,f,field,integer=True)
for pi,source in [(88,'BurkinaFaso'),(89,'Cambodia')]:
 a.pnum('supplement',pi,a.qa5['common_functions']['source_counts'][source],'empirical/results/COHORT_QA.json',{'cohort':'common_functions','source':source},'source_counts',integer=True)
 for family in ['logistic','tree']:
  for function in ['plan','admin']:
   f={'cohort':'common_functions','source':source,'policy':family+'_B_'+function+'_MOST5','quota':.5};a.pnum('supplement',pi,a.value(a.H5S,'yield_delta_vs_B',**f),a.H5S,f,'yield_delta_vs_B',digits=3)

# Retained H3 paragraphs are compared exactly, not merely numerically.
oldmain=a.oldmain
textlist=[p.text for p in a.docs['supplement'].paragraphs]
preservation=[{'source_h3_main_zero_based_paragraph':i,'exact_text':oldmain.paragraphs[i].text,'found_in_current_supplement':oldmain.paragraphs[i].text in textlist,'supplement_one_based_paragraph':textlist.index(oldmain.paragraphs[i].text)+1 if oldmain.paragraphs[i].text in textlist else None} for i in [17,23,24]]
assert all(x['found_in_current_supplement'] for x in preservation)

# Quantitative editorial claims use the primary planning analysis and common-function follow-up separately.
editor=json.loads((a.R/'editorial/EDITORIAL_TEXT.json').read_text());cover='\n'.join(editor['cover']);highlights=editor['highlights'];edchecks=[]
def ed(where,actual,expected,source,selector,field):
 ok=expected in actual
 edchecks.append({'field':where,'expected':expected,'source':source,'selector':selector,'metric':field,'pass':ok})
 if not ok:a.failures.append(edchecks[-1])
ed('cover',cover,format(a.qa4['planning']['matched_primary_n'],','),'baseline_h4/reference/results/COHORT_QA.json',{'cohort':'planning'},'matched_primary_n')
ed('cover',cover,format(a.qa5['common_functions']['primary_n'],','),'empirical/results/COHORT_QA.json',{'cohort':'common_functions'},'primary_n')
ed('cover',cover,f'{a.con():.2f}',a.H4D,{'cohort':'planning','contrast':'MOST5_increment','quota':.5},'equal_country_mean')
d=a.subset(a.H4T,cohort='planning',quota=.5,dimension='sector',route='country_holdout');tv=d.groupby('country').composition_tv_pp.mean().mean()
ed('cover',cover,f'{tv:.2f}',a.H4T,{'cohort':'planning','dimension':'sector','quota':.5},'equal-country composition distance')
admin=a.value(a.H5F,'admin_minus_plan_yield_mean',cohort='common_functions',family='logistic',quota=.5)
ed('cover',cover,f'{admin:.2f}',a.H5F,{'cohort':'common_functions','family':'logistic','quota':.5},'admin_minus_plan_yield_mean')
for hi,expected,source,selector,field in [(0,f'{a.con():.2f}',a.H4D,{'cohort':'planning','quota':.5},'MOST5_increment'),(2,f'{tv:.2f}',a.H4T,{'cohort':'planning','dimension':'sector','quota':.5},'equal-country composition distance'),(3,f'{admin:.2f}',a.H5F,{'cohort':'common_functions','family':'logistic','quota':.5},'admin_minus_plan_yield_mean')]:ed('highlight_'+str(hi+1),highlights[hi],expected,source,selector,field)
ed('cover',cover,'seven countries and losses in four',a.H4D,{'cohort':'planning','contrast':'MOST5_increment','quota':.5},'positive/negative country counts')
assert len(highlights)==5 and all(len(x)<=85 for x in highlights)
# Check the qualitative sign-change highlight against both actual secondary results.
for s in ['BurkinaFaso','Cambodia']:
 f={'cohort':'planning_H4','source':s,'quota':.5};lv=a.value(a.H5S,'yield_delta_vs_B',policy='logistic_B_plan_MOST5',**f);tvv=a.value(a.H5S,'yield_delta_vs_B',policy='tree_B_plan_MOST5',**f);assert lv*tvv<0

newprose=[x for x in a.prose if x['document']==str(a.SUPP)]
(a.O/'SUPPLEMENT_PROSE_NUMERIC_REGISTER.json').write_text(json.dumps(newprose,indent=2,ensure_ascii=False)+'\n')
(a.O/'EDITORIAL_NUMERIC_REGISTER.json').write_text(json.dumps(edchecks,indent=2,ensure_ascii=False)+'\n')
(a.O/'H3_PARAGRAPH_PRESERVATION_QA.json').write_text(json.dumps(preservation,indent=2,ensure_ascii=False)+'\n')
current={'main_sha256':hashlib.sha256(a.MAIN.read_bytes()).hexdigest(),'supplement_sha256':hashlib.sha256(a.SUPP.read_bytes()).hexdigest(),'editorial_text_sha256':hashlib.sha256((a.R/'editorial/EDITORIAL_TEXT.json').read_bytes()).hexdigest()}
assert current['main_sha256']=='d31832598cd42f4d6c4050ba7ea899037f0a0b04602f8dfa28275635c4509cc8'
assert current['supplement_sha256']=='980d6092ab81d385e40f29b4483bb7923425400a3442988ff0caf1a0ca4d832a'
qa={'status':'PASS' if not a.failures else 'FAIL',**current,'new_table_numeric_cells':len(a.register),'main_named_numeric_prose_checks':81,'supplement_named_numeric_prose_checks':len(newprose),'editorial_numeric_checks':len(edchecks),'five_highlight_lengths':[len(x) for x in highlights],'exact_historical_tables':7,'exact_restored_h3_paragraphs':len(preservation),'failures':a.failures,'remaining_precision_observation':'Cover and highlight4 state the0.64 common-function contrast without naming logistic. Numeric value correct; adding learner wording would prevent interpreting it as learner-independent. Not a numeric error.','not_checked_externally':['References/DOI destination content','World Bank instrument wording/national harmonisation','Download date/affiliation/ORCID','Funding and competing-interest personal declarations','Current journal/portal rules'],'scope':'Static document-to-canonical-output audit, no additional empirical test or external access.'}
(a.O/'FINAL_DOCUMENT_NUMERIC_QA.json').write_text(json.dumps(qa,indent=2,ensure_ascii=False)+'\n');print(json.dumps(qa,indent=2,ensure_ascii=False))
