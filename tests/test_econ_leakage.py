"""Future-influence proof for the econ forecast: reruns the pipeline's own
lineage + future-perturbation self-test against the committed snapshots.
Requires data/snapshots/econ (produced by ingest/fetch_econ.py, which the
workflow runs before tests)."""
import pathlib, sys, unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "ingest"))
import econ_forecast as E  # noqa: E402


class TestNoFutureInfluence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.S = {sid: E.load_series(sid) for sid in E.LAGS}
        if not all(cls.S.values()):
            raise unittest.SkipTest("econ snapshots not present")

    def test_selftest_origins(self):
        for m in ("2015-06", "2020-04", "2024-06", "2025-12", "2026-06"):
            for h in (1, 3, 6):
                E.perturbation_check(self.S, E.mi(m), h)  # raises on any leak

    def test_lineage_all_recent_origins(self):
        t = E.mi("2024-01")
        while t <= E.mi("2026-08"):
            for h in E.HORIZONS:
                E.lineage_check(self.S, t, h)
            t += 3


if __name__ == "__main__":
    unittest.main()
