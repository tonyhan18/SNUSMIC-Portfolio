from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path
import unittest

from scripts.backtest.us_index_mtf_decay import (
    DailyBar,
    SignalRow,
    run_backtest,
)


def row(
    day: int,
    *,
    open_: float = 100.0,
    close: float = 100.0,
    d_close_under: bool = False,
    d_cross_down: bool = False,
    d_cross_up: bool = False,
    two_close_under: bool = False,
    two_cross_down: bool = False,
    two_cross_up: bool = False,
    week_close_under: bool = False,
    week_cross_down: bool = False,
    week_cross_up: bool = False,
    weekly_alive: bool = True,
) -> SignalRow:
    date = dt.date(2020, 1, 1) + dt.timedelta(days=day)
    return SignalRow(
        bar=DailyBar(date, open_, max(open_, close), min(open_, close), close, 1_000_000),
        d_close_under=d_close_under,
        d_cross_down=d_cross_down,
        d_cross_up=d_cross_up,
        two_close_under=two_close_under,
        two_cross_down=two_cross_down,
        two_cross_up=two_cross_up,
        week_close_under=week_close_under,
        week_cross_down=week_cross_down,
        week_cross_up=week_cross_up,
        weekly_alive=weekly_alive,
    )


class MtfDecayBacktestTest(unittest.TestCase):
    def test_six_exits_decay_from_remaining_position(self) -> None:
        rows = [row(0)]
        signals = [
            {"d_close_under": True},
            {},
            {"d_cross_down": True},
            {},
            {"two_close_under": True},
            {},
            {"two_cross_down": True},
            {},
            {"week_close_under": True},
            {},
            {"week_cross_down": True},
            {},
        ]
        for i, sig in enumerate(signals, start=1):
            rows.append(row(i, **sig))

        result = run_backtest(rows, start_date=rows[0].bar.date, commission_rate=0.0, slippage_per_share=0.0)
        exits = [event for event in result["events"] if event["action"].startswith("EXIT_")]
        self.assertEqual([e["stage_after"] for e in exits], [1, 2, 3, 4, 5, 6])
        self.assertEqual([round(e["position_after_pct"], 2) for e in exits], [80.0, 64.0, 51.2, 40.96, 20.48, 10.24])

    def test_ineligible_cross_is_not_latched(self) -> None:
        rows = [
            row(0),
            row(1, d_close_under=True, d_cross_down=True),
            row(2),  # stage 1 fills; the earlier stage-2 cross must not be reused
            row(3),
            row(4),
        ]
        result = run_backtest(rows, start_date=rows[0].bar.date, commission_rate=0.0, slippage_per_share=0.0)
        exits = [event for event in result["events"] if event["action"].startswith("EXIT_")]
        self.assertEqual(len(exits), 1)
        self.assertEqual(exits[0]["stage_after"], 1)

    def test_reentry_after_stage_one_uses_fresh_daily_cross(self) -> None:
        rows = [
            row(0),
            row(1, d_close_under=True),
            row(2),
            row(3, d_cross_up=True, weekly_alive=True),
            row(4, open_=90.0, close=91.0),
        ]
        result = run_backtest(rows, start_date=rows[0].bar.date, commission_rate=0.0, slippage_per_share=0.0)
        actions = [event["action"] for event in result["events"]]
        self.assertEqual(actions, ["INITIAL_BUY", "EXIT_1", "REENTER"])
        self.assertEqual(result["final_stage"], 0)
        self.assertAlmostEqual(result["final_exposure_pct"], 100.0, places=6)

    def test_reentry_after_stage_three_requires_two_day_cross(self) -> None:
        rows = [
            row(0),
            row(1, d_close_under=True), row(2),
            row(3, d_cross_down=True), row(4),
            row(5, two_close_under=True), row(6),
            row(7, d_cross_up=True), row(8),
            row(9, two_cross_up=True), row(10),
        ]
        result = run_backtest(rows, start_date=rows[0].bar.date, commission_rate=0.0, slippage_per_share=0.0)
        actions = [event["action"] for event in result["events"]]
        self.assertEqual(actions[-1], "REENTER")
        self.assertEqual(result["final_stage"], 0)

    def test_next_open_execution_and_costs(self) -> None:
        rows = [
            row(0, open_=100.0, close=100.0),
            row(1, open_=101.0, close=100.0, d_close_under=True),
            row(2, open_=80.0, close=82.0),
        ]
        result = run_backtest(rows, start_date=rows[0].bar.date, commission_rate=0.001, slippage_per_share=0.02)
        exit_event = [e for e in result["events"] if e["action"] == "EXIT_1"][0]
        self.assertEqual(exit_event["signal_date"], rows[1].bar.date.isoformat())
        self.assertEqual(exit_event["fill_date"], rows[2].bar.date.isoformat())
        self.assertAlmostEqual(exit_event["fill_price"], 79.98, places=6)
        self.assertGreater(exit_event["commission"], 0)

    def test_exit_has_priority_over_reentry(self) -> None:
        rows = [
            row(0),
            row(1, d_close_under=True, d_cross_up=True),
            row(2),
        ]
        result = run_backtest(rows, start_date=rows[0].bar.date, commission_rate=0.0, slippage_per_share=0.0)
        actions = [event["action"] for event in result["events"]]
        self.assertEqual(actions, ["INITIAL_BUY", "EXIT_1"])

    def test_no_negative_cash_or_overexposure_on_gap_up_reentry(self) -> None:
        rows = [
            row(0, open_=100.0),
            row(1, d_close_under=True),
            row(2, open_=90.0),
            row(3, d_cross_up=True, weekly_alive=True),
            row(4, open_=150.0, close=150.0),
        ]
        result = run_backtest(rows, start_date=rows[0].bar.date, commission_rate=0.001, slippage_per_share=0.02)
        self.assertGreaterEqual(result["cash"], -1e-6)
        self.assertLessEqual(result["final_exposure_pct"], 100.0 + 1e-6)
        self.assertTrue(math.isfinite(result["metrics"]["total_return_pct"]))

    def test_published_artifacts_are_reproducible_and_non_repainting(self) -> None:
        root = Path(__file__).resolve().parents[1]
        pine = (root / "public" / "pine" / "us-index-mtf-decay.pine").read_text(encoding="utf-8")
        data = json.loads((root / "src" / "data" / "us-index-mtf-decay.json").read_text(encoding="utf-8"))
        self.assertIn("process_orders_on_close = false", pine)
        self.assertIn("lookahead = barmerge.lookahead_on", pine)
        self.assertNotIn("lookahead = barmerge.lookahead_off", pine)
        self.assertIn("close[1]", pine)
        self.assertEqual(data["params"]["scaleout_remaining_pct"], [20, 20, 20, 20, 50, 50])
        self.assertEqual(data["params"]["remaining_after_each_stage_pct"], [80, 64, 51.2, 40.96, 20.48, 10.24])
        self.assertEqual([item["symbol"] for item in data["instruments"]], ["QQQ", "SOXX"])


if __name__ == "__main__":
    unittest.main()
