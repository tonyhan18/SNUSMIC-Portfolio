# -*- coding: utf-8 -*-
"""US index MTF decay scale-out / all-in re-entry research engine.

Rules are evaluated on completed daily, two-calendar-day, and weekly bars.
Signals generated at a bar close fill at the next observed daily open.
The module intentionally stays independent from the report-driven strategy
contest because this is a single-ETF, full-capital allocation system.
"""
from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
import math
from typing import Any, Iterable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class DailyBar:
    date: dt.date
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass(frozen=True)
class SignalRow:
    bar: DailyBar
    d_close_under: bool = False
    d_cross_down: bool = False
    d_cross_up: bool = False
    two_close_under: bool = False
    two_cross_down: bool = False
    two_cross_up: bool = False
    week_close_under: bool = False
    week_cross_down: bool = False
    week_cross_up: bool = False
    weekly_alive: bool = False


def _truth(value: Any) -> bool:
    return bool(value) if value is not None and not pd.isna(value) else False


def _sma(values: pd.Series, length: int) -> pd.Series:
    return values.rolling(length, min_periods=length).mean()


def _with_signals(frame: pd.DataFrame, prefix: str) -> pd.DataFrame:
    out = frame.copy()
    sma5 = _sma(out["close"], 5)
    sma20 = _sma(out["close"], 20)
    out[f"{prefix}_close_under"] = out["close"] < sma20
    out[f"{prefix}_cross_down"] = (sma5 < sma20) & (sma5.shift(1) >= sma20.shift(1))
    out[f"{prefix}_cross_up"] = (sma5 > sma20) & (sma5.shift(1) <= sma20.shift(1))
    out[f"{prefix}_alive"] = out["close"] >= sma20
    out[f"{prefix}_sma5"] = sma5
    out[f"{prefix}_sma20"] = sma20
    return out


def prepare_signal_rows(prices: pd.DataFrame) -> list[SignalRow]:
    """Build completed-bar signals without forward-filling event booleans.

    The 2D research proxy uses fixed two-calendar-day buckets anchored to
    Python's ordinal calendar. TradingView's native ``2D`` feed can differ
    around exchange holidays; the published report discloses this limitation.
    """
    required = {"open", "high", "low", "close"}
    missing = required.difference(prices.columns)
    if missing:
        raise ValueError(f"missing OHLC columns: {sorted(missing)}")
    df = prices.copy().sort_index()
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    df = df[~df.index.duplicated(keep="last")]
    df = df.dropna(subset=["open", "high", "low", "close"])
    if df.empty:
        return []

    daily = _with_signals(df, "d")

    ordinal = pd.Series([stamp.date().toordinal() // 2 for stamp in df.index], index=df.index)
    two = df.assign(_bucket=ordinal).groupby("_bucket", sort=True).agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"),
        close=("close", "last"), volume=("volume", "sum") if "volume" in df else ("close", "size"),
    )
    two_close_dates = df.assign(_bucket=ordinal).groupby("_bucket").apply(lambda x: x.index[-1], include_groups=False)
    two.index = pd.DatetimeIndex(two_close_dates.to_list())
    two = _with_signals(two, "two")

    iso = df.index.isocalendar()
    weekly_keys = pd.Series(list(zip(iso.year.astype(int), iso.week.astype(int))), index=df.index)
    weekly_source = df.assign(_bucket=weekly_keys.to_list())
    weekly = weekly_source.groupby("_bucket", sort=True).agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"),
        close=("close", "last"), volume=("volume", "sum") if "volume" in df else ("close", "size"),
    )
    week_close_dates = weekly_source.groupby("_bucket").apply(lambda x: x.index[-1], include_groups=False)
    weekly.index = pd.DatetimeIndex(week_close_dates.to_list())
    weekly = _with_signals(weekly, "week")

    # Match the canonical non-repainting Pine pattern: the just-completed HTF
    # bar becomes available on the first daily bar of the next HTF period.
    # Because decisions occur at that daily close, its order fills at the next
    # daily open. This is deliberately one session slower than hindsight-style
    # Friday-close -> Monday-open execution.
    next_daily = pd.Series(df.index[1:].to_list(), index=df.index[:-1])

    def move_to_next_daily(events: pd.DataFrame) -> pd.DataFrame:
        moved = events.copy()
        moved.index = pd.DatetimeIndex([next_daily.get(index, pd.NaT) for index in events.index])
        return moved[~moved.index.isna()]

    two_events = move_to_next_daily(two[["two_close_under", "two_cross_down", "two_cross_up"]])
    week_events = move_to_next_daily(weekly[["week_close_under", "week_cross_down", "week_cross_up", "week_alive"]])
    joined = daily.join(two_events, how="left").join(week_events, how="left")
    joined["weekly_alive"] = joined["week_alive"].ffill().fillna(False)

    rows: list[SignalRow] = []
    for timestamp, values in joined.iterrows():
        rows.append(SignalRow(
            bar=DailyBar(
                timestamp.date(), float(values.open), float(values.high),
                float(values.low), float(values.close), float(values.get("volume", 0.0) or 0.0),
            ),
            d_close_under=_truth(values.d_close_under),
            d_cross_down=_truth(values.d_cross_down),
            d_cross_up=_truth(values.d_cross_up),
            two_close_under=_truth(values.get("two_close_under")),
            two_cross_down=_truth(values.get("two_cross_down")),
            two_cross_up=_truth(values.get("two_cross_up")),
            week_close_under=_truth(values.get("week_close_under")),
            week_cross_down=_truth(values.get("week_cross_down")),
            week_cross_up=_truth(values.get("week_cross_up")),
            weekly_alive=_truth(values.weekly_alive),
        ))
    return rows


