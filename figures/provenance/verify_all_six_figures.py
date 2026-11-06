"""Verify current PDFs/SVGs and regenerated artwork without changing metadata."""
from __future__ import annotations
import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
import subprocess, tempfile
from lxml import etree
from PIL import Image
from pypdf import PdfReader

NAMES=['Figure_1','Figure_2','Figure_S1','Figure_S2','Figure_S3','Figure_S4']

def canonical_svg(path):
    root=etree.fromstring(path.read_bytes())
    for node in list(root.iter()):
        if node.tag=='{http://purl.org/dc/elements/1.1/}date':
            node.getparent().remove(node)
    identities={node.attrib['id']:f'id{i}'for i,node in enumerate(root.iter())if'id'in node.attrib}
    for node in root.iter():
        for key,value in list(node.attrib.items()):
            if key=='id':node.attrib[key]=identities[value]
            elif value.startswith('#')and value[1:]in identities:node.attrib[key]='#'+identities[value[1:]]
            else:
                node.attrib[key]=re.sub(r'url\(#([^)]+)\)',lambda m:'url(#'+identities.get(m.group(1),m.group(1))+')',value)
    return etree.tostring(root,method='c14n',with_comments=False)

def pdf_pixels(path):
    with tempfile.TemporaryDirectory(prefix='papere-figure-verify-') as d:
        stem=Path(d)/'render'
        subprocess.run(['pdftoppm','-singlefile','-r','144','-png',str(path),str(stem)],check=True,capture_output=True)
        data=stem.with_suffix('.png').read_bytes()
    with Image.open(BytesIO(data)) as image:
        image.load();pixels=image.tobytes();size=image.size
    return size,sha256(pixels).hexdigest(),data

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--payload',type=Path,required=True);p.add_argument('--replay',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True);a=p.parse_args()
    results={}
    for n in NAMES:
        reference=a.payload/'upload_pdf'/(n+'.pdf');rerun=a.replay/'pdf'/(n+'.pdf')
        rp=PdfReader(reference);np=PdfReader(rerun)
        assert len(rp.pages)==len(np.pages)==1
        rsize,rhash,_=pdf_pixels(reference);nsize,nhash,_=pdf_pixels(rerun)
        rsvg=a.payload/'editable_svg'/(n+'.svg');nsvg=a.replay/'svg'/(n+'.svg')
        png=a.replay/'png'/(n+'.png')
        with Image.open(png)as im:im.verify()
        q={'pdf_byte_identical':reference.read_bytes()==rerun.read_bytes(),
           'pdf_visible_text_identical':rp.pages[0].extract_text()==np.pages[0].extract_text(),
           'pdf_page_size_identical':list(rp.pages[0].mediabox)==list(np.pages[0].mediabox),
           'pdf_render_pixel_identical':rsize==nsize and rhash==nhash,
           'pdf_render_pixel_sha256':nhash,'render_dimensions':list(nsize),
           'svg_byte_identical':rsvg.read_bytes()==nsvg.read_bytes(),
           'svg_structure_equal_ignoring_dates_and_internal_ID_names':canonical_svg(rsvg)==canonical_svg(nsvg),
           'metadata_reference':{str(k):str(v)for k,v in rp.metadata.items()},
           'metadata_replay':{str(k):str(v)for k,v in np.metadata.items()},
           'replay_png_valid':True}
        oldpng=a.payload/'preview_png'/(n+'.png')
        if oldpng.exists():q['reference_PNG_byte_identical']=oldpng.read_bytes()==png.read_bytes()
        assert all(q[k]for k in ['pdf_visible_text_identical','pdf_page_size_identical','pdf_render_pixel_identical','svg_structure_equal_ignoring_dates_and_internal_ID_names']),n
        assert 'Matplotlib'in q['metadata_reference'].get('/Creator','')
        assert 'Matplotlib'in q['metadata_replay'].get('/Creator','')
        results[n]=q
    result={'status':'PASS','figures':results,'scope':'CSV figure generation only; no empirical model re-estimation, survey inference, native Windows or journal portal validation','comparison_normalisation':'Only in-memory comparison ignores SVG dates and equivalent internal ID names; delivered metadata is unchanged.'}
    a.receipt.parent.mkdir(parents=True,exist_ok=True);a.receipt.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':'PASS','figures':len(results),'PDF_pixel_identity_all':True,'SVG_structural_identity_all':True}))

if __name__=='__main__':main()
