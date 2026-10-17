# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import sys

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.backtest.us_index_mtf_decay import (  # noqa: E402
    prepare_signal_rows,
    run_backtest,
    run_buy_and_hold,
)

OUTPUT = ROOT / "src" / "data" / "us-index-mtf-decay.json"
FULL_OUTPUT = ROOT / "public" / "data" / "us-index-mtf-decay-full.json"
PRICE_DIR = ROOT / "data" / "prices"


def load_adjusted_ohlcv(ticker: str, start: str = "2001-01-01") -> pd.DataFrame:
    PRICE_DIR.mkdir(parents=True, exist_ok=True)
    cache = PRICE_DIR / f"US_MTF_{ticker}.csv"
    today = dt.date.today()
    if cache.exists():
        cached = pd.read_csv(cache, index_col=0, parse_dates=True).sort_index()
        if not cached.empty and cached.index[-1].date() >= today - dt.timedelta(days=5):
            return cached

    raw = yf.download(
        ticker,
        start=start,
        end=(today + dt.timedelta(days=1)).isoformat(),
        auto_adjust=False,
        actions=False,
        progress=False,
        threads=False,
    )
    if raw.empty:
        if cache.exists():
            return pd.read_csv(cache, index_col=0, parse_dates=True).sort_index()
        raise RuntimeError(f"No market data returned for {ticker}")
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = [str(col[0]).lower().replace(" ", "_") for col in raw.columns]
    else:
        raw.columns = [str(col).lower().replace(" ", "_") for col in raw.columns]
    ratio = raw["adj_close"] / raw["close"] if "adj_close" in raw else 1.0
    out = pd.DataFrame(index=pd.to_datetime(raw.index).tz_localize(None))
    for column in ("open", "high", "low", "close"):
        out[column] = pd.to_numeric(raw[column], errors="coerce") * ratio
    out["volume"] = pd.to_numeric(raw.get("volume", 0), errors="coerce").fillna(0)
    out = out.dropna(subset=["open", "high", "low", "close"])
    out.index.name = "Date"
    out.to_csv(cache)
    return out


def period_metrics(equity: list[dict], start: str, end: str | None = None) -> dict:
    selected = [p for p in equity if p["date"] >= start and (end is None or p["date"] <= end)]
    if len(selected) < 2:
        return {"start": start, "end": end, "total_return_pct": None, "mdd_pct": None}
    values = [float(p["nav"]) for p in selected]
    peaks: list[float] = []
    peak = values[0]
    for value in values:
        peak = max(peak, value)
        peaks.append(peak)
    return {
        "start": selected[0]["date"],
        "end": selected[-1]["date"],
        "total_return_pct": round((values[-1] / values[0] - 1.0) * 100.0, 4),
        "mdd_pct": round(min(value / high - 1.0 for value, high in zip(values, peaks)) * 100.0, 4),
    }


