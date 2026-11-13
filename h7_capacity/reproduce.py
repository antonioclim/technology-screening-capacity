"""Build and verify Paper E Table 5 and Figure 3 from pinned H7 aggregates.

Run from the proposed repository root:
  python h7_capacity/reproduce.py --output ../h7_capacity_output
The candidate layout detects sibling frozen_v1.0.0 automatically.

For an isolated overlay, also supply --source-repository PATH_TO_FROZEN_SOFTWARE.
No microdata, downloads, fitted models, publication or release action is used.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
from hashlib import sha256
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

ROOT=Path(__file__).resolve().parent


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    default_source=ROOT.parent/'frozen_v1.0.0' if (ROOT.parent/'frozen_v1.0.0').is_dir() else ROOT.parent
    parser.add_argument('--source-repository',type=Path,default=default_source)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();source=args.source_repository.resolve();out=args.output.resolve()
    if out.exists():parser.error('--output must be a new directory')
    if source==out or source in out.parents or ROOT==out or ROOT in out.parents:
        parser.error('--output must be outside the software and H7 payloads')
    candidate_root=ROOT.parent if source==ROOT.parent/'frozen_v1.0.0' else None
    if candidate_root is not None and (out==candidate_root or candidate_root in out.parents):
        parser.error('--output must be outside the candidate repository')
    provenance=json.loads((ROOT/'INTEGRATION_PROVENANCE.json').read_text())
    for name,pin in provenance['source_scripts_unchanged'].items():
        if sha256((ROOT/name).read_bytes()).hexdigest()!=pin:
            parser.error('Archived H7 derivative source identity differs: '+name)
    for name,pin in provenance['original_support_file_sha256'].items():
        path=source/name
        if not path.is_file() or sha256(path.read_bytes()).hexdigest()!=pin:
            parser.error('Original H7 checker identity differs: '+name)
    for name,pin in provenance['input_hashes'].items():
        path=source/'reported_results/H7'/name
        if not path.is_file() or sha256(path.read_bytes()).hexdigest()!=pin:
            parser.error('Pinned H7 aggregate identity does not match: '+name)
    independent=source/'acquisition/independent/independent_h7.py'
    if not independent.is_file():parser.error('Original independent H7 checker is required in --source-repository')
    lock={line.split('==')[0]:line.split('==')[1] for line in (ROOT/'requirements-complete-linux-py312.txt').read_text().splitlines() if '==' in line}
    packages={};missing=[]
    for name,pin in lock.items():
        try:packages[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:missing.append(name+'=='+pin)
    if missing:parser.error('Missing dependencies: '+', '.join(missing)+'. Install h7_capacity/requirements-complete-linux-py312.txt in a separate Python 3.12 environment.')
    mismatches={name:{'expected':pin,'installed':packages[name]} for name,pin in lock.items() if packages[name]!=pin}
    if mismatches:parser.error('Dependency versions differ from the tested lock: '+json.dumps(mismatches)+'. Use h7_capacity/requirements-complete-linux-py312.txt.')
    out.mkdir(parents=True);(out/'logs').mkdir();derived=out/'derived'
    receipt={'status':'RUNNING','scope':'Pinned H7 aggregate derivation, figure authoring and synthetic numerical checks',
      'started_utc':datetime.now(timezone.utc).isoformat(),'runtime':{'python':platform.python_version(),'platform':platform.platform(),'packages':packages},
      'commands':[],'dependency_lock_matched':True,'models_fitted':0,'microdata_accessed':False,'empirical_reexecution':False,
      'new_public_release_or_deposit':False,'source_repository':str(source),'input_hashes':provenance['input_hashes'],
      'original_support_file_sha256':provenance['original_support_file_sha256'],
      'module_file_sha256':{path.name:sha256(path.read_bytes()).hexdigest() for path in sorted(ROOT.iterdir()) if path.is_file()}}
    def save():
        path=out/'H7_REPRODUCTION_RECEIPT.json';tmp=path.with_suffix('.tmp')
        tmp.write_text(json.dumps(receipt,indent=2)+'\n');os.replace(tmp,path)
    def call(label,arguments):
        cmd=[sys.executable,'-B',*map(str,arguments)]
        env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','MPLCONFIGDIR':str(out/'matplotlib_cache')}
        run=subprocess.run(cmd,cwd=source,env=env,capture_output=True)
        logs={}
        for kind,data in [('stdout',run.stdout),('stderr',run.stderr)]:
            (out/'logs'/f'{label}.{kind}.txt').write_bytes(data)
            logs[kind]={'bytes':len(data),'sha256':sha256(data).hexdigest()}
        receipt['commands'].append({'label':label,'arguments':list(map(str,arguments)),'exit_code':run.returncode,'logs':logs});save()
        if run.returncode:raise RuntimeError(label+' failed; inspect its log')
        print(label+' PASS',flush=True)
    try:
        save()
        input_csv=source/'reported_results/H7/equal_country_policy_summaries.csv'
        call('synthetic_primitives',[independent,'--synthetic','--output',out/'H7_INDEPENDENT_PRIMITIVES.json'])
        call('aggregate_contracts',[ROOT/'check_aggregate_contracts.py','--source-repository',source,'--report',out/'H7_AGGREGATE_CONTRACTS.json','--cost-table',out/'H7_RAW_COST_SENSITIVITY.csv'])
        call('build_capacity',[ROOT/'build_h7_capacity.py','--input',input_csv,'--output',derived])
        call('verify_capacity',[ROOT/'verify_h7_capacity.py','--input',input_csv,'--derived',derived,'--report',out/'H7_CAPACITY_QA.json'])
        checks=[]
        for relative,pin in provenance['expected_rebuild_hashes'].items():
            digest=sha256((out/relative).read_bytes()).hexdigest()
            checks.append({'path':relative,'sha256':digest,'expected_sha256':pin,'byte_identical':digest==pin})
        receipt['deterministic_rebuild_checks']=checks
        if not all(x['byte_identical'] for x in checks):raise ValueError('A deterministic CSV/PNG differs from the archived derivative')
        primitive=json.loads((out/'H7_INDEPENDENT_PRIMITIVES.json').read_text())
        aggregate=json.loads((out/'H7_AGGREGATE_CONTRACTS.json').read_text())
        capacity=json.loads((out/'H7_CAPACITY_QA.json').read_text())
        receipt.update(status='PASS',completed_utc=datetime.now(timezone.utc).isoformat(),
            independent_scalar_comparisons=primitive['independent_scalar_comparisons'],
            plateau_regression_trials=primitive['plateau_regression_trials'],
            aggregate_numeric_comparisons=aggregate['total_numeric_comparisons'],
            affine_upper_hull_comparisons=capacity['table_checks']['independent_upper_hull_comparisons'],
            plotted_coordinate_checks=capacity['artwork_checks']['svg_coordinate_checks'])
        save();print(json.dumps({key:receipt[key] for key in ['status','independent_scalar_comparisons','aggregate_numeric_comparisons','affine_upper_hull_comparisons','plotted_coordinate_checks','models_fitted','microdata_accessed']},indent=2))
    except Exception as error:
        receipt.update(status='FAILED',reason=str(error));save();raise

if __name__=='__main__':main()
