#!/usr/bin/env python3
"""Convert the supplied Matplotlib SVG figures into native ODF vector/text shapes.

S3 figure kit conversion module, imported by build_h7_capacity.py.
No raster image or embedded SVG object is used. Original SVGs remain unchanged
as source references. Figure S3's table widths follow its canonical PDF, as
documented in the QA record. Path and text provenance is recorded per object.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import collections, hashlib, json, math, re, zipfile
from lxml import etree as E
from fontTools.svgLib.path import parse_path
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from matplotlib.font_manager import findfont, FontProperties

NS={
 'office':'urn:oasis:names:tc:opendocument:xmlns:office:1.0',
 'draw':'urn:oasis:names:tc:opendocument:xmlns:drawing:1.0',
 'style':'urn:oasis:names:tc:opendocument:xmlns:style:1.0',
 'text':'urn:oasis:names:tc:opendocument:xmlns:text:1.0',
 'svg':'urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0',
 'fo':'urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0',
 'dc':'http://purl.org/dc/elements/1.1/',
 'meta':'urn:oasis:names:tc:opendocument:xmlns:meta:1.0',
 'xlink':'http://www.w3.org/1999/xlink',
 'manifest':'urn:oasis:names:tc:opendocument:xmlns:manifest:1.0'}
SVG='http://www.w3.org/2000/svg'
qn=lambda n:'{'+NS[n.split(':')[0]]+'}'+n.split(':')[1]
def el(tag,attrs=None,text=None,**kw):
 x=E.Element(qn(tag),nsmap=kw.get('nsmap'))
 for k,v in (attrs or {}).items():x.set(qn(k) if ':' in k else k,str(v))
 if text is not None:x.text=text
 return x
cm=lambda v:f'{v*2.54/72:.9f}cm'
def css(s):
 return {k.strip():v.strip() for k,v in (a.split(':',1) for a in s.split(';') if ':' in a)}
def matrix_mul(a,b):
 aa,ab,ac,ad,ae,af=a;ba,bb,bc,bd,be,bf=b
 return (aa*ba+ac*bb,ab*ba+ad*bb,aa*bc+ac*bd,ab*bc+ad*bd,aa*be+ac*bf+ae,ab*be+ad*bf+af)
I=(1,0,0,1,0,0)
def transform(s):
 m=I
 for name,values in re.findall(r'(\w+)\s*\(([^)]*)\)',s or ''):
  v=[float(n) for n in re.findall(r'[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?',values)]
  if name=='translate':n=(1,0,0,1,v[0],v[1] if len(v)>1 else 0)
  elif name=='scale':n=(v[0],0,0,v[1] if len(v)>1 else v[0],0,0)
  elif name=='matrix':n=tuple(v)
  elif name=='rotate':
   a=math.radians(v[0]);n=(math.cos(a),math.sin(a),-math.sin(a),math.cos(a),0,0)
   if len(v)==3:n=matrix_mul(matrix_mul((1,0,0,1,v[1],v[2]),n),(1,0,0,1,-v[1],-v[2]))
  else:raise ValueError(name)
  m=matrix_mul(m,n)
 return m
def xy(m,p):
 a,b,c,d,e,f=m;x,y=p;return a*x+c*y+e,b*x+d*y+f
def recording(d,m=I):
 p=RecordingPen();parse_path(d,TransformPen(p,m));return p
def bbox(p):
 q=BoundsPen(None);p.replay(q);return q.bounds
def pathdata(p,scale=1000,origin=(0,0)):
 out=[]
 for op,pts in p.value:
  coords=' '.join(f'{(v-origin[j%2])*scale:.6f}'.rstrip('0').rstrip('.') for point in pts for j,v in enumerate(point))
  cmd={'moveTo':'M','lineTo':'L','curveTo':'C','qCurveTo':'Q','closePath':'Z','endPath':''}[op]
  if cmd:out.append(cmd+' '+coords)
 return ' '.join(out)

class Converter:
 def __init__(self,source):
  self.source=source;self.svg=E.parse(str(source)).getroot();self.width,self.height=map(float,self.svg.get('viewBox').split()[2:])
  self.ids={x.get('id'):x for x in self.svg.iter() if x.get('id')};self.records=[];self.styles=[];self.stylecache={};self.fontcache={};self.objects=[];self.warnings=[]
  self.content=el('office:document-content',{'office:version':'1.3'},nsmap=NS)
  fonts=el('office:font-face-decls');fonts.append(el('style:font-face',{'style:name':'DejaVu Sans','svg:font-family':"'DejaVu Sans'",'style:font-family-generic':'swiss','style:font-pitch':'variable'}));self.content.append(fonts)
  self.auto=el('office:automatic-styles');self.content.append(self.auto)
  body=el('office:body');drawing=el('office:drawing');self.page=el('draw:page',{'draw:name':source.stem,'draw:style-name':'dp1','draw:master-page-name':'Default'});drawing.append(self.page);body.append(drawing);self.content.append(body)

 def style(self,props,paragraph=None,text=None):
  key=json.dumps([props,paragraph,text],sort_keys=True)
  if key in self.stylecache:return self.stylecache[key]
  name='gr'+str(len(self.stylecache)+1);s=el('style:style',{'style:name':name,'style:family':'graphic'})
  s.append(el('style:graphic-properties',props))
  if paragraph:s.append(el('style:paragraph-properties',paragraph))
  if text:s.append(el('style:text-properties',text))
  self.auto.append(s);self.stylecache[key]=name;return name

 def addpath(self,p,style,source_id,description=''):
  bounds=bbox(p)
  if bounds is None:return
  x0,y0,x1,y1=bounds;w=max(x1-x0,0.001);h=max(y1-y0,0.001)
  fill=style.get('fill','#000000');stroke=style.get('stroke','none')
  gp={'draw:fill':'none' if fill=='none' else 'solid','draw:stroke':'none' if stroke=='none' else 'solid','svg:stroke-width':cm(float(style.get('stroke-width',1))),'svg:stroke-linecap':style.get('stroke-linecap','butt'),'draw:stroke-linejoin':style.get('stroke-linejoin','round')}
  if fill!='none':gp['draw:fill-color']=fill
  if stroke!='none':gp['svg:stroke-color']=stroke
  opacity=style.get('opacity',style.get('fill-opacity'))
  if opacity:gp['draw:opacity']=str(float(opacity)*100)+'%'
  dash=style.get('stroke-dasharray')
  if dash and dash!='none':
   vals=[float(v) for v in re.split(r'[ ,]+',dash) if v]
   dn='dash'+str(len(self.auto))
   dashprops={'draw:name':dn,'draw:style':'rect','draw:dots1':'1','draw:dots1-length':cm(vals[0]),'draw:distance':cm(vals[1] if len(vals)>1 else vals[0])}
   if len(vals)==4:dashprops.update({'draw:dots2':'1','draw:dots2-length':cm(vals[2])})
   self.auto.append(el('draw:stroke-dash',dashprops))
   gp['draw:stroke']='dash';gp['draw:stroke-dash']=dn
  name=f'{source_id}_path_{len(self.objects)+1}'
  ops=[(op,pts) for op,pts in p.value if op!='endPath']
  if abs(x1-x0)<1e-8 or abs(y1-y0)<1e-8:
   if stroke=='none':return
   start=(x0,y0);end=(x1,y1)
   path=el('draw:line',{'draw:name':name,'draw:style-name':self.style(gp),'draw:layer':'layout','svg:x1':cm(start[0]),'svg:y1':cm(start[1]),'svg:x2':cm(end[0]),'svg:y2':cm(end[1])})
  else:
   path=el('draw:path',{'draw:name':name,'draw:style-name':self.style(gp),'draw:layer':'layout','svg:x':cm(x0),'svg:y':cm(y0),'svg:width':cm(w),'svg:height':cm(h),'svg:viewBox':f'0 0 {round(w*1000)} {round(h*1000)}','svg:d':pathdata(p,origin=(x0,y0))})
  self.page.append(path);self.objects.append({'name':name,'kind':'path','source_id':source_id,'bounds':bounds,'description':description})

 def addtext(self,node,style,m,source_id):
  text=''.join(node.itertext())
  if not text:return
  size=float(re.search(r'[0-9.]+',style.get('font-size','10')).group())
  weight=style.get('font-weight','normal');family='DejaVu Sans';fontpath=findfont(FontProperties(family=family,weight=weight))
  if fontpath not in self.fontcache:self.fontcache[fontpath]=TTFont(fontpath)
  font=self.fontcache[fontpath];upm=font['head'].unitsPerEm;cmap=font.getBestCmap();adv=sum(font['hmtx'][cmap.get(ord(c),'.notdef')][0] for c in text)*size/upm
  # Native text remains editable. Font metrics place the text frame at its baseline.
  ascent=font['hhea'].ascent*size/upm;descent=-font['hhea'].descent*size/upm
  x=float(node.get('x','0'));y=float(node.get('y','0'));anchor=style.get('text-anchor','start')
  x-=adv/2 if anchor=='middle' else adv if anchor=='end' else 0
  w=max(adv+max(2,size*0.3),size*0.2);h=ascent+descent
  left,top=xy(m,(x,y-ascent));a,b,c,d,e,f=m
  gp={'draw:fill':'none','draw:stroke':'none','fo:padding':'0cm','fo:padding-top':'0cm','fo:padding-bottom':'0cm','fo:padding-left':'0cm','fo:padding-right':'0cm','draw:textarea-vertical-align':'top','draw:auto-grow-height':'false','draw:auto-grow-width':'false','draw:fit-to-size':'false','fo:wrap-option':'no-wrap'}
  pp={'fo:margin-left':'0cm','fo:margin-right':'0cm','fo:margin-top':'0cm','fo:margin-bottom':'0cm','fo:line-height':'100%','fo:text-align':'left'}
  tp={'style:font-name':family,'fo:font-size':f'{size}pt','fo:font-weight':weight,'fo:color':style.get('fill','#000000'),'fo:language':'en','fo:country':'GB'}
  attrs={'draw:name':f'{source_id}_text_{len(self.objects)+1}','draw:style-name':self.style(gp,pp,tp),'draw:layer':'layout','svg:width':cm(w),'svg:height':cm(h)}
  if abs(b)<1e-9 and abs(c)<1e-9:attrs.update({'svg:x':cm(left),'svg:y':cm(top)})
  else:
   attrs['draw:transform']=f'matrix({a:.12g} {b:.12g} {c:.12g} {d:.12g} {cm(left)} {cm(top)})'
  pname='p'+str(len(self.objects)+1)
  ps=el('style:style',{'style:name':pname,'style:family':'paragraph'})
  ps.append(el('style:paragraph-properties',pp));ps.append(el('style:text-properties',tp));self.auto.append(ps)
  frame=el('draw:frame',attrs);tb=el('draw:text-box');paragraph=el('text:p',{'text:style-name':pname})
  parts=re.split(r'( {2,})',text);paragraph.text=parts[0]
  for spaces,tail in zip(parts[1::2],parts[2::2]):
   space=el('text:s',{'text:c':len(spaces)});space.tail=tail;paragraph.append(space)
  tb.append(paragraph);frame.append(tb);self.page.append(frame)
  self.objects.append({'name':attrs['draw:name'],'kind':'text','source_id':source_id,'text':text,'baseline':xy(m,(float(node.get('x','0')),y)),'advance':adv,'font_size':size})

 def walk(self,node,m=I,inherited=None,source_id='svg',clip=None):
  tag=E.QName(node).localname
  if tag in ['defs','metadata','title','desc','style','clipPath','pattern']:return
  s=dict(inherited or {});s.update(css(node.get('style','')))
  for key in ['fill','stroke','stroke-width','opacity','fill-opacity','font-size','font-family','font-weight','text-anchor']:
   if node.get(key) is not None:s[key]=node.get(key)
  m=matrix_mul(m,transform(node.get('transform')));source_id=node.get('id',source_id)
  if node.get('clip-path'):
   cp=self.ids[node.get('clip-path')[5:-1]].find('{'+SVG+'}rect')
   if cp is None:raise ValueError('Unsupported non-rectangular clipping path')
   x=float(cp.get('x'));y=float(cp.get('y'));clip=(x,y,x+float(cp.get('width')),y+float(cp.get('height')))
  table_context=self.source.stem=='Figure_S3' and any(a.get('id')=='table_1' for a in node.iterancestors())
  # The canonical PDF's table has a wider row-label column than its SVG export.
  # Reconcile only that presentation difference, using measured PDF coordinates.
  table_boundary=182.219468;table_shift=19.888852
  if tag=='use':
   href=node.get('{http://www.w3.org/1999/xlink}href') or node.get('href');ref=self.ids[href[1:]]
   m=matrix_mul(m,(1,0,0,1,float(node.get('x',0)),float(node.get('y',0))))
   self.walk(ref,m,s,source_id,clip);return
  if tag=='text':
   anchor_x=xy(m,(float(node.get('x','0')),float(node.get('y','0'))))[0]
   if table_context and anchor_x>=table_boundary-1e-6:m=matrix_mul((1,0,0,1,table_shift,0),m)
   self.addtext(node,s,m,source_id);return
  if tag=='path':
   p=recording(node.get('d',''),m)
   if table_context:
    p.value=[(op,tuple((x+table_shift if x>=table_boundary-1e-6 else x,y) for x,y in pts)) for op,pts in p.value]
   bounds=bbox(p)
   outside=clip and bounds and (bounds[0]<clip[0]-1e-6 or bounds[1]<clip[1]-1e-6 or bounds[2]>clip[2]+1e-6 or bounds[3]>clip[3]+1e-6)
   if outside:
    vertices=flatten(p.value)
    if s.get('fill','#000000')!='none':
     poly=clippolygon(vertices,clip)
     if poly:
      fill=RecordingPen();fill.moveTo(poly[0]);[fill.lineTo(q) for q in poly[1:]];fill.closePath();fs=dict(s);fs['stroke']='none';self.addpath(fill,fs,source_id,'clipped boundary fill; curve tolerance <=0.01pt')
    if s.get('stroke','none')!='none':
     stroke=RecordingPen()
     for a,b in zip(vertices,vertices[1:]+vertices[:1]):
      seg=clipline(a,b,clip)
      if seg:stroke.moveTo(seg[0]);stroke.lineTo(seg[1]);stroke.endPath()
     ss=dict(s);ss['fill']='none';self.addpath(stroke,ss,source_id,'clipped boundary stroke; curve tolerance <=0.01pt')
   elif s.get('fill','').startswith('url('):
    self.pattern(p,s,source_id)
   else:self.addpath(p,s,source_id)
   return
  if tag=='rect':
   x=float(node.get('x',0));y=float(node.get('y',0));w=float(node.get('width'));h=float(node.get('height'))
   self.addpath(recording(f'M{x} {y} L{x+w} {y} L{x+w} {y+h} L{x} {y+h} Z',m),s,source_id);return
  for child in node:self.walk(child,m,s,source_id,clip)

 def pattern(self,p,style,source_id):
  # Matplotlib hatches are converted to native paths, not bitmap fills.
  pid=style['fill'][5:-1];pat=self.ids[pid];bg=pat.find('{'+SVG+'}rect');s=dict(style);s['fill']=bg.get('fill');self.addpath(p,s,source_id,'pattern background')
  box=bbox(p);x0,y0,x1,y1=box;W=float(pat.get('width'));H=float(pat.get('height'))
  if abs(x1-x0)<1e-8 or abs(y1-y0)<1e-8:return
  combined=RecordingPen()
  for child in pat:
   if E.QName(child).localname!='path':continue
   hs=css(child.get('style',''));hp=recording(child.get('d'));subs=[];cur=[]
   for op,pts in hp.value:
    if op=='moveTo' and cur:subs.append(cur);cur=[]
    cur.append((op,pts))
   if cur:subs.append(cur)
   for ix in range(math.floor(x0/W)-1,math.ceil(x1/W)+1):
    for iy in range(math.floor(y0/H)-1,math.ceil(y1/H)+1):
     for sub in subs:
      moved=[(op,tuple((x+ix*W,y+iy*H) for x,y in pts)) for op,pts in sub]
      rec=RecordingPen();rec.value=moved;b=bbox(rec)
      if b is None or b[2]<x0 or b[0]>x1 or b[3]<y0 or b[1]>y1:continue
      if all(op in ('moveTo','lineTo','endPath') for op,_ in moved):
       ps=[pt for op,pts in moved for pt in pts]
       if len(ps)==2:
        clipped=clipline(ps[0],ps[1],box)
        if clipped:combined.moveTo(clipped[0]);combined.lineTo(clipped[1]);combined.endPath()
      elif b[0]>=x0 and b[2]<=x1 and b[1]>=y0 and b[3]<=y1:
       combined.value.extend(moved)
      else:
       # Boundary circles are flattened at <=0.01pt before rectangular clipping.
       pts=flatten(moved);pts=clippolygon(pts,box)
       if pts:combined.moveTo(pts[0]);[combined.lineTo(q) for q in pts[1:]];combined.closePath()
   self.addpath(combined,hs,source_id,'editable hatch geometry; boundary flattening tolerance <=0.01pt')

 def save(self,out):
  if self.source.stem=='Figure_S3':
   self.warnings.append('The table column start is reconciled to the canonical PDF: 182.219468pt in the SVG, 202.10832pt in the PDF, shift 19.888852pt. All table labels and values are unchanged.')
  self.walk(self.svg)
  styles=el('office:document-styles',{'office:version':'1.3'},nsmap=NS);styles.append(el('office:styles'))
  auto=el('office:automatic-styles');layout=el('style:page-layout',{'style:name':'pm1'});layout.append(el('style:page-layout-properties',{'fo:page-width':cm(self.width),'fo:page-height':cm(self.height),'fo:margin-top':'0cm','fo:margin-bottom':'0cm','fo:margin-left':'0cm','fo:margin-right':'0cm','style:print-orientation':'portrait'}));auto.append(layout)
  dp=el('style:style',{'style:name':'dp1','style:family':'drawing-page'});dp.append(el('style:drawing-page-properties',{'draw:fill':'solid','draw:fill-color':'#ffffff','draw:background-size':'border','style:repeat':'no-repeat'}));auto.append(dp);styles.append(auto)
  masters=el('office:master-styles');masters.append(el('style:master-page',{'style:name':'Default','style:page-layout-name':'pm1','draw:style-name':'dp1'}));styles.append(masters)
  meta=el('office:document-meta',{'office:version':'1.3'},nsmap=NS);m=el('office:meta');m.append(el('meta:generator',text='svg_to_native_odg.py 1.0'));m.append(el('dc:creator',text='Antonio Clim'));m.append(el('dc:title',text=self.source.stem));m.append(el('meta:creation-date',text=datetime.now(timezone.utc).isoformat()));m.append(el('meta:user-defined',{'meta:name':'Source SVG SHA-256'},hashlib.sha256(self.source.read_bytes()).hexdigest()));m.append(el('meta:user-defined',{'meta:name':'Original vector renderer'},'Matplotlib 3.10.8'));meta.append(m)
  manifest=el('manifest:manifest',{'manifest:version':'1.3'},nsmap={'manifest':NS['manifest']})
  for path,mime in [('/','application/vnd.oasis.opendocument.graphics'),('content.xml','text/xml'),('styles.xml','text/xml'),('meta.xml','text/xml')]:manifest.append(el('manifest:file-entry',{'manifest:full-path':path,'manifest:media-type':mime}))
  out.parent.mkdir(parents=True,exist_ok=True)
  with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
   z.writestr('mimetype','application/vnd.oasis.opendocument.graphics',compress_type=zipfile.ZIP_STORED)
   for n,tree in [('content.xml',self.content),('styles.xml',styles),('meta.xml',meta),('META-INF/manifest.xml',manifest)]:z.writestr(n,E.tostring(tree,xml_declaration=True,encoding='UTF-8'))
  return {'file':out.name,'source_svg':self.source.name,'objects':len(self.objects),'object_types':dict(collections.Counter(x['kind'] for x in self.objects)),'image_objects':0,'warnings':self.warnings,'source_sha256':hashlib.sha256(self.source.read_bytes()).hexdigest(),'objects_detail':self.objects}

def clipline(a,b,box):
 x0,y0,x1,y1=box;dx=b[0]-a[0];dy=b[1]-a[1];t0,t1=0.,1.
 for p,q in [(-dx,a[0]-x0),(dx,x1-a[0]),(-dy,a[1]-y0),(dy,y1-a[1])]:
  if abs(p)<1e-15:
   if q<0:return None
  else:
   v=q/p
   if p<0:t0=max(t0,v)
   else:t1=min(t1,v)
   if t0>t1:return None
 return ((a[0]+t0*dx,a[1]+t0*dy),(a[0]+t1*dx,a[1]+t1*dy))
def flatten(ops):
 out=[];last=None
 for op,pts in ops:
  if op in ['moveTo','lineTo']:out.append(pts[0]);last=pts[0]
  elif op=='curveTo':
   p0=last;p1,p2,p3=pts
   for i in range(1,17):
    t=i/16;u=1-t;out.append(tuple(u**3*p0[k]+3*u*u*t*p1[k]+3*u*t*t*p2[k]+t**3*p3[k] for k in range(2)))
   last=p3
 return out
def clippolygon(points,box):
 x0,y0,x1,y1=box
 for axis,bound,sign in [(0,x0,1),(0,x1,-1),(1,y0,1),(1,y1,-1)]:
  result=[]
  if not points:return []
  prev=points[-1];pin=(prev[axis]-bound)*sign>=0
  for cur in points:
   cin=(cur[axis]-bound)*sign>=0
   if cin!=pin:
    t=(bound-prev[axis])/(cur[axis]-prev[axis]);result.append(tuple(prev[k]+t*(cur[k]-prev[k]) for k in range(2)))
   if cin:result.append(cur)
   prev,pin=cur,cin
  points=result
 return points