def build_one(ticker: str, label: str, start_date: dt.date) -> dict:
    prices = load_adjusted_ohlcv(ticker)
    rows = prepare_signal_rows(prices)
    strategy = run_backtest(
        rows,
        start_date=start_date,
        initial_capital=100_000.0,
        commission_rate=0.0001,
        slippage_per_share=0.02,
    )
    benchmark = run_buy_and_hold(
        prices,
        start_date=start_date,
        initial_capital=100_000.0,
        commission_rate=0.0001,
        slippage_per_share=0.02,
    )
    # Keep the committed artifact page-focused. Daily cash/unit internals and
    # the dense exposure ledger are reproducible from the engine but needlessly
    # inflate the statically generated Next.js payload.
    for internal_key in ("cash", "units", "final_equity", "pending", "exposure"):
        strategy.pop(internal_key, None)
    return {
        "symbol": ticker,
        "label": label,
        "currency": "USD",
        "data_start": prices.index[0].date().isoformat(),
        "data_end": prices.index[-1].date().isoformat(),
        "strategy": strategy,
        "benchmark": benchmark,
        "stress_periods": {
            "global_financial_crisis": period_metrics(strategy["equity"], "2007-10-01", "2009-06-30"),
            "covid_crash": period_metrics(strategy["equity"], "2020-02-01", "2020-06-30"),
            "rate_hike_bear": period_metrics(strategy["equity"], "2022-01-01", "2022-12-31"),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()

    start_date = dt.date(2002, 1, 2)
    instruments = [
        build_one("QQQ", "Nasdaq-100 ETF (QQQ)", start_date),
        build_one("SOXX", "Philadelphia Semiconductor ETF proxy (SOXX)", start_date),
    ]
    payload = {
        "schema_version": "1.0",
        "generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "strategy": {
            "key": "US_index_mtf_decay",
            "label": "미국 대형지수 MTF 감쇠 분할매도·일괄 재매수",
            "description": "일봉·2일봉·주봉 추세 훼손 깊이에 따라 잔여 수량을 감쇠 매도하고, 단계별 회복 신호에서 보유 현금을 재투입하는 롱온리 전략.",
        },
        "params": {
            "backtest_start": start_date.isoformat(),
            "initial_capital_usd": 100_000,
            "commission_pct_per_fill": 0.01,
            "slippage_usd_per_share": 0.02,
            "price_mode": "split/dividend-adjusted OHLC",
            "signal_timing": "completed D close; prior completed 2D/W value becomes actionable on the next daily bar close",
            "fill_timing": "next observed daily open",
            "scaleout_remaining_pct": [20, 20, 20, 20, 50, 50],
            "remaining_after_each_stage_pct": [80, 64, 51.2, 40.96, 20.48, 10.24],
            "reentry_sizing": "spend all available cash at the next open without leverage",
            "fx_mode": "disabled in baseline USD backtest",
            "two_day_proxy": "fixed two-calendar-day buckets; TradingView native 2D may differ around holidays",
        },
        "instruments": instruments,
        "assumptions": [
            "QQQ와 SOXX는 각각 나스닥100 및 필라델피아 반도체 지수의 거래 가능한 ETF 대용물이다.",
            "신호와 체결 종목을 동일하게 두었으며 지수 자체 체결을 가정하지 않았다.",
            "2D·주봉 신호는 확정된 이전 상위 봉만 사용하며 다음 일봉 종가에 의사결정한다. 미래 데이터·진행 중 상위 봉을 참조하지 않는다.",
            "재진입 주문은 다음 시가에서 가용 현금 전액으로 수량을 계산하므로 레버리지를 사용하지 않는다.",
            "배당·분할 조정 OHLC를 사용한다. 실제 세금, 환전비용, 호가 스프레드, 시장충격은 포함하지 않는다.",
            "환율 필터 A/B/C는 계좌·상품 구조가 달라 기준 백테스트에서 제외했으며 Pine 코드의 선택형 시각 필터로만 제공한다.",
        ],
    }
    FULL_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    FULL_OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # Static generation stays fast by shipping a chart/report subset in the
    # imported JSON. The complete fill ledger remains downloadable from public/.
    compact = json.loads(json.dumps(payload))
    compact["full_data_url"] = "/data/us-index-mtf-decay-full.json"
    for instrument in compact["instruments"]:
        for side in ("strategy", "benchmark"):
            points = instrument[side]["equity"]
            instrument[side]["equity"] = [
                point for index, point in enumerate(points)
                if index % 21 == 0 or index == len(points) - 1
            ]
        instrument["strategy"]["events"] = instrument["strategy"]["events"][-100:]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(compact, ensure_ascii=False, indent=2), encoding="utf-8")
    for item in instruments:
        sm = item["strategy"]["metrics"]
        bm = item["benchmark"]["metrics"]
        print(
            f"{item['symbol']}: strategy CAGR={sm['cagr_pct']} MDD={sm['mdd_pct']} "
            f"vs B&H CAGR={bm['cagr_pct']} MDD={bm['mdd_pct']}"
        )
    print(f"wrote {args.output} and {FULL_OUTPUT}")


if __name__ == "__main__":
    main()
