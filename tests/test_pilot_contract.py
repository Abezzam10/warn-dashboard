"""Contract: the dashboard's pilot artifact (web/ca-pilot.json) must stay in
sync with the verified analysis artifact (analysis/results_final.json) and
must keep the corrected method wording. A failure here stops the deploy."""
import json, pathlib, unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
PILOT = json.loads((ROOT / "web" / "ca-pilot.json").read_text())
RESULTS = json.loads((ROOT / "analysis" / "results_final.json").read_text())


class TestPilotArtifact(unittest.TestCase):
    def test_months_match_analysis(self):
        self.assertEqual(set(PILOT["months"]), {"2026-08", "2026-09", "2026-10"})
        for m, t in RESULTS["targets"].items():
            p = PILOT["months"][m]
            for k in ("rows", "employees", "z_rows", "z_emps", "distinct_filings", "seasonal"):
                self.assertEqual(p[k], t[k], f"{m}.{k}")

    def test_reference_window_fixed_and_consistent(self):
        w = PILOT["reference_window"]
        self.assertEqual((w["start"], w["end"]), ("2024-07", "2026-06"))
        base = RESULTS["targets"]["2026-08"]
        self.assertEqual(w["notices_median"], base["base_rows"][0])
        self.assertEqual(w["notices_mad"], base["base_rows"][1])
        self.assertEqual(w["employees_median"], base["base_emps"][0])
        self.assertEqual(w["employees_mad"], base["base_emps"][1])
        # Same fixed window for all three target months, never rolling.
        for t in RESULTS["targets"].values():
            self.assertEqual(t["base_rows"], base["base_rows"])
            self.assertEqual(t["base_emps"], base["base_emps"])

    def test_wording_keeps_caveats(self):
        self.assertIn("fixed 24-month reference window", PILOT["method"])
        self.assertIn("same window for all three months", PILOT["method"])
        self.assertIn("exploratory heuristic cutoff", PILOT["method"])
        self.assertIn("No calibrated false-alarm rate", PILOT["method"])
        self.assertIn("22 of 23", PILOT["units"])
        self.assertIn("3-position uncertainty", PILOT["units"])
        self.assertIn("not a forecast", PILOT["limits"])
        self.assertIn("cannot confirm or rule out an AI link", PILOT["limits"])

    def test_series_and_partial_month(self):
        for m, v in RESULTS["series"].items():
            if m >= "2024-07":
                self.assertEqual(PILOT["series"][m], v, f"series {m}")
        self.assertEqual(PILOT["partial"]["month"], "2026-11")
        self.assertEqual(PILOT["series"]["2026-11"], [14, 562])

    def test_lag_and_concentration(self):
        self.assertEqual(PILOT["lag"], RESULTS["lag"])
        self.assertEqual(PILOT["months"]["2026-10"]["concentration"], RESULTS["october_top"])
        self.assertNotIn("concentration", PILOT["months"]["2026-08"])
        self.assertNotIn("concentration", PILOT["months"]["2026-09"])

    def test_freshness_metadata(self):
        s = PILOT["source"]
        self.assertEqual(s["data_through"], "2026-11-04")
        self.assertEqual(s["retrieved"], "2026-11-08")
        self.assertIn("edd.ca.gov", s["url"])
        self.assertEqual(PILOT["schema_version"], 1)


if __name__ == "__main__":
    unittest.main()