def _metrics(equity: list[dict[str, Any]]) -> dict[str, Any]:
    if not equity:
        return {"total_return_pct": 0.0, "cagr_pct": None, "sharpe": None, "mdd_pct": 0.0}
    values = np.asarray([float(p["value"]) for p in equity], dtype=float)
    start = float(values[0])
    end = float(values[-1])
    total = (end / start - 1.0) * 100.0 if start else 0.0
    dates = [dt.date.fromisoformat(p["date"]) for p in equity]
    years = max((dates[-1] - dates[0]).days / 365.2425, 0.0)
    cagr = ((end / start) ** (1.0 / years) - 1.0) * 100.0 if start > 0 and end > 0 and years > 0 else None
    rets = np.diff(values) / values[:-1]
    finite = rets[np.isfinite(rets)]
    sharpe = None
    if len(finite) > 1 and float(np.std(finite, ddof=1)) > 0:
        sharpe = float(np.mean(finite) / np.std(finite, ddof=1) * math.sqrt(252))
    peaks = np.maximum.accumulate(values)
    drawdowns = values / peaks - 1.0
    return {
        "total_return_pct": round(float(total), 4),
        "cagr_pct": round(float(cagr), 4) if cagr is not None else None,
        "sharpe": round(float(sharpe), 4) if sharpe is not None else None,
        "mdd_pct": round(float(drawdowns.min() * 100.0), 4),
    }


