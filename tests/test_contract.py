"""Contract tests: the published JSON must match what web/ expects, and the
chat whitelist must stay in sync with the query engine. A failure here stops
the Action before anything is deployed."""
import json, pathlib, re, unittest

DATA = pathlib.Path(__file__).resolve().parent.parent / "data"
WEB = pathlib.Path(__file__).resolve().parent.parent / "web"

NOTICE_FIELDS = {"id", "employer", "employer_raw", "state", "location", "county",
                 "notice_date", "effective_date", "workers_announced",
                 "workers_missing", "notice_type", "first_seen", "duplicate_of"}
ALLOWED_METRICS = {"notice_count", "workers_announced_sum", "top_employers",
                   "monthly_series", "employer_history", "forecast"}
ALLOWED_FILTERS = {"state", "county", "employer", "notice_type"}
ALLOWED_GROUP_BY = {"month", "state", "notice_type", "employer"}


def load(name):
    return json.loads((DATA / name).read_text())


class TestPublishedArtifacts(unittest.TestCase):
    def test_notices_schema(self):
        j = load("notices.json")
        self.assertEqual(j["schema_version"], 1)
        notices = j["notices"]
        self.assertGreater(len(notices), 1000)
        for n in notices:
            self.assertEqual(set(n), NOTICE_FIELDS)
            self.assertTrue(n["id"] and n["employer"] and n["state"])
            self.assertIsInstance(n["workers_missing"], bool)
            if n["workers_announced"] is not None:
                self.assertIsInstance(n["workers_announced"], int)
            for d in (n["notice_date"], n["effective_date"]):
                if d is not None:
                    self.assertRegex(d, r"^\d{4}-\d{2}-\d{2}$")

    def test_no_visa_fields_anywhere(self):
        # WARN has no H-1B/visa field; nothing may pretend otherwise.
        for n in load("notices.json")["notices"]:
            self.assertTrue(set(n).isdisjoint({"visa", "h1b", "h-1b"}))

    def test_meta_counts_consistent(self):
        meta = load("meta.json")
        notices = load("notices.json")["notices"]
        self.assertEqual(meta["row_counts"]["notices"], len(notices))
        self.assertIn("generated_at", meta["upstream"])
        self.assertEqual(meta["upstream"]["license"], "CC BY 4.0")

    def test_series_shape(self):
        s = load("series.json")
        self.assertIn("national", s)
        for row in s["national"]:
            self.assertRegex(row["month"], r"^\d{4}-\d{2}$")
            self.assertGreaterEqual(row["notices"], 0)
        self.assertIn("economic_context", s)
        self.assertIn(s["economic_context"]["bls"]["status"], ("ok", "unavailable"))

    def test_forecasts_honesty(self):
        f = load("forecasts.json")
        nat = f["national"]["notices"]
        self.assertIn(nat["status"], ("ok", "below_baseline", "insufficient_history", "withheld"))
        if nat["status"] == "ok":
            # must actually beat the baseline it claims to beat
            sn = nat["backtest_scores"]["seasonal_naive"]["h1"]["mae"]
            alt = nat["backtest_scores"]["seasonal_naive_drift"]["h1"]["mae"]
            self.assertLess(alt, sn)
            for p in nat["points"]:
                self.assertLessEqual(p["lower_80"], p["point"])
                self.assertLessEqual(p["point"], p["upper_80"])
                self.assertTrue(p["trained_on"] if "trained_on" in p else True)
            self.assertIn("trained_on", nat)

    def test_news_metadata_only(self):
        n = load("news.json")
        for a in n["articles"]:
            self.assertEqual(set(a), {"employer", "title", "url", "domain",
                                      "published_date"})
            self.assertTrue(a["url"].startswith("http"))


class TestEconForecastContract(unittest.TestCase):
    """The learned-forecast artifact must stay honest: no lookahead in its own
    records, the publication gate provably applied, intervals ordered."""

    def setUp(self):
        self.j = load("econ_forecast.json")

    def test_schema_and_horizons(self):
        self.assertEqual(self.j["schema_version"], 1)
        self.assertEqual(sorted(self.j["horizons"], key=int), ["1", "2", "3", "4", "5", "6"])
        self.assertTrue(self.j["evaluation"]["pseudo_real_time"])
        self.assertTrue(self.j["evaluation"]["caveats"])
        self.assertNotIn("interpolated_predictor_months", self.j)
        self.assertIn("issue_semantics", self.j)

    def test_publication_gate(self):
        for h, hz in self.j["horizons"].items():
            self.assertIn(hz["status"], ("ok", "no_ml_beat"))
            is_ml = hz["published_model_kind"] == "machine_learning"
            self.assertEqual(hz["status"] == "ok", is_ml)
            sel = hz["metrics"]["selection_2024_2025"]["models"]
            base = hz["strongest_baseline"]["name"]
            if hz["status"] == "ok":
                # the published ML model really did beat the strongest baseline
                self.assertLess(sel[hz["published_model"]]["mae"], sel[base]["mae"])
            for m, d in sel.items():
                self.assertGreaterEqual(d["n"], 12, f"h={h} {m}: too few selection origins")

    def test_no_lookahead_in_backtest_rows(self):
        for h, hz in self.j["horizons"].items():
            h = int(h)
            for r in hz["backtest"]:
                self.assertLess(r["origin"], r["target"])
                oy, om = int(r["origin"][:4]), int(r["origin"][5:7])
                ty, tm = int(r["target"][:4]), int(r["target"][5:7])
                self.assertEqual((ty * 12 + tm) - (oy * 12 + om), h)

    def test_live_forecast_shape(self):
        for h, hz in self.j["horizons"].items():
            live = hz["live"]
            self.assertIsNotNone(live, f"h={h} has no live forecast")
            self.assertLess(self.j["issue_month"], live["target_month"])
            self.assertLessEqual(live["lower_80"], live["point"])
            self.assertLessEqual(live["point"], live["upper_80"])
            self.assertEqual(live["model"], hz["published_model"])
            # intervals are tied to the published model's own selection residuals
            self.assertIn("published model", hz["interval"]["method"])

    def test_holdout_reported_not_reselected(self):
        for h, hz in self.j["horizons"].items():
            hd = hz["holdout_2026"]
            self.assertIn("held_up", hd)
            self.assertGreater(hd["n"], 0)
        # every era reports every model - selection never hides a loser
        for h, hz in self.j["horizons"].items():
            for era in ("sel_2024", "sel_2025", "test_2026"):
                self.assertTrue(hz["metrics"][era]["models"], f"h={h} {era}")


class TestChatContract(unittest.TestCase):
    def test_whitelists_match_web(self):
        js = (WEB / "chat.js").read_text()
        for name, allowed in (("METRICS", ALLOWED_METRICS),
                              ("FILTERS", ALLOWED_FILTERS),
                              ("GROUP_BY", ALLOWED_GROUP_BY)):
            m = re.search(name + r"\s*=\s*new Set\(\[([^\]]*)\]\)", js)
            self.assertIsNotNone(m, f"{name} whitelist missing in chat.js")
            in_js = set(re.findall(r"'([^']+)'", m.group(1)))
            self.assertEqual(in_js, allowed, f"{name} whitelist drifted")


if __name__ == "__main__":
    unittest.main()
