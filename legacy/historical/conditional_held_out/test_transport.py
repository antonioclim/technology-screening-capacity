import json
from fractions import Fraction as F
from pathlib import Path
import subprocess
import sys
import unittest

from run_transport import (
    BINARY, FIXED, QUOTAS, Cell, choose_binary, contact_cases,
    evaluate, parse_csv, synthetic_fixture, validate,
)


class TransportTests(unittest.TestCase):
    def test_capacity_with_absent_priority_state(self):
        cells = (
            Cell(0, 0, F(0), F(0)),
            Cell(20, 10, F(20), F(10)),
            Cell(10, 0, F(10), F(0)),
            Cell(10, 0, F(10), F(0)),
            Cell(10, 0, F(10), F(0)),
        )
        self.assertEqual(contact_cases(cells, FIXED["five_states"], F(".20")), (F(10), F(5)))
        self.assertEqual(contact_cases(cells, FIXED["digital"], F(".20")), (F(10), F(2)))
        for policy in FIXED.values():
            self.assertEqual(contact_cases(cells, policy, F(1)), (F(50), F(10)))

    def test_changing_holdout_labels_cannot_change_fit(self):
        source = synthetic_fixture()
        before = [
            {key: [contact_cases(cells, cut, q) for q in QUOTAS] for key, cut in BINARY.items()}
            for cells in source
        ]
        changed = [dict(row) for row in before]
        changed[0] = {
            key: [(contact, contact if key == "integrated" else F(0)) for contact, _ in scores]
            for key, scores in changed[0].items()
        }
        self.assertEqual(choose_binary(before, 0), choose_binary(changed, 0))

    def test_exact_tie_uses_earliest_boundary(self):
        identical = {key: [(q, q / 4) for q in QUOTAS] for key in BINARY}
        self.assertEqual(choose_binary([identical] * 3, 1), "digital")

    def test_synthetic_output_contains_only_aggregated_metrics(self):
        report = evaluate(synthetic_fixture(), synthetic=True)
        self.assertEqual(report["scope"], "SYNTHETIC_TEST_ONLY")
        self.assertEqual(report["outcome_scope"], "Generated test labels")
        self.assertEqual(report["source_count"], 12)
        self.assertEqual(len(report["results"]), 28)
        for row in report["results"]:
            self.assertEqual(set(row), {
                "quota", "policy", "pooled_cases_per_100_expected_contacts",
                "median_source_paired_delta_vs_digital",
            })
            self.assertTrue(0 <= row["pooled_cases_per_100_expected_contacts"] <= 100)

    def test_empirical_route_rejects_fixture_population_size(self):
        with self.assertRaisesRegex(ValueError, "frozen sample size"):
            validate(synthetic_fixture(), synthetic=False)

    def test_pool_floor_is_checked_even_when_sources_pass(self):
        sources = synthetic_fixture()
        sources = [
            tuple(Cell(c.n, 0, c.weight, F(0)) if i == 4 else c
                  for i, c in enumerate(cells))
            for cells in sources
        ]
        with self.assertRaisesRegex(ValueError, "pooled state"):
            validate(sources, synthetic=True)

    def test_duplicate_and_missing_source_state_rejected(self):
        header = b"source,state,n,n_cases,weight_mass,case_mass\n"
        row = b"x,1,100,20,100,20\n"
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            parse_csv(header + row + row)
        with self.assertRaisesRegex(ValueError, "five explicit"):
            parse_csv(header + row)

    def test_cli_checks_attestation_before_open(self):
        script = Path(__file__).with_name("run_transport.py")
        gated = subprocess.run(
            [sys.executable, str(script), "--input", "/path/does/not/exist"],
            capture_output=True, text=True,
        )
        self.assertEqual(gated.returncode, 2)
        self.assertIn("requires --confirm-authorized-aggregates", gated.stderr)
        ok = subprocess.run(
            [sys.executable, str(script), "--synthetic"],
            capture_output=True, text=True, check=True,
        )
        self.assertEqual(json.loads(ok.stdout)["scope"], "SYNTHETIC_TEST_ONLY")


if __name__ == "__main__":
    unittest.main()
