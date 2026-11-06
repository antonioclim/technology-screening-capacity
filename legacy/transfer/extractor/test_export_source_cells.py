"""Implementation checks on artificial rows and archived aggregate references only."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

import export_source_cells as ex


class ExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frozen = ex.load_frozen_executor(ex.ROOT / "vendor")

    def frame(self, rows):
        data = []
        for k, (source, state, sales, employment, weight) in enumerate(rows, 1):
            data.append({"firmid": k, "country": source, "e6a": sales,
                         "s7": employment, "base_wt": weight,
                         **{f"ib9b{i}": int(i == state) for i in range(1, 6)}})
        return self.frozen.prepare_full_frame(pd.DataFrame(data))

    def test_inclusive_quantile_ties(self):
        d = self.frame([("Bangladesh", 1, 1, 1, 1), ("Bangladesh", 2, 1, 1, 1),
                        ("Bangladesh", 3, 3, 1, 1), ("Bangladesh", 4, 4, 1, 1),
                        ("Bangladesh", 5, 9, 1, 1)])
        got = ex.add_event(d, self.frozen)
        self.assertEqual(got.H1_EVENT.tolist(), [True, True, False, False, False])
        self.assertAlmostEqual(float(got.loc[got.H1_EVENT, "W_PRIMARY_SOURCE_MEAN1"].sum() /
                                     got.W_PRIMARY_SOURCE_MEAN1.sum()), .4)

    def test_archived_float_boundary_edge_is_preserved_and_exposed(self):
        d = self.frame([("Bangladesh", 1, 1, 1, 1), ("Bangladesh", 2, 1, 1, 1),
                        ("Bangladesh", 5, 9, 1, 8)])
        got = ex.add_event(d, self.frozen)
        # Exact arithmetic would stop at the first tied outcome. The unchanged
        # archived floating-point function advances on this constructed edge.
        self.assertEqual(got.H1_EVENT.tolist(), [True, True, True])

    def test_weight_scale_diagnostic_flags_edge_without_replacing_labels(self):
        d = self.frame([("Bangladesh", 1, 1, 1, 1), ("Bangladesh", 2, 1, 1, 1),
                        ("Bangladesh", 5, 9, 1, 8)])
        got = ex.add_event(d, self.frozen)
        before = got.H1_EVENT.copy()
        result = ex.quantile_scale_diagnostics(got, self.frozen)[0]
        self.assertTrue(result["finite_precision_scale_difference_flag"])
        self.assertEqual(result["event_membership_difference_n"], 1)
        self.assertAlmostEqual(result["event_membership_difference_normalised_weight_mass"], 2.4)
        self.assertEqual(result["raw_weight_scale_threshold"], 0.)
        self.assertGreater(result["frozen_normalised_weight_threshold"], 0.)
        self.assertTrue(result["frozen_labels_preserved"])
        self.assertTrue(got.H1_EVENT.equals(before))

    def test_weight_scale_diagnostic_equal_weight_case(self):
        d = self.frame([("Bangladesh", 1, i + 1, 1, 7) for i in range(5)])
        got = ex.add_event(d, self.frozen)
        result = ex.quantile_scale_diagnostics(got, self.frozen)[0]
        self.assertFalse(result["finite_precision_scale_difference_flag"])
        self.assertEqual(result["event_membership_difference_n"], 0)
        self.assertEqual(result["frozen_event_weighted_share"], .2)

    def test_source_mean_one_and_hand_aggregate(self):
        d = self.frame([("Bangladesh", 1, 1, 1, 1), ("Bangladesh", 2, 4, 1, 3),
                        ("Brazil", 1, 2, 1, 7), ("Brazil", 5, 8, 1, 7)])
        got = ex.add_event(d, self.frozen)
        self.assertEqual(got.groupby("country").W_PRIMARY_SOURCE_MEAN1.sum().to_dict(),
                         {"Bangladesh": 2., "Brazil": 2.})
        cells = ex.aggregate(got)
        self.assertEqual(len(cells), 10)
        a1 = next(r for r in cells if r["source"] == "Bangladesh" and r["state"] == 1)
        a2 = next(r for r in cells if r["source"] == "Bangladesh" and r["state"] == 2)
        self.assertEqual((a1["n"], a1["n_cases"], a1["weight_mass"], a1["case_mass"]),
                         (1, 1, "0.500000000000000000", "0.500000000000000000"))
        self.assertEqual((a2["n_cases"], a2["weight_mass"], a2["case_mass"]),
                         (0, "1.500000000000000000", "0.000000000000000000"))

    def test_eligibility_mask_and_explicit_zero_state(self):
        d = self.frame([("Bangladesh", 1, 1, 1, 1), ("Bangladesh", 2, 0, 1, 1),
                        ("Bangladesh", 3, 1, 0, 1), ("Bangladesh", 4, 1, 1, 0),
                        ("Bangladesh", 0, 1, 1, 1), ("Poland", 1, 1, 1, 1)])
        sample = self.frozen.build_sample(d, "PRIMARY_S60_N200")
        self.assertEqual(sample.firmid.tolist(), [1])
        cells = ex.aggregate(ex.add_event(sample, self.frozen))
        self.assertEqual(len(cells), 5)
        for row in cells[1:]:
            self.assertEqual((row["n"], row["n_cases"], float(row["weight_mass"]),
                              float(row["case_mass"])), (0, 0, 0., 0.))

    def test_membership_digest_is_order_invariant(self):
        d = self.frame([("Brazil", 5, 4, 1, 1), ("Bangladesh", 1, 1, 1, 1)])
        expected = hashlib.sha256(b"Bangladesh|2\nBrazil|1\n").hexdigest()
        self.assertEqual(self.frozen.sample_fingerprint(d), expected)
        self.assertEqual(self.frozen.sample_fingerprint(d.iloc[::-1]), expected)

    def test_wrong_raw_hash_refused_before_csv_or_zip_parse(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "not-a-zip.zip"
            raw.write_bytes(b"not a zip or CSV")
            with self.assertRaisesRegex(RuntimeError, "container SHA-256 mismatch"):
                self.frozen.load_real_microdata(raw)

    def test_failed_export_writes_no_success_or_output_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, target = Path(tmp) / "bad.zip", Path(tmp) / "result"
            raw.write_bytes(b"bad input")
            protocol = ex.ROOT.parent / "protocol/H1_PROTOCOL.json"
            with self.assertRaisesRegex(RuntimeError, "container SHA-256 mismatch"):
                ex.export(raw, ex.ROOT / "vendor", protocol, target,
                          ex.ROOT / "vendor/aggregate_reference")
            self.assertFalse(target.exists())

    def test_archived_aggregate_reference_gate_and_parity(self):
        refs = ex.load_references(ex.ROOT / "vendor/aggregate_reference")
        rows = []
        for ref in refs["X06"]:
            if ref["group_id"] not in {f"state_{i}" for i in range(1, 6)}:
                continue
            weight = float(ref["weighted_total"])
            rows.append({"state": int(ref["group_id"][-1]), "n": int(ref["unweighted_n"]),
                         "weight_mass": weight,
                         "case_mass": weight * float(ref["weighted_low_performance_share"])})
        checks = ex.check_parity(rows, refs)
        self.assertGreaterEqual(len(checks), 20)
        self.assertTrue(all(r["passed"] for r in checks))
        rows[0]["case_mass"] += 1
        with self.assertRaisesRegex(ValueError, "Frozen aggregate parity failed"):
            ex.check_parity(rows, refs)

    def test_protocol_and_vendor_pins(self):
        self.assertEqual(ex.digest(ex.ROOT.parent / "protocol/H1_PROTOCOL.json"), ex.PROTOCOL_SHA)
        self.assertEqual(ex.digest(ex.ROOT / "vendor/upstream/run_e4_frozen_analysis_v1.0.2.py"), ex.EXECUTOR_SHA)


if __name__ == "__main__":
    unittest.main(verbosity=2)