def _yearly_returns(equity: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_year: dict[int, list[float]] = {}
    for point in equity:
        by_year.setdefault(dt.date.fromisoformat(point["date"]).year, []).append(float(point["nav"]))
    return [
        {"year": year, "return_pct": round((values[-1] / values[0] - 1.0) * 100.0, 4)}
        for year, values in sorted(by_year.items()) if values and values[0] != 0
    ]


def run_backtest(
    rows: Iterable[SignalRow],
    *,
    start_date: dt.date,
    initial_capital: float = 100_000.0,
    commission_rate: float = 0.0001,
    slippage_per_share: float = 0.02,
) -> dict[str, Any]:
    rows = list(rows)
    if not rows:
        raise ValueError("no price rows")

    cash = float(initial_capital)
    units = 0.0
    avg_cost = 0.0
    stage = 0
    pending: dict[str, Any] | None = None
    initial_units = 0.0
    events: list[dict[str, Any]] = []
    equity: list[dict[str, Any]] = []
    exposure: list[dict[str, Any]] = []
    sell_pnls: list[float] = []

    def buy_all(bar: DailyBar, action: str, signal_date: dt.date) -> None:
        nonlocal cash, units, avg_cost, initial_units, stage
        fill = bar.open + slippage_per_share
        qty = max(0.0, cash / (fill * (1.0 + commission_rate)))
        notional = qty * fill
        commission = notional * commission_rate
        previous_units = units
        previous_cost_value = avg_cost * units
        cash -= notional + commission
        if abs(cash) < 1e-7:
            cash = 0.0
        units += qty
        avg_cost = (previous_cost_value + notional + commission) / units if units else 0.0
        if action == "INITIAL_BUY":
            initial_units = units
        else:
            stage = 0
        events.append({
            "signal_date": signal_date.isoformat(), "fill_date": bar.date.isoformat(),
            "action": action, "stage_after": stage, "fill_price": round(fill, 6),
            "quantity": round(qty, 6), "commission": round(commission, 6),
            "position_after_pct": 100.0,
        })

    for row in rows:
        bar = row.bar
        if bar.date < start_date:
            continue

        if units == 0.0 and not events:
            buy_all(bar, "INITIAL_BUY", bar.date)
        elif pending is not None:
            if pending["action"].startswith("EXIT_"):
                fill = max(0.000001, bar.open - slippage_per_share)
                qty = min(units, pending["qty"])
                notional = qty * fill
                commission = notional * commission_rate
                cash += notional - commission
                realized = (fill - avg_cost) * qty - commission
                sell_pnls.append(realized)
                units -= qty
                if units < 1e-9:
                    units = 0.0
                stage = int(pending["stage"])
                position_pct = units / initial_units * 100.0 if initial_units else 0.0
                events.append({
                    "signal_date": pending["signal_date"].isoformat(), "fill_date": bar.date.isoformat(),
                    "action": pending["action"], "stage_after": stage,
                    "fill_price": round(fill, 6), "quantity": round(qty, 6),
                    "commission": round(commission, 6), "realized_pnl": round(realized, 6),
                    "position_after_pct": round(position_pct, 6),
                })
            else:
                buy_all(bar, "REENTER", pending["signal_date"])
                initial_units = units
            pending = None

        equity_close = cash + units * bar.close
        nav = equity_close / initial_capital
        position_value = units * bar.close
        exposure_pct = position_value / equity_close * 100.0 if equity_close > 0 else 0.0
        equity.append({"date": bar.date.isoformat(), "value": equity_close, "nav": round(nav, 8)})
        exposure.append({"date": bar.date.isoformat(), "weight_pct": round(exposure_pct, 6), "stage": stage})

        if pending is not None or units <= 0:
            continue

        next_stage = stage + 1
        exit_signal = (
            (stage == 0 and row.d_close_under)
            or (stage == 1 and row.d_cross_down)
            or (stage == 2 and row.two_close_under)
            or (stage == 3 and row.two_cross_down)
            or (stage == 4 and row.week_close_under)
            or (stage == 5 and row.week_cross_down)
        )
        if exit_signal and next_stage <= 6:
            fraction = 0.20 if next_stage <= 4 else 0.50
            qty = units * fraction
            if qty > 1e-9:
                pending = {
                    "action": f"EXIT_{next_stage}", "stage": next_stage,
                    "qty": qty, "signal_date": bar.date,
                }
                continue

        reentry_signal = (
            (stage in (1, 2) and row.weekly_alive and row.d_cross_up)
            or (stage in (3, 4) and row.two_cross_up)
            or (stage in (5, 6) and row.week_cross_up)
        )
        if reentry_signal and cash > 1e-9:
            pending = {"action": "REENTER", "signal_date": bar.date}

    metrics = _metrics(equity)
    metrics.update({
        "start": equity[0]["date"], "end": equity[-1]["date"],
        "events": max(0, len(events) - 1),
        "exit_events": len(sell_pnls),
        "win_rate_pct": round(sum(p > 0 for p in sell_pnls) / len(sell_pnls) * 100.0, 4) if sell_pnls else None,
    })
    final_equity = float(equity[-1]["value"])
    return {
        "metrics": metrics,
        "yearly": _yearly_returns(equity),
        "equity": [{"date": p["date"], "nav": p["nav"]} for p in equity],
        "exposure": exposure,
        "events": events,
        "cash": cash,
        "units": units,
        "final_equity": final_equity,
        "final_stage": stage,
        "pending": (
            {**pending, "signal_date": pending["signal_date"].isoformat()}
            if pending is not None else None
        ),
        "final_exposure_pct": exposure[-1]["weight_pct"],
    }


def run_buy_and_hold(
    prices: pd.DataFrame,
    *,
    start_date: dt.date,
    initial_capital: float = 100_000.0,
    commission_rate: float = 0.0001,
    slippage_per_share: float = 0.02,
) -> dict[str, Any]:
    frame = prices.loc[pd.Timestamp(start_date):].copy()
    if frame.empty:
        raise ValueError("no buy-and-hold rows")
    fill = float(frame.iloc[0]["open"]) + slippage_per_share
    units = initial_capital / (fill * (1.0 + commission_rate))
    equity = []
    for timestamp, values in frame.iterrows():
        value = units * float(values["close"])
        equity.append({"date": timestamp.date().isoformat(), "value": value, "nav": round(value / initial_capital, 8)})
    result = _metrics(equity)
    result.update({"start": equity[0]["date"], "end": equity[-1]["date"]})
    return {"metrics": result, "yearly": _yearly_returns(equity), "equity": [{"date": p["date"], "nav": p["nav"]} for p in equity]}
