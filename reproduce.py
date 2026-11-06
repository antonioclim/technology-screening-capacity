"""Reproduce Paper E calculations from lawful external inputs or supplied figure CSVs.

No data download, publication, external service or repository automation is used.
Outputs from empirical modes are private analytical results and must remain outside
the software payload. Synthetic tests and figure generation are distinct modes.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

ROOT=Path(__file__).resolve().parent
RAW_SHA='6d77d3ffb9dcef2ca4534e1c438ddd2e0b357eb852e6c5b48aa5fa6c3cbe2f0e'
EMPIRICAL={'pooled','transfer','conditional','followup','acquisition','all'}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=['synthetic','figures','pooled','transfer','conditional','followup','acquisition','prepare','all'],required=True)
    p.add_argument('--microdata',type=Path)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();out=a.output.resolve()
    if out.exists():p.error('--output must be a new directory')
    if out==ROOT or ROOT in out.parents:p.error('--output must be outside the software payload')
    if a.mode in EMPIRICAL|{'prepare'}:
        if not a.microdata:p.error('--microdata is required for empirical and preparation modes')
        raw=a.microdata.resolve()
        if not raw.is_file()or sha256(raw.read_bytes()).hexdigest()!=RAW_SHA:p.error('The original FAT ZIP identity does not match')
    out.mkdir(parents=True);(out/'logs').mkdir()
    receipt={'status':'RUNNING','mode':a.mode,'started_utc':datetime.now(timezone.utc).isoformat(),'empirical_reproduction':False,'commands':[],
             'runtime':{'python':platform.python_version(),'platform':platform.platform()},'new_public_release_or_deposit':False}
    def save():
        path=out/'REPRODUCTION_RECEIPT.json';tmp=out/'REPRODUCTION_RECEIPT.tmp'
        b=(json.dumps(receipt,indent=2,sort_keys=True)+'\n').encode()
        with tmp.open('wb')as f:f.write(b);f.flush();os.fsync(f.fileno())
        assert tmp.read_bytes()==b;os.replace(tmp,path);assert path.read_bytes()==b
    def call(label,args):
        cmd=[sys.executable,'-B',*map(str,args)]
        env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
        r=subprocess.run(cmd,cwd=ROOT,env=env,capture_output=True)
        log_hashes={}
        for kind,b in [('stdout',r.stdout),('stderr',r.stderr)]:
            path=out/'logs'/f'{label}.{kind}.txt';tmp=path.with_suffix('.tmp')
            with tmp.open('wb')as f:f.write(b);f.flush();os.fsync(f.fileno())
            assert tmp.read_bytes()==b;os.replace(tmp,path);assert path.read_bytes()==b
            log_hashes[kind]={'bytes':len(b),'sha256':sha256(b).hexdigest()}
        receipt['commands'].append({'label':label,'arguments':list(map(str,args)),'exit_code':r.returncode,'logs':log_hashes});save()
        if r.returncode:raise RuntimeError(f'{label} failed; inspect its local log')
        print(label+' PASS',flush=True)
    try:
        save()
        if a.mode in {'synthetic','all'}:
            for label,folder,pattern in [('legacy_transfer','legacy/transfer/engine','test_holdout_engine.py'),('legacy_raw_pooled','legacy','test_raw_pooled.py'),('conditional','conditional/software','test_pilot_primitives.py'),('followup','followup/software','test_h5_followup.py'),('acquisition','acquisition/software','test_h7_primitives.py')]:
                call('synthetic_'+label,['-m','unittest','discover','-s',ROOT/folder,'-p',pattern,'-v'])
        if a.mode in {'pooled','all'}:
            call('pooled',[ROOT/'legacy/run_raw_pooled.py','--microdata',raw,'--frozen-module',ROOT/'legacy/transfer/extractor/vendor/upstream/run_e4_frozen_analysis_v1.0.2.py','--protocol',ROOT/'legacy/transfer/protocol/H1_PROTOCOL.json','--deletion-core',ROOT/'legacy/rebuild_x10_bounds.py','--output',out/'pooled'])
        if a.mode in {'transfer','all'}:
            call('transfer',[ROOT/'legacy/transfer/run_transfer_from_raw.py','--microdata',raw,'--reported',ROOT/'legacy/reported_results/transfer','--output',out/'transfer'])
        if a.mode in {'conditional','prepare','all'}:
            c=ROOT/'conditional'
            args=[c/'software/run_h4_pilot.py','--microdata',raw,'--frozen-e4',c/'inputs/run_e4_frozen_analysis_v1.0.2.py','--h1-protocol',c/'inputs/H1_PROTOCOL.json','--protocol',c/'protocol/H4_PROTOCOL.json','--addendum',c/'protocol/H4_ADDENDUM_A01.json','--output',out/'conditional_run']
            if a.mode=='prepare':args+=['--prepare-only']
            call('conditional',args)
            if a.mode!='prepare':
                call('conditional_summary',[c/'software/summarise_h4.py','--run',out/'conditional_run','--output',out/'conditional_summary'])
                call('conditional_accounting',[c/'software/verify_aggregate_accounting.py','--run',out/'conditional_run','--summary',out/'conditional_summary','--output',out/'CONDITIONAL_ACCOUNTING_QA.json'])
        if a.mode in {'followup','prepare','all'}:
            f=ROOT/'followup';args=[f/'software/run_h5_followup.py','--microdata',raw,'--output',out/'followup']
            if a.mode=='prepare':args+=['--prepare-only']
            call('followup',args)
            if a.mode!='prepare':call('followup_accounting',[f/'software/verify_h5_accounting.py','--results',out/'followup','--receipt',out/'FOLLOWUP_ACCOUNTING_QA.json'])
        if a.mode in {'acquisition','all'}:
            call('acquisition',[ROOT/'acquisition/software/run_h7.py','--microdata',raw,'--output',out/'acquisition'])
        if a.mode in {'figures','all'}:
            call('figures',[ROOT/'figures/generate_all_figures.py','--output',out/'figures'])
        receipt.update(status='PASS',completed_utc=datetime.now(timezone.utc).isoformat(),empirical_reproduction=a.mode in EMPIRICAL,
                       scope={'synthetic':'Software fixtures only; no empirical data read','figures':'Reported aggregate CSV-to-figure reproduction only','prepare':'Input identity and cohort preparation only; no new fitted scores','all':'All canonical empirical engines, declared synthetic suites and figure generation'}.get(a.mode,'Native execution of the selected empirical engine and its available accounting checks'))
        if a.mode in EMPIRICAL|{'prepare'}:receipt['input_zip_sha256']=RAW_SHA
        save();print(json.dumps({'status':receipt['status'],'mode':a.mode,'empirical_reproduction':receipt['empirical_reproduction']}))
    except Exception as e:
        receipt.update(status='FAILED',reason=str(e));save();raise

if __name__=='__main__':main()
