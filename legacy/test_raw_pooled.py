#!/usr/bin/env python3
"""Fail-closed interface tests; no synthetic result counts as empirical evidence."""
from fractions import Fraction
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


adapter = module(ROOT / 'run_raw_pooled.py', 'test_pooled_raw_adapter')
core = module(ROOT / 'pooled_capacity_core.py', 'test_pooled_capacity_core')


class InputFailures(unittest.TestCase):
    def test_wrong_raw_hash_creates_no_output(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            raw, output = root / 'wrong.zip', root / 'output'
            raw.write_bytes(b'not the pinned FAT container')
            with self.assertRaisesRegex(ValueError, 'container SHA-256 mismatch'):
                adapter.run(raw, root / 'missing.py', root / 'missing.json', root / 'core.py', root / 'deletion.py', output)
            self.assertFalse(output.exists())

    def test_nonempty_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            output = root / 'output'
            output.mkdir()
            keep = output / 'keep.txt'
            keep.write_text('retained')
            with self.assertRaisesRegex(ValueError, 'new or empty'):
                adapter.run(root / 'absent.zip', root / 'missing.py', root / 'missing.json', root / 'core.py', root / 'deletion.py', output)
            self.assertEqual(keep.read_text(), 'retained')

    def test_invalid_state_accounting_creates_no_output(self):
        with tempfile.TemporaryDirectory() as name:
            output = Path(name) / 'output'
            with self.assertRaisesRegex(ValueError, 'Invalid state masses'):
                core.analyse([Fraction(1)] * 5, [Fraction(0)] * 5, {}, output, {'microdata_accessed': True})
            self.assertFalse(output.exists())

    def test_wrong_software_hash_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / 'wrong.py'
            path.write_text('raise RuntimeError("must not execute")')
            with self.assertRaisesRegex(ValueError, 'Software SHA-256 mismatch'):
                adapter.load_module(path, 'not_loaded', '0' * 64)


if __name__ == '__main__':
    unittest.main()
