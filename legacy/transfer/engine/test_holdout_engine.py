"""Synthetic and hand-computable software tests; no empirical validation."""
from fractions import Fraction as F
import json
from pathlib import Path
import tempfile
import unittest

import holdout_engine as h

PROTOCOL = "a" * 64


def cells(events=(8, 6, 4, 2, 1), n=(10, 10, 10, 10, 10)):
    return tuple(h.Cell(ni, ei, F(ni), F(ei)) for ni, ei in zip(n, events))


def fixture():
    return {"India": cells(), "India_Wave2_New": cells((3, 7, 1, 5, 1)),
            "Kenya": cells((2, 4, 7, 1, 3)), "Brazil": cells((6, 1, 8, 2, 5))}


def countries(data):
    return {s: "India" if s.startswith("India") else s for s in data}


class HoldoutTests(unittest.TestCase):
    def test_hand_computable_five_vs_digital(self):
        # q=.50 contacts 25 of50: five contacts (10,10,5,0,0), events16.
        c = cells()
        five = h.evaluate_source(c, (1, 2, 3, 4), F(".50"))
        self.assertEqual(five["contact_mass"], 25)
        self.assertEqual(five["case_mass"], 16)
        self.assertEqual(five["yield"], 64)
        self.assertEqual(five["state_shares_percent"], (40, 40, 20, 0, 0))
        digital = h.evaluate_source(c, (1,), F(".50"))
        # Digital remainder15 uniformly contacts3.75 of each other state.
        self.assertEqual(digital["state_contacts"], (10, F(15, 4), F(15, 4), F(15, 4), F(15, 4)))
        self.assertEqual(digital["case_mass"], F(103, 8))
        self.assertEqual(digital["yield"], F(103, 2))

    def test_all_policies_fill_all_quotas(self):
        for c in fixture().values():
            for cuts in (*h.THREE_BLOCKS, *h.FIXED.values()):
                for q in h.QUOTAS:
                    r = h.evaluate_source(c, cuts, q)
                    self.assertEqual(r["contact_mass"], 50*q)
                    self.assertEqual(sum(r["state_shares_percent"]), 100)

    def test_marginal_block_uniform(self):
        r = h.evaluate_source(cells(), (1, 4), F(".50"))
        self.assertEqual(r["state_contacts"], (10, 5, 5, 5, 0))

    def test_full_quota_all_policies_equal(self):
        reference = h.evaluate_source(cells(), (), F(1))
        for cuts in (*h.THREE_BLOCKS, *h.FIXED.values()):
            self.assertEqual(h.evaluate_source(cells(), cuts, F(1)), reference)

    def test_absent_state_explicit_zero_supported(self):
        data = {"A": cells((8, 6, 0, 2, 1), (10, 10, 0, 10, 10))}
        self.assertEqual(h.parse_csv(h.serialise_cells(data)), data)
        r = h.evaluate_source(data["A"], (1, 2, 3, 4), F(".5"))
        self.assertEqual(r["state_contacts"][2], 0)

    def test_missing_state_rejected(self):
        data = h.serialise_cells({"A": cells()}).decode().splitlines()
        with self.assertRaisesRegex(ValueError, "all five"):
            h.parse_csv(("\n".join(data[:-1])+"\n").encode())

    def test_duplicate_state_rejected(self):
        data = h.serialise_cells({"A": cells()})
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            h.parse_csv(data+data.splitlines(keepends=True)[1])

    def test_invalid_and_nonfinite_mass_rejected(self):
        data = h.serialise_cells({"A": cells()})
        for bad in (b"nan", b"inf", b"-10", b"1/2"):
            with self.assertRaises(ValueError):
                h.parse_csv(data.replace(b"10.000000000000000000000000000000000000", bad, 1))

    def test_bad_counts_and_weight_normalisation_rejected(self):
        bad = list(cells())
        bad[0] = h.Cell(10, 11, F(10), F(11))
        with self.assertRaisesRegex(ValueError, "Infeasible"):
            h.validate({"A": tuple(bad)})
        bad[0] = h.Cell(10, 8, F(11), F(8))
        with self.assertRaisesRegex(ValueError, "normalised"):
            h.validate({"A": tuple(bad)})

    def test_exact_tie_lexical(self):
        # Same event fraction in every state makes every candidate exactly equal.
        chosen, obj = h.training_selection({"A": cells((2, 2, 2, 2, 2))})
        self.assertEqual(chosen, (1, 2))
        self.assertTrue(all(o[0] == 0 for o in obj.values()))

    def test_signed_negative_loss_retained(self):
        c = cells((0, 0, 0, 10, 10))
        five = h.evaluate_source(c, (1, 2, 3, 4), F(".5"))["yield"]
        candidate = h.evaluate_source(c, (1, 2), F(".5"))["yield"]
        self.assertLess(five-candidate, 0)

    def test_training_source_order_invariance(self):
        data = fixture()
        reverse = dict(reversed(list(data.items())))
        self.assertEqual(h.fit(data, countries(data), PROTOCOL),
                         h.fit(reverse, countries(reverse), PROTOCOL))

    def test_changing_heldout_labels_never_changes_its_lock(self):
        original = fixture()
        altered = {**original, "Kenya": cells((9, 9, 1, 1, 9))}
        a = h.crossvalidate(original, countries(original), PROTOCOL)
        b = h.crossvalidate(altered, countries(altered), PROTOCOL)
        lock_a = next(f["lock"] for f in a["folds"] if f["held_out_unit"] == "Kenya")
        lock_b = next(f["lock"] for f in b["folds"] if f["held_out_unit"] == "Kenya")
        self.assertEqual(lock_a, lock_b)
        results_a = [r for r in a["results"] if r["source"] == "Kenya"]
        results_b = [r for r in b["results"] if r["source"] == "Kenya"]
        self.assertNotEqual(results_a, results_b)

    def test_source_overlap_rejected(self):
        data = {"A": cells()}
        lock = h.fit(data, {"A": "Alpha"}, PROTOCOL)
        with self.assertRaisesRegex(ValueError, "sources overlap"):
            h.score(lock, data, {"A": "Alpha"}, PROTOCOL)

    def test_country_overlap_rejected(self):
        lock = h.fit({"India": cells()}, {"India": "India"}, PROTOCOL)
        with self.assertRaisesRegex(ValueError, "countries overlap"):
            h.score(lock, {"India_Wave2_New": cells()}, {"India_Wave2_New": "India"},
                    PROTOCOL, country_disjoint=True)

    def test_leave_country_out_removes_both_india_sources(self):
        data = fixture()
        report = h.crossvalidate(data, countries(data), PROTOCOL, unit="country")
        fold = next(f for f in report["folds"] if f["held_out_unit"] == "India")
        self.assertEqual(fold["held_out_sources"], ["India", "India_Wave2_New"])
        self.assertEqual(fold["lock"]["training_sources"], ["Brazil", "Kenya"])

    def test_lock_digest_code_and_protocol_mismatch_rejected(self):
        lock = h.fit({"A": cells()}, {"A": "Alpha"}, PROTOCOL)
        with self.assertRaisesRegex(ValueError, "Lock digest"):
            h.verify_lock({**lock, "selected_cuts": [3, 4]}, PROTOCOL)
        without = {k: v for k, v in lock.items() if k != "lock_sha256"}
        for key, message in (("code_sha256", "code"), ("algorithm_sha256", "Algorithm")):
            changed = h.seal_lock({**without, key: "0"*64})
            with self.assertRaisesRegex(ValueError, message):
                h.verify_lock(changed, PROTOCOL)
        with self.assertRaisesRegex(ValueError, "Protocol"):
            h.verify_lock(lock, "b"*64)

    def test_synthetic_empirical_scope_mismatch_rejected(self):
        lock = h.fit({"A": cells()}, {"A": "A"}, PROTOCOL)
        with self.assertRaisesRegex(ValueError, "scopes differ"):
            h.score(lock, {"B": cells()}, {"B": "B"}, PROTOCOL, evidence_type="empirical")

    def test_country_summary_equal_country_not_equal_source(self):
        data = fixture()
        report = h.crossvalidate(data, countries(data), PROTOCOL, unit="country")
        rows = [r for r in report["results"] if r["quota"] == "0.50" and r["policy"] == "digital"]
        by_country = {}
        for r in rows:
            by_country.setdefault(r["country"], []).append(r["cases_per_100_expected_contacts"])
        expected = sum(sum(v)/len(v) for v in by_country.values())/len(by_country)
        summary = next(r for r in report["summary"] if r["quota"] == "0.50"
                       and r["policy"] == "digital"
                       and r["aggregation"] == "equal_country_within_country_equal_source")
        self.assertEqual(summary["cases_per_100_expected_contacts"], expected)

    def test_pooled_recall_uses_events_not_contacts(self):
        data = fixture()
        report = h.crossvalidate(data, countries(data), PROTOCOL)
        rows = [r for r in report["results"] if r["quota"] == "0.50" and r["policy"] == "digital"]
        pooled = next(r for r in report["summary"] if r["quota"] == "0.50"
                      and r["policy"] == "digital" and r["aggregation"] == "expected_contact_weight_pooled")
        expected = 100*sum(r["expected_weighted_cases"] for r in rows)/sum(r["eligible_weighted_event_mass"] for r in rows)
        self.assertEqual(pooled["event_recall_percent"], expected)

    def test_zero_events_recall_undefined_yield_zero(self):
        r = h.evaluate_source(cells((0, 0, 0, 0, 0)), (), F(".5"))
        self.assertIsNone(r["recall_percent"])
        self.assertEqual(r["yield"], 0)

    def test_manifest_digest_and_provenance_required(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload = h.serialise_cells({"A": cells()})
            (root/"cells.csv").write_bytes(payload)
            manifest = {"input_sha256": h.digest(payload), "evidence_type": "synthetic",
                        "sources": {"A": "A"}, "provenance": "Artificial data", "prior_exposure": "None empirical"}
            path = root/"manifest.json"
            path.write_text(json.dumps(manifest))
            loaded, _, _ = h.load_input(root/"cells.csv", path)
            self.assertEqual(loaded, {"A": cells()})
            manifest["input_sha256"] = "0"*64
            path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "digest"):
                h.load_input(root/"cells.csv", path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
