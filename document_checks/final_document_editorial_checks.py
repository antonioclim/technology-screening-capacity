"""Static editorial checks; does not replace numerical or visual verification."""
from pathlib import Path
from zipfile import ZipFile
from lxml import etree
import hashlib,json,re,datetime,os,tempfile
ROOT=Path(__file__).resolve().parents[1]
FILES={'manuscript':ROOT/'manuscript/Manuscript_Identified.docx','supplement':ROOT/'supplement/Supplement.docx','cover':ROOT/'editorial/output/Cover_Letter.docx','highlights':ROOT/'editorial/output/Highlights.docx'}
NS={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,b):
 fd,n=tempfile.mkstemp(dir=p.parent,prefix=p.name+'.');
 with os.fdopen(fd,'wb') as f:f.write(b);f.flush();os.fsync(f.fileno())
 os.replace(n,p);assert p.read_bytes()==b
out={'generated_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'Actual final four DOCX static editorial checks; numerical validation and all-page visual QA are separate records.','files':{}}
for name,p in FILES.items():
 with ZipFile(p) as z:
  assert z.testzip() is None
  doc=etree.fromstring(z.read('word/document.xml'));pars=[''.join(t.text or '' for t in x.xpath('.//w:t',namespaces=NS)) for x in doc.xpath('./w:body/w:p',namespaces=NS)]
  tabletext=[[' | '.join(''.join(t.text or '' for t in c.xpath('.//w:t',namespaces=NS)) for c in row.xpath('./w:tc',namespaces=NS)) for row in table.xpath('./w:tr',namespaces=NS)] for table in doc.xpath('//w:tbl',namespaces=NS)]
  vertical=doc.xpath('//w:tbl//w:tblBorders/w:left[not(@w:val="nil" or @w:val="none")]|//w:tbl//w:tblBorders/w:right[not(@w:val="nil" or @w:val="none")]|//w:tbl//w:tblBorders/w:insideV[not(@w:val="nil" or @w:val="none")]',namespaces=NS)
  shd=doc.xpath('//w:tbl//w:shd',namespaces=NS);tracked=doc.xpath('//w:ins|//w:del',namespaces=NS)
  badparts=[x for x in z.namelist() if 'comment' in x.lower() or 'customxml' in x.lower()]
  assert not(vertical or shd or tracked or badparts)
  props={n:z.read(n).decode() for n in ['docProps/core.xml','docProps/app.xml'] if n in z.namelist()}
  out['files'][name]={'path':str(p),'sha256':sha(p),'bytes':p.stat().st_size,'paragraphs':len(pars),'tables':len(tabletext),'vertical_table_borders':len(vertical),'table_shading':len(shd),'tracked_changes':len(tracked),'comments_or_customxml_parts':badparts,'metadata':props}
  if name=='manuscript':
   abstract=pars[pars.index('Abstract')+1];out['abstract']={'words':len(abstract.split()),'text':abstract};assert len(abstract.split())<=250
   ai=(ROOT/'baseline_h4/AUTHOR_APPROVED_AI_DECLARATION_EN.txt').read_text().strip();assert ai in pars;out['approved_AI_exact']=True
   out['tone_residues']={x:any(x in v for v in pars) for x in ['fabricated','manufacture','rule out a claim','allegedly']};assert not any(out['tone_residues'].values())
   assert 'equal-country mean' in abstract and 'total-variation distance' in abstract
   out['manuscript_table_captions']=[x for x in pars if re.match(r'Table [1-3]\. ',x)]
   out['manuscript_dois']=re.findall(r'https://doi.org/\S+','\n'.join(pars));assert len(out['manuscript_dois'])==9
   out['author_runs']=[''.join(x.xpath('.//w:t/text()',namespaces=NS)) for x in doc.xpath('./w:body/w:p[2]/w:r',namespaces=NS)]
   assert out['author_runs']==['Antonio Clim','a'];assert doc.xpath('./w:body/w:p[2]/w:r[2]/w:rPr/w:vertAlign[@w:val="superscript"]',namespaces=NS)
  elif name=='supplement':
   out['supplement_table_captions']=[x for x in pars if re.match(r'Table S\d+\. ',x)]
   out['supplement_figure_captions']=[x for x in pars if re.match(r'Figure S\d+\. ',x)]
   out['S10_first_contrast']=tabletext[9][1];assert out['S10_first_contrast'].startswith('MOST5 added to B')
   out['S10_baseline_note_explicit']=any(('All fitted information contrasts hold B fixed' in x) or ('Except for learned versus fixed MOST, all contrasts condition on B; the size comparison also includes log employment.' in x) for x in pars);assert out['S10_baseline_note_explicit']
  elif name=='cover':
   out['cover_text']=pars;out['cover_words']=len(' '.join(pars).split());assert '13,617 common firms at the same quota' in '\n'.join(pars)
  elif name=='highlights':
   h=[x for x in pars if x and x!='Highlights'];out['highlights']=[{'text':x,'characters':len(x)} for x in h];assert 3<=len(h)<=5 and all(len(x)<=85 for x in h)
   assert h[3].startswith('At 50%')
out['status']='PASS'
write(ROOT/'editorial_audit/H5_FINAL_DOCUMENT_EDITORIAL_QA.json',(json.dumps(out,ensure_ascii=False,indent=2)+'\n').encode())
print(json.dumps({'status':out['status'],'sha256':{k:v['sha256'] for k,v in out['files'].items()},'abstract_words':out['abstract']['words'],'highlight_characters':[x['characters'] for x in out['highlights']],'S10_first_contrast':out['S10_first_contrast']},indent=2))
