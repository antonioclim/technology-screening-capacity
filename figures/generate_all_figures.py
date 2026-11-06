"""Regenerate all six current Paper E figures from eight aggregate CSV files.

This entry point uses Python/Matplotlib sources preserved with the package.
It performs no empirical model fitting and requires no microdata or network.
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
import tempfile

HERE = Path(__file__).resolve().parent


def atomic(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            if stream.write(data) != len(data):
                raise OSError('Short output write')
            stream.flush()
            os.fsync(stream.fileno())
        if temporary.read_bytes() != data:
            raise OSError('Temporary output readback differs')
        os.replace(temporary, path)
        if path.read_bytes() != data:
            raise OSError('Final output readback differs')
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def execute(arguments, receipt: Path):
    result = subprocess.run([sys.executable, '-B', *map(str, arguments)],
                            cwd=HERE, text=True, capture_output=True,
                            env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
    atomic(receipt.with_suffix('.stdout.txt'), result.stdout.encode())
    atomic(receipt.with_suffix('.stderr.txt'), result.stderr.encode())
    if result.returncode:
        raise RuntimeError(f'Plot command failed with exit code {result.returncode}; see {receipt.name} logs')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True,
                        help='New output directory outside this figure package')
    parser.add_argument('--inputs', type=Path, default=HERE/'inputs',
                        help='Pinned aggregate CSV root with main, pooled, transfer and acquisition directories')
    args = parser.parse_args()
    output = args.output.resolve()
    inputs = args.inputs.resolve()
    if output.exists():
        parser.error('--output must be a new directory')
    if output == HERE or HERE in output.parents:
        parser.error('--output must be outside this reference figure package')
    pins = json.loads((HERE/'INPUT_IDENTITIES.json').read_text())
    input_receipts = {}
    for relative, expected in pins.items():
        source = inputs/relative
        data = source.read_bytes()
        observed = sha256(data).hexdigest()
        if observed != expected['sha256']:
            raise ValueError('Input identity differs: '+relative)
        input_receipts[relative] = {'sha256': observed, 'bytes': len(data)}
    output.mkdir(parents=True)
    try:
        with tempfile.TemporaryDirectory(prefix='papere-figure-build-') as staging:
            stage = Path(staging)
            execute([HERE/'sources/plot_main_figures.py', '--inputs', inputs/'main',
                     '--output', stage/'main'], output/'receipts/main')
            execute([HERE/'sources/plot_pooled.py', '--results', inputs/'pooled',
                     '--output', stage/'pooled'], output/'receipts/pooled')
            execute([HERE/'sources/plot_supplement_transfer.py',
                     '--csv', inputs/'transfer/within_source_quota_50_percent.csv',
                     '--output-dir', stage/'transfer'], output/'receipts/transfer')
            execute([HERE/'sources/plot_acquisition.py', '--inputs', inputs/'acquisition',
                     '--output', stage/'acquisition'], output/'receipts/acquisition')
            names = {'Figure_1': stage/'main/Figure_1',
                     'Figure_2': stage/'main/Figure_2',
                     'Figure_S1': stage/'transfer/Figure_S1',
                     'Figure_S2': stage/'pooled/FIGURE_CAPACITY',
                     'Figure_S3': stage/'pooled/FIGURE_LIST_COMPOSITION',
                     'Figure_S4': stage/'acquisition/Figure_S4'}
            artifacts = {}
            for current, original in names.items():
                for extension in ['pdf', 'svg', 'png']:
                    data = original.with_suffix('.'+extension).read_bytes()
                    target = output/extension/(current+'.'+extension)
                    atomic(target, data)
                    artifacts[str(target.relative_to(output))] = {
                        'sha256': sha256(data).hexdigest(), 'bytes': len(data)}
            for source, name in [(stage/'main/FIGURE_BUILD_QA.json','main.json'),
                                 (stage/'pooled/PLOT_WRITE_QA.json','pooled.json'),
                                 (stage/'transfer/FIGURE_S1_QA.json','transfer.json'),
                                 (stage/'acquisition/FIGURE_S4_QA.json','acquisition.json')]:
                atomic(output/'receipts'/name, source.read_bytes())
        result = {'status': 'PASS', 'scope': 'CSV_TO_FIGURE_GENERATION_ONLY',
                  'empirical_reproduction': False, 'microdata_accessed': False,
                  'created_utc': datetime.now(timezone.utc).isoformat(),
                  'python': platform.python_version(), 'platform': platform.platform(),
                  'inputs': input_receipts, 'figures': list(names), 'artifacts': artifacts,
                  'numbering': 'Current main 1/2; source transfer S1; original pooled yield S2 and composition S3; selective acquisition and fixed-sector allocation S4',
                  'limits': 'The native environment was Linux/Python. This is not a native Windows or portal check.'}
        atomic(output/'FIGURE_REPLAY_QA.json', (json.dumps(result, indent=2)+'\n').encode())
        print(json.dumps(result, indent=2))
    except Exception as exc:
        atomic(output/'FIGURE_FAILURE.json',
               (json.dumps({'status':'FAIL','type':type(exc).__name__,'message':str(exc)},indent=2)+'\n').encode())
        raise


if __name__ == '__main__':
    main()
