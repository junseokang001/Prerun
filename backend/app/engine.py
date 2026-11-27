"""Pre-breakout signals, timing frequencies, and chart geometry. No look-ahead in features."""

from __future__ import annotations

import bisect
import math
from datetime import date, datetime

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

# Thresholds are the single source of truth for scores and the Korean explanations.
T = {
    "vol_ratio_min": 1.15,
    "vol_ratio_max": 2.30,
    "vol_today_max": 3.0,
    "ret5_flat_min": -0.04,
    "ret5_flat_max": 0.06,
    "ret20_min": -0.12,
    "ret20_max": 0.12,
    "ret3_max_quiet": 0.08,
    "bw_rank_max": 0.28,
    "dist52_min": -0.08,
    "dist52_max": -0.003,
    "dist_res_min": -0.05,
    "dist_res_max": -0.001,
    "ma_gap_5_20_max": 0.025,
    "ma_gap_20_60_min": -0.01,
    "ma_gap_20_60_max": 0.06,
    "dist_ma20_near_max": 0.04,
    "obv_min": 0.30,
    "rsi_min": 43.0,
    "rsi_max": 60.0,
    "rsi_ago_min": 32.0,
    "rsi_ago_max": 54.0,
    "rsi_rise": 2.0,
    "surge_1": 0.08,
    "surge_3": 0.12,
    "surge_5": 0.15,
    "hot_ma": 0.08,
    "hot_rsi": 72.0,
    "break_ma": -0.06,
    "break_ret5": -0.045,
    "target": 0.07,
    "min_score": 24.0,
    "min_signals": 2,
    "horizon": 30,
}

SIGNAL_IDS = [
    "quiet_volume",
    "squeeze",
    "near_resistance",
    "ma_convergence",
    "obv_divergence",
    "rsi_recovery",
]

SIGNAL_NAME = {
    "quiet_volume": "거래량은 늘고 가격은 잠잠",
    "squeeze": "볼린저 밴드 수축",
    "near_resistance": "저항 바로 아래",
    "ma_convergence": "이평선이 모이는 중",
    "obv_divergence": "OBV 매집",
    "rsi_recovery": "RSI가 40~55에서 회복",
}

FEATURE_NAMES = [
    "vol_ratio",
    "ret_5",
    "ret_20",
    "bw_rank",
    "dist_52",
    "dist_res",
    "ma_gap_5_20",
    "ma_gap_20_60",
    "obv_norm",
    "rsi",
    "dist_ma20",
    "rsi_delta",
    "atr_pct",
    "vol_flat",
    "kospi_ret_5",
    "kospi_ret_20",
    "nasdaq_ret_5",
    "nasdaq_ret_20",
    "rs_5",
    "rs_20",
    "sector_rs_5",
]

FEATURE_LABEL = {
    "vol_ratio": "5일 평균 거래량 ÷ 20일 평균",
    "ret_5": "5거래일 수익률",
    "ret_20": "20거래일 수익률",
    "bw_rank": "볼린저 밴드 폭의 120일 백분위",
    "dist_52": "직전 52주 고점과의 거리",
    "dist_res": "직전 20일 고점과의 거리",
    "ma_gap_5_20": "5일선이 20일선보다 아래에 있는 간격",
    "ma_gap_20_60": "20일선이 60일선보다 아래에 있는 간격",
    "obv_norm": "OBV 20일 변화 ÷ 하루 평균 거래량",
    "rsi": "RSI(14)",
    "dist_ma20": "현재가와 20일선의 차이",
    "rsi_delta": "RSI가 5거래일 전보다 오른 폭",
    "atr_pct": "ATR(14) ÷ 종가, 하루 변동 폭",
    "vol_flat": "가격이 잠잠할 때의 5일/20일 거래량",
    "kospi_ret_5": "코스피 5거래일 수익률",
    "kospi_ret_20": "코스피 20거래일 수익률",
    "nasdaq_ret_5": "나스닥 5거래일 수익률",
    "nasdaq_ret_20": "나스닥 20거래일 수익률",
    "rs_5": "같은 시장 지수 대비 5거래일 초과수익 (한국 코스피, 미국 나스닥)",
    "rs_20": "같은 시장 지수 대비 20거래일 초과수익 (한국 코스피, 미국 나스닥)",
    "sector_rs_5": "같은 업종 유니버스 대비 5거래일 초과수익 (업종이 2종목 미만이면 0)",
}

CALIBRATION_EDGES = [0.0, 0.30, 0.40, 0.50, 0.60, 0.70, 1.01]


def _finite(value) -> bool:
    try:
        return value is not None and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _f(value, default=float("nan")) -> float:
    if not _finite(value):
        return default
    return float(value)


def _barrier_labels(close: np.ndarray, high: np.ndarray, low: np.ndarray, atr: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Triple barrier over the next 10 sessions, plus the legacy close-to-close +7% label.

    Target distance is the smaller of +7% and +1.5×ATR. Stop distance is the smaller of
    −5% and −1.0×ATR. If both barriers print on the same bar, the stop wins.
    """
    n = len(close)
    horizon = 10
    tb = np.full(n, -1, dtype=np.int16)
    tb_day = np.full(n, 0, dtype=np.int16)
    legacy = np.full(n, -1, dtype=np.int16)
    for i in range(n):
        if i + horizon >= n:
            continue
        c0 = close[i]
        if not np.isfinite(c0) or c0 <= 0:
            continue
        atr_i = atr[i]
        if np.isfinite(atr_i) and atr_i > 0:
            upper = min(0.07, 1.5 * float(atr_i) / c0)
            stop = min(0.05, 1.0 * float(atr_i) / c0)
        else:
            upper = 0.07
            stop = 0.05
        up_px = c0 * (1.0 + upper)
        dn_px = c0 * (1.0 - stop)
        outcome = 0
        day = 0
        for step in range(1, horizon + 1):
            hit_up = high[i + step] >= up_px
            hit_dn = low[i + step] <= dn_px
            if hit_dn:
                outcome = 0
                day = step
                break
            if hit_up:
                outcome = 1
                day = step
                break
        tb[i] = outcome
        tb_day[i] = day
        legacy_hit = 0
        for step in range(1, horizon + 1):
            future = close[i + step]
            if np.isfinite(future) and future / c0 - 1 >= 0.07:
                legacy_hit = 1
                break
        legacy[i] = legacy_hit
    return tb, tb_day, legacy


def compute_features(bars: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(bars)
    df["dt"] = pd.to_datetime(df["date"])
    c = df["close"].astype(float)
    h = df["high"].astype(float)
    v = df["volume"].astype(float)
    df["ret_1"] = c.pct_change(1)
    df["ret_3"] = c.pct_change(3)
    df["ret_5"] = c.pct_change(5)
    df["ret_20"] = c.pct_change(20)
    df["ma5"] = c.rolling(5).mean()
    df["ma20"] = c.rolling(20).mean()
    df["ma60"] = c.rolling(60).mean()
    df["vol_ma5"] = v.rolling(5).mean()
    df["vol_ma20"] = v.rolling(20).mean()
    df["vol_ratio"] = df["vol_ma5"] / df["vol_ma20"].replace(0, np.nan)
    df["vol_today_ratio"] = v / df["vol_ma20"].replace(0, np.nan)
    std = c.rolling(20).std()
    df["bb_mid"] = df["ma20"]
    df["bb_upper"] = df["bb_mid"] + 2 * std
    df["bb_lower"] = df["bb_mid"] - 2 * std
    df["bandwidth"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"].replace(0, np.nan)
    df["bw_rank"] = df["bandwidth"].rolling(120, min_periods=60).rank(pct=True)
    df["prior_high_52"] = h.shift(1).rolling(252, min_periods=120).max()
    df["prior_high_20"] = h.shift(1).rolling(20).max()
    df["dist_52"] = c / df["prior_high_52"] - 1
    df["dist_res"] = c / df["prior_high_20"] - 1
    direction = np.sign(c.diff()).fillna(0.0)
    df["obv"] = (direction * v).cumsum()
    obv_delta = df["obv"] - df["obv"].shift(20)
    df["obv_norm"] = obv_delta / df["vol_ma20"].replace(0, np.nan) / 20.0
    delta = c.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    df["rsi"] = 100 - 100 / (1 + rs)
    df["rsi_5ago"] = df["rsi"].shift(5)
    df["ma_gap_5_20"] = (df["ma20"] - df["ma5"]) / df["ma20"].replace(0, np.nan)
    df["ma_gap_20_60"] = (df["ma60"] - df["ma20"]) / df["ma60"].replace(0, np.nan)
    df["ma5_slope"] = df["ma5"] / df["ma5"].shift(3) - 1
    df["dist_ma20"] = c / df["ma20"] - 1
    df["value20"] = (c * v).rolling(20).mean()
    low = df["low"].astype(float)
    prev_close = c.shift(1)
    true_range = pd.concat([(h - low), (h - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    df["atr14"] = true_range.rolling(14).mean()
    df["atr_pct"] = df["atr14"] / c.replace(0, np.nan)
    df["low10"] = low.rolling(10).min()
    df["vol_flat"] = np.where(df["ret_5"].abs() < 0.04, df["vol_ratio"], 0.0)
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    df["macd"] = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]
    close = c.to_numpy(dtype=float)
    n = len(close)
    hits = np.full(n, -1, dtype=np.int16)
    for step in range(1, T["horizon"] + 1):
        future = np.full(n, np.nan)
        future[: n - step] = close[step:] / close[: n - step] - 1
        mask = (hits < 0) & np.isfinite(future) & (future >= T["target"])
        # Only label rows that still have a full horizon ahead.
        mask[n - T["horizon"] :] = False
        hits[mask] = step
    unfinished = np.arange(n) > n - 1 - T["horizon"]
    hits[unfinished] = -1
    # Rows with a full window that never hit stay 0.
    full = ~unfinished & (hits < 0) & np.isfinite(close)
    hits[full] = 0
    df["first_hit"] = hits
    tb, tb_day, legacy = _barrier_labels(
        close,
        h.to_numpy(dtype=float),
        low.to_numpy(dtype=float),
        df["atr14"].to_numpy(dtype=float),
    )
    df["tb"] = tb
    df["tb_day"] = tb_day
    df["legacy10"] = legacy
    return df


def metrics_at(df: pd.DataFrame, i: int) -> dict:
    row = df.iloc[i]
    keys = [
        "close", "ret_1", "ret_3", "ret_5", "ret_20", "vol_ratio", "vol_today_ratio",
        "bw_rank", "dist_52", "dist_res", "ma_gap_5_20", "ma_gap_20_60", "ma5_slope",
        "obv_norm", "rsi", "rsi_5ago", "dist_ma20", "prior_high_52", "prior_high_20",
        "bb_upper", "bb_lower", "bb_mid", "bandwidth", "ma20", "ma5", "ma60",
        "volume", "vol_ma5", "vol_ma20", "value20", "macd", "macd_signal", "macd_hist",
        "high", "low", "open", "atr14", "atr_pct", "vol_flat",
        "kospi_ret_5", "kospi_ret_20", "nasdaq_ret_5", "nasdaq_ret_20",
        "rs_5", "rs_20", "sector_rs_5",
    ]
    out = {}
    for key in keys:
        out[key] = _f(row[key]) if key in df.columns else float("nan")
    return out


def decide(m: dict) -> dict:
    ret1, ret3, ret5, ret20 = m["ret_1"], m["ret_3"], m["ret_5"], m["ret_20"]
    vol_ratio, vol_today = m["vol_ratio"], m["vol_today_ratio"]
    bw, dist52, dist_res = m["bw_rank"], m["dist_52"], m["dist_res"]
    gap520, gap2060, slope = m["ma_gap_5_20"], m["ma_gap_20_60"], m["ma5_slope"]
    obv, rsi, rsi_ago = m["obv_norm"], m["rsi"], m["rsi_5ago"]
    dist_ma = m["dist_ma20"]
    close, upper, lower = m["close"], m["bb_upper"], m["bb_lower"]
    prior52 = m["prior_high_52"]

    quiet = (
        _finite(vol_ratio)
        and T["vol_ratio_min"] <= vol_ratio <= T["vol_ratio_max"]
        and _finite(vol_today)
        and vol_today < T["vol_today_max"]
        and _finite(ret5)
        and T["ret5_flat_min"] <= ret5 <= T["ret5_flat_max"]
        and _finite(ret20)
        and T["ret20_min"] <= ret20 <= T["ret20_max"]
        and _finite(ret3)
        and ret3 < T["ret3_max_quiet"]
    )
    squeeze = (
        _finite(bw)
        and bw <= T["bw_rank_max"]
        and _finite(close)
        and _finite(upper)
        and _finite(lower)
        and close < upper * 0.998
        and close > lower
        and _finite(ret5)
        and ret5 < 0.07
    )
    near_52 = _finite(dist52) and T["dist52_min"] <= dist52 <= T["dist52_max"]
    near_res = _finite(dist_res) and T["dist_res_min"] <= dist_res <= T["dist_res_max"]
    near = (
        (near_52 or near_res)
        and _finite(ret5)
        and ret5 < 0.07
        and _finite(close)
        and _finite(prior52)
        and close < prior52 * 0.998
    )
    ma_conv = (
        _finite(gap520)
        and 0 <= gap520 <= T["ma_gap_5_20_max"]
        and _finite(slope)
        and slope > 0
        and _finite(gap2060)
        and T["ma_gap_20_60_min"] <= gap2060 <= T["ma_gap_20_60_max"]
        and _finite(dist_ma)
        and dist_ma < T["dist_ma20_near_max"]
    )
    obv_div = (
        _finite(obv)
        and obv >= T["obv_min"]
        and _finite(ret20)
        and -0.08 <= ret20 <= 0.04
        and _finite(ret5)
        and ret5 < 0.06
    )
    rsi_rec = (
        _finite(rsi)
        and T["rsi_min"] <= rsi <= T["rsi_max"]
        and _finite(rsi_ago)
        and T["rsi_ago_min"] <= rsi_ago <= T["rsi_ago_max"]
        and rsi >= rsi_ago + T["rsi_rise"]
    )
    fired = {
        "quiet_volume": quiet,
        "squeeze": squeeze,
        "near_resistance": near,
        "ma_convergence": ma_conv,
        "obv_divergence": obv_div,
        "rsi_recovery": rsi_rec,
    }
    parts = {
        "quiet_volume": _score_quiet(vol_ratio, ret5, quiet),
        "squeeze": _score_squeeze(bw, squeeze),
        "near_resistance": _score_near(dist52, dist_res, near_52, near_res, near),
        "ma_convergence": _score_ma(gap520, slope, ma_conv),
        "obv_divergence": _score_obv(obv, obv_div),
        "rsi_recovery": _score_rsi(rsi, rsi_ago, rsi_rec),
    }
    score = round(sum(parts.values()), 2)
    surge = (
        (_finite(ret1) and ret1 >= T["surge_1"])
        or (_finite(ret3) and ret3 >= T["surge_3"])
        or (_finite(ret5) and ret5 >= T["surge_5"])
    )
    hot = (_finite(dist_ma) and dist_ma >= T["hot_ma"]) or (_finite(rsi) and rsi >= T["hot_rsi"])
    breakout = (
        _finite(close)
        and _finite(prior52)
        and close >= prior52
        and (
            (_finite(ret5) and ret5 >= 0.05)
            or (_finite(vol_today) and vol_today >= 2.2)
        )
    )
    breakdown = (
        _finite(dist_ma)
        and dist_ma <= T["break_ma"]
        and _finite(ret5)
        and ret5 <= T["break_ret5"]
    )
    excl = {"surge": surge, "hot": hot, "breakout": breakout, "breakdown": breakdown}
    located = quiet or squeeze or near
    raw = (
        score >= T["min_score"]
        and sum(bool(v) for v in fired.values()) >= T["min_signals"]
        and located
        and not any(excl.values())
    )
    return {
        "fired": fired,
        "parts": parts,
        "score": score,
        "excl": excl,
        "raw": raw,
        "near_52": near_52,
        "near_res": near_res,
    }


def _clip01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _score_quiet(vol_ratio, ret5, fired) -> float:
    if not fired:
        return 0.0
    vol_q = 1 - min(abs(vol_ratio - 1.65) / 0.75, 1)
    flat_q = 1 - min(abs(ret5) / 0.06, 1)
    return round(12 + 6 * vol_q + 4 * flat_q, 2)


def _score_squeeze(bw, fired) -> float:
    if not fired:
        return 0.0
    tightness = _clip01((T["bw_rank_max"] - bw) / T["bw_rank_max"])
    return round(14 + 8 * tightness, 2)


def _score_near(dist52, dist_res, near_52, near_res, fired) -> float:
    if not fired:
        return 0.0
    best = 0.0
    if near_52 and _finite(dist52):
        best = max(best, 12 + 6 * (1 - min(abs(dist52) / 0.08, 1)))
    if near_res and _finite(dist_res):
        best = max(best, 11 + 5 * (1 - min(abs(dist_res) / 0.05, 1)))
    return round(best, 2)


def _score_ma(gap, slope, fired) -> float:
    if not fired:
        return 0.0
    gap_q = 1 - min(gap / T["ma_gap_5_20_max"], 1)
    slope_q = _clip01(slope / 0.01)
    return round(10 + 4 * gap_q + 2 * slope_q, 2)


def _score_obv(obv, fired) -> float:
    if not fired:
        return 0.0
    return round(8 + 4 * _clip01(obv / 1.0), 2)


def _score_rsi(rsi, rsi_ago, fired) -> float:
    if not fired:
        return 0.0
    return round(8 + 2 * _clip01((rsi - rsi_ago) / 8), 2)


def scan_history(df: pd.DataFrame) -> list[dict]:
    n = len(df)
    days = []
    for i in range(n):
        if not _finite(df.iloc[i]["ma60"]) or not _finite(df.iloc[i]["bw_rank"]):
            continue
        m = metrics_at(df, i)
        decision = decide(m)
        hit = int(df.iloc[i]["first_hit"])
        tb = int(df.iloc[i]["tb"]) if "tb" in df.columns else -1
        tb_day = int(df.iloc[i]["tb_day"]) if "tb_day" in df.columns else 0
        legacy10 = int(df.iloc[i]["legacy10"]) if "legacy10" in df.columns else -1
        days.append(
            {
                "i": i,
                "date": str(df.iloc[i]["date"])[:10],
                "metrics": m,
                "first_hit": None if hit < 0 else hit,
                "tb": tb,
                "tb_day": tb_day,
                "legacy10": legacy10,
                **decision,
            }
        )
    return days


def _bucket_key(ids: list[str]) -> str:
    return "|".join(sorted(ids))


def _empty_bucket() -> dict:
    return {"n": 0, "w1": 0, "w2": 0, "w3": 0, "w4": 0, "none": 0, "hit10": 0}


def _add_hit(bucket: dict, hit: int) -> None:
    bucket["n"] += 1
    if hit <= 0:
        bucket["none"] += 1
    elif hit <= 3:
        bucket["w1"] += 1
    elif hit <= 7:
        bucket["w2"] += 1
    elif hit <= 15:
        bucket["w3"] += 1
    else:
        bucket["w4"] += 1
    if 1 <= hit <= 10:
        bucket["hit10"] += 1


def build_backtest(per_symbol: list[tuple[str, list[dict]]]) -> dict:
    """Empirical hit rates plus a time-split gradient boosting check.

    A day counts only when the stock had not already surged. Labels use the
    next 30 closes and never enter the features.
    """
    exact: dict[str, dict] = {}
    by_signal: dict[str, dict] = {sid: _empty_bucket() for sid in SIGNAL_IDS}
    baseline = _empty_bucket()
    candidates = _empty_bucket()
    rows = []
    for symbol, days in per_symbol:
        for day in days:
            if day["first_hit"] is None:
                continue
            m = day["metrics"]
            if not _finite(m["ret_5"]) or not _finite(m["rsi"]):
                continue
            # Baseline: not already surged over the last 1–5 sessions.
            if day["excl"]["surge"]:
                continue
            _add_hit(baseline, day["first_hit"])
            fired_ids = [sid for sid, on in day["fired"].items() if on]
            for sid in fired_ids:
                _add_hit(by_signal[sid], day["first_hit"])
            if day["raw"]:
                _add_hit(candidates, day["first_hit"])
                key = _bucket_key(fired_ids)
                exact.setdefault(key, _empty_bucket())
                _add_hit(exact[key], day["first_hit"])
            feat = feature_vector(m)
            if feat is not None and int(day.get("tb", -1)) >= 0:
                rows.append(
                    {
                        "date": day["date"],
                        "x": feat,
                        "y": int(day["tb"]),
                        "y_legacy": 1 if int(day.get("legacy10", -1)) == 1 else 0,
                        "first_hit": int(day["tb_day"]) if int(day["tb"]) == 1 else 0,
                    }
                )
    ml = _fit_ml(rows)
    dates = [r["date"] for r in rows]
    return {
        "target_pct": T["target"],
        "horizon": T["horizon"],
        "baseline": baseline,
        "candidates": candidates,
        "by_signal": by_signal,
        "exact": exact,
        "ml": ml,
        "sample_start": min(dates) if dates else None,
        "sample_end": max(dates) if dates else None,
        "feature_rows": len(rows),
    }


def index_return_series(bars: list[dict]) -> list[tuple[str, dict]]:
    closes = [(str(bar["date"])[:10], float(bar["close"])) for bar in bars if bar.get("close")]
    series: list[tuple[str, dict]] = []
    for index, (day, close) in enumerate(closes):
        prev5 = closes[index - 5][1] if index >= 5 else 0.0
        prev20 = closes[index - 20][1] if index >= 20 else 0.0
        if close == 0 or prev5 == 0 or prev20 == 0:
            continue
        series.append((day, {"ret5": close / prev5 - 1, "ret20": close / prev20 - 1}))
    return series


def _asof(series: list[tuple[str, dict]], day: str) -> dict:
    """Latest index return on or before this stock date. Missing sessions stay at the last real close."""
    if not series:
        return {}
    dates = [item[0] for item in series]
    index = bisect.bisect_right(dates, day) - 1
    return series[index][1] if index >= 0 else {}


def add_context_features(frames: dict, kospi_bars: list[dict], nasdaq_bars: list[dict], sector_of: dict, market_of: dict) -> None:
    """Join index trend, relative strength, and same-sector excess return onto each daily row."""
    kospi = index_return_series(kospi_bars)
    nasdaq = index_return_series(nasdaq_bars)
    sector_sum: dict[tuple[str, str], float] = {}
    sector_n: dict[tuple[str, str], int] = {}
    for symbol, frame in frames.items():
        sector = sector_of.get(symbol) or ("US" if market_of.get(symbol) == "US" else "KR")
        frame["sector"] = sector
        df = frame["df"]
        dates = [str(value)[:10] for value in df["date"].tolist()]
        for day, ret in zip(dates, df["ret_5"].tolist()):
            if ret == ret:
                key = (day, sector)
                sector_sum[key] = sector_sum.get(key, 0.0) + float(ret)
                sector_n[key] = sector_n.get(key, 0) + 1
    for symbol, frame in frames.items():
        df = frame["df"]
        dates = [str(value)[:10] for value in df["date"].tolist()]
        bench = nasdaq if market_of.get(symbol) == "US" else kospi
        sector = frame["sector"]
        kospi_5, kospi_20, naz_5, naz_20 = [], [], [], []
        rs_5, rs_20, sector_rs = [], [], []
        for index, day in enumerate(dates):
            k = _asof(kospi, day)
            n = _asof(nasdaq, day)
            b = _asof(bench, day)
            ret5 = df["ret_5"].iloc[index]
            ret20 = df["ret_20"].iloc[index]
            kospi_5.append(k.get("ret5", np.nan))
            kospi_20.append(k.get("ret20", np.nan))
            naz_5.append(n.get("ret5", np.nan))
            naz_20.append(n.get("ret20", np.nan))
            rs_5.append(float(ret5) - b["ret5"] if ret5 == ret5 and "ret5" in b else np.nan)
            rs_20.append(float(ret20) - b["ret20"] if ret20 == ret20 and "ret20" in b else np.nan)
            key = (day, sector)
            if key in sector_n and sector_n[key] >= 2 and ret5 == ret5:
                sector_rs.append(float(ret5) - sector_sum[key] / sector_n[key])
            else:
                sector_rs.append(0.0)
        df["kospi_ret_5"] = kospi_5
        df["kospi_ret_20"] = kospi_20
        df["nasdaq_ret_5"] = naz_5
        df["nasdaq_ret_20"] = naz_20
        df["rs_5"] = rs_5
        df["rs_20"] = rs_20
        df["sector_rs_5"] = sector_rs


def feature_vector(metrics: dict) -> list[float] | None:
    values: list[float] = []
    for name in FEATURE_NAMES:
        if name == "rsi_delta":
            if not _finite(metrics.get("rsi")) or not _finite(metrics.get("rsi_5ago")):
                return None
            values.append(float(metrics["rsi"]) - float(metrics["rsi_5ago"]))
            continue
        raw = metrics.get(name)
        if not _finite(raw):
            return None
        values.append(float(raw))
    return values


def feature_matrix(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    n = len(df)
    matrix = np.zeros((n, len(FEATURE_NAMES)), dtype=float)
    valid = np.ones(n, dtype=bool)
    rsi = df["rsi"].to_numpy(dtype=float)
    rsi_ago = df["rsi_5ago"].to_numpy(dtype=float)
    for column, name in enumerate(FEATURE_NAMES):
        series = rsi - rsi_ago if name == "rsi_delta" else df[name].to_numpy(dtype=float)
        matrix[:, column] = series
        valid &= np.isfinite(series)
    return matrix, valid


def _new_hgb() -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(
        max_depth=3,
        learning_rate=0.06,
        max_iter=200,
        min_samples_leaf=40,
        l2_regularization=1.0,
        random_state=7,
    )


def _fit_logit(x: np.ndarray, y: np.ndarray):
    if len(y) < 50 or y.min() == y.max():
        return None, None
    try:
        scaler = StandardScaler()
        xs = scaler.fit_transform(x)
        clf = LogisticRegression(max_iter=500, C=1.0, solver="lbfgs")
        clf.fit(xs, y)
        return clf, {"mean": scaler.mean_.astype(float), "scale": np.where(scaler.scale_ == 0, 1.0, scaler.scale_).astype(float)}
    except Exception:
        return None, None


def _logit_proba(logit, scaler, matrix: np.ndarray) -> np.ndarray:
    if logit is None or scaler is None:
        return np.full(len(matrix), 0.5)
    scale = np.where(scaler["scale"] == 0, 1.0, scaler["scale"])
    return logit.predict_proba((matrix - scaler["mean"]) / scale)[:, 1]


def _log_loss(y: np.ndarray, proba: np.ndarray) -> float:
    p = np.clip(proba, 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def _raw_scores(pack: dict, matrix: np.ndarray) -> np.ndarray:
    hgb = pack["model"].predict_proba(matrix)[:, 1]
    weight = float(pack.get("blend_w") if pack.get("blend_w") is not None else 1.0)
    if weight >= 0.999 or pack.get("logit") is None:
        return hgb
    other = _logit_proba(pack.get("logit"), pack.get("scaler"), matrix)
    return weight * hgb + (1.0 - weight) * other


def _calibrated_scores(pack: dict, matrix: np.ndarray) -> np.ndarray:
    raw = _raw_scores(pack, matrix)
    isotonic = pack.get("isotonic")
    if isotonic is None:
        return raw
    return np.clip(isotonic.predict(raw), 0.0, 1.0)


def attach_probabilities(frames: dict, ml: dict) -> None:
    """Score every completed day with the calibrated model. No future prices are used."""
    model = ml.get("model")
    for frame in frames.values():
        if model is None:
            frame["probs"] = None
            continue
        matrix, valid = feature_matrix(frame["df"])
        probs = np.full(len(frame["df"]), np.nan)
        if valid.any():
            probs[valid] = _calibrated_scores(ml, matrix[valid])
        frame["probs"] = probs


def local_contributions(model_pack: dict, metrics: dict) -> tuple[float | None, list[dict], float | None]:
    """How much each measured value moves the probability versus the training median.

    This is a one-at-a-time replacement, not a claim that the feature caused the price.
    """
    model = (model_pack or {}).get("model")
    medians = (model_pack or {}).get("medians")
    vector = feature_vector(metrics)
    if model is None or medians is None or vector is None:
        return None, [], None
    row = np.array([vector], dtype=float)
    raw_score = float(_raw_scores(model_pack, row)[0])
    probability = float(_calibrated_scores(model_pack, row)[0])
    found = []
    for index, name in enumerate(FEATURE_NAMES):
        swapped = row.copy()
        swapped[0, index] = medians[index]
        swapped_probability = float(_calibrated_scores(model_pack, swapped)[0])
        found.append(
            {
                "feature": name,
                "label": FEATURE_LABEL[name],
                "value": float(vector[index]),
                "median": float(medians[index]),
                "delta": probability - swapped_probability,
            }
        )
    found.sort(key=lambda item: abs(item["delta"]), reverse=True)
    return probability, found, raw_score


EMBARGO_DAYS = 10


def _unavailable(reason: str) -> dict:
    return {"available": False, "reason": reason, "threshold": None, "calibration": []}


def _fit_ml(rows: list[dict]) -> dict:
    """Purged walk-forward fit. Isotonic uses out-of-fold scores only."""
    if len(rows) < 400:
        return _unavailable(f"학습에 쓸 미급등 표본이 {len(rows)}건이라 모델을 맞추지 않았습니다. 400건 미만입니다.")
    rows = sorted(rows, key=lambda r: r["date"])
    unique_dates = sorted({r["date"] for r in rows})
    if len(unique_dates) < 140:
        return _unavailable("날짜가 부족해 학습·구간외 보정·시험을 나누지 못했습니다.")
    i_test = int(len(unique_dates) * 0.80)
    dev_dates = unique_dates[: max(0, i_test - EMBARGO_DAYS)]
    test_dates = unique_dates[i_test + EMBARGO_DAYS :]
    if len(dev_dates) < 80 or len(test_dates) < 20:
        return _unavailable("경계 10거래일을 비우면 학습 또는 시험 날짜가 부족합니다.")
    dev_set = set(dev_dates)
    test_set = set(test_dates)
    dev_rows = [r for r in rows if r["date"] in dev_set]
    test_rows = [r for r in rows if r["date"] in test_set]
    n_dev = len(dev_dates)
    cuts = [int(n_dev * p) for p in (0.45, 0.65, 0.85, 1.0)]
    oof: list[dict] = []
    for start, end in zip(cuts[:-1], cuts[1:]):
        train_end_idx = start - EMBARGO_DAYS
        if train_end_idx < 40 or end <= start:
            continue
        train_dates = set(dev_dates[:train_end_idx])
        oof_dates = set(dev_dates[start:end])
        train_rows = [r for r in dev_rows if r["date"] in train_dates]
        fold_rows = [r for r in dev_rows if r["date"] in oof_dates]
        if len(train_rows) < 200 or len(fold_rows) < 30:
            continue
        y_tr = np.array([r["y"] for r in train_rows], dtype=int)
        if y_tr.min() == y_tr.max():
            continue
        x_tr = np.array([r["x"] for r in train_rows], dtype=float)
        x_oof = np.array([r["x"] for r in fold_rows], dtype=float)
        hgb = _new_hgb()
        hgb.fit(x_tr, y_tr)
        logit, scaler = _fit_logit(x_tr, y_tr)
        p_h = hgb.predict_proba(x_oof)[:, 1]
        p_l = _logit_proba(logit, scaler, x_oof)
        for index, row in enumerate(fold_rows):
            oof.append({"y": row["y"], "p_hgb": float(p_h[index]), "p_logit": float(p_l[index]), "date": row["date"]})
    if len(oof) < 80:
        return _unavailable("구간 밖 보정에 쓸 표본이 80건보다 적습니다.")
    p_hgb = np.array([r["p_hgb"] for r in oof], dtype=float)
    p_logit = np.array([r["p_logit"] for r in oof], dtype=float)
    y_oof = np.array([r["y"] for r in oof], dtype=int)
    hgb_ll = _log_loss(y_oof, p_hgb)
    best_w, best_ll = 1.0, hgb_ll
    for weight in (0.0, 0.25, 0.5, 0.75):
        loss = _log_loss(y_oof, weight * p_hgb + (1.0 - weight) * p_logit)
        if loss + 1e-4 < best_ll:
            best_ll = loss
            best_w = weight
    blended = best_w * p_hgb + (1.0 - best_w) * p_logit
    isotonic = None
    if y_oof.min() != y_oof.max() and len(np.unique(np.round(blended, 5))) >= 3:
        isotonic = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        isotonic.fit(blended, y_oof)
    y_dev = np.array([r["y"] for r in dev_rows], dtype=int)
    if len(dev_rows) < 200 or len(test_rows) < 80 or y_dev.min() == y_dev.max():
        return _unavailable("학습 또는 시험 표본이 한쪽으로 몰리거나 건수가 부족합니다.")
    x_dev = np.array([r["x"] for r in dev_rows], dtype=float)
    model = _new_hgb()
    model.fit(x_dev, y_dev)
    logit, scaler = _fit_logit(x_dev, y_dev)
    pack = {"model": model, "logit": logit, "scaler": scaler, "blend_w": best_w, "isotonic": isotonic}
    x_test = np.array([r["x"] for r in test_rows], dtype=float)
    y_test = np.array([r["y"] for r in test_rows], dtype=int)
    y_legacy = np.array([r["y_legacy"] for r in test_rows], dtype=int)
    hits = np.array([r["first_hit"] for r in test_rows], dtype=int)
    raw_test = _raw_scores(pack, x_test)
    proba = np.clip(isotonic.predict(raw_test), 0.0, 1.0) if isotonic is not None else raw_test
    baseline = float(y_test.mean())
    legacy_baseline = float(y_legacy.mean())
    calibration = _calibration(proba, y_test, hits, raw_test, y_legacy)
    chosen = _choose_threshold(proba, y_test, baseline)
    oof_dates = sorted({r["date"] for r in oof})
    if chosen is None:
        threshold = None
        alerts = 0
        precision = None
        legacy_precision = None
        selected_timing = _empty_bucket()
        reason = (
            f"시험 구간({test_rows[0]['date']}~{test_rows[-1]['date']})에서 보정 확률을 올려도 "
            f"삼중 장벽 적중이 전체 {baseline * 100:.1f}%를 넘지 못했습니다. 후보를 만들지 않습니다."
        )
    else:
        threshold = chosen["threshold"]
        alerts = chosen["n"]
        precision = chosen["hit"]
        selected = proba >= threshold
        legacy_precision = float(y_legacy[selected].mean()) if int(selected.sum()) else None
        selected_timing = _timing_from_mask(hits, selected)
        blend_txt = "부스팅만" if best_w >= 0.999 else f"부스팅 {best_w * 100:.0f}% + 로지스틱 {(1 - best_w) * 100:.0f}%"
        reason = (
            f"학습 {dev_dates[0]}~{dev_dates[-1]}, 시험 {test_dates[0]}~{test_dates[-1]}. "
            f"경계 앞뒤 {EMBARGO_DAYS}거래일을 비워 10일 라벨이 시험 가격에 닿지 않게 했습니다. "
            f"등확률 보정은 학습 구간을 다시 나눈 뒤 그 밖에서 나온 {len(oof)}건에만 맞췄습니다. "
            f"혼합은 {blend_txt} (구간외 로그손실 부스팅 {hgb_ll:.3f}, 선택 {best_ll:.3f}). "
            f"시험 {len(y_test)}건의 삼중 장벽 적중은 {baseline * 100:.1f}%이고, "
            f"보정 확률 {threshold * 100:.0f}% 이상 {alerts}건은 {precision * 100:.1f}%입니다. "
            f"같은 기준의 종가 +7% 적중은 {legacy_precision * 100:.1f}%이고, 시험 전체 종가 +7%는 {legacy_baseline * 100:.1f}%입니다. "
            f"카드의 큰 숫자는 보정 확률이고, 그 옆의 시험 적중·건수·기준선이 실제 비율입니다."
        )
    order = np.argsort(proba)
    top_n = max(1, int(len(proba) * 0.2))
    top_rate = float(y_test[order[-top_n:]].mean())
    at_50 = proba >= 0.5
    return {
        "available": True,
        "model": model,
        "logit": logit,
        "scaler": scaler,
        "blend_w": best_w,
        "isotonic": isotonic,
        "medians": [float(v) for v in np.median(x_dev, axis=0)],
        "train_end": dev_dates[-1],
        "calibrate_start": oof_dates[0],
        "calibrate_end": oof_dates[-1],
        "test_start": test_dates[0],
        "test_end": test_dates[-1],
        "train_n": len(dev_rows),
        "calibrate_n": len(oof),
        "test_n": len(test_rows),
        "embargo_days": EMBARGO_DAYS,
        "oof_log_loss_hgb": hgb_ll,
        "oof_log_loss_blend": best_ll,
        "baseline_hit_rate": baseline,
        "legacy_baseline_hit_rate": legacy_baseline,
        "threshold": threshold,
        "threshold_reason": reason,
        "precision_at_threshold": precision,
        "legacy_precision_at_threshold": legacy_precision,
        "precision_at_50": float(y_test[at_50].mean()) if int(at_50.sum()) else None,
        "alerts": alerts,
        "alerts_at_50": int(at_50.sum()),
        "top_quintile_n": top_n,
        "top_quintile_hit_rate": top_rate,
        "calibration": calibration,
        "selected_timing": selected_timing,
        "label": "10거래일 안에 손절보다 목표(+7%와 1.5×ATR 중 작은 쪽)가 먼저",
        "reason": None if threshold is not None else reason,
    }


def _calibration(
    proba: np.ndarray,
    y: np.ndarray,
    hits: np.ndarray,
    raw: np.ndarray | None = None,
    legacy: np.ndarray | None = None,
) -> list[dict]:
    """Equal-count tiers on the raw score. Lookup uses those raw bounds.

    Isotonic scores pile up, so cutting the calibrated number hides the top tier.
    The number shown on a card is still this tier's test-fold hit rate.
    """
    score = np.asarray(raw if raw is not None else proba, dtype=float)
    quantiles = np.quantile(score, [0.0, 0.2, 0.4, 0.6, 0.8, 1.0])
    edges = [float(quantiles[0])]
    for value in quantiles[1:]:
        value = float(value)
        if value <= edges[-1]:
            value = edges[-1] + 1e-6
        edges.append(value)
    edges[-1] = max(edges[-1], float(score.max()) + 1e-4)
    rank_names = ["하위 20%", "20~40%", "40~60%", "60~80%", "상위 20%"]
    rows = []
    for index, (lo, hi) in enumerate(zip(edges[:-1], edges[1:])):
        mask = (score >= lo) & (score < hi) if index < len(edges) - 2 else (score >= lo) & (score <= hi)
        n = int(mask.sum())
        label = rank_names[index] if index < len(rank_names) else f"{index + 1}구간"
        rows.append(
            {
                "label": label,
                "lo": float(lo),
                "hi": float(hi if index == len(edges) - 2 else hi),
                "n": n,
                "predicted_mean": float(proba[mask].mean()) if n else None,
                "raw_mean": float(score[mask].mean()) if n else None,
                "actual_hit_rate": float(y[mask].mean()) if n else None,
                "legacy_hit_rate": float(legacy[mask].mean()) if legacy is not None and n else None,
                "timing": _timing_from_mask(hits, mask),
            }
        )
    return rows


def _choose_threshold(proba: np.ndarray, y: np.ndarray, baseline: float) -> dict | None:
    """Highest test-fold hit rate among cuts that beat the base rate.

    45% is allowed only when every cut from 50% upward fails to beat the base rate.
    The list is never filled by lowering the cut until eight names appear.
    """
    passing = []
    for threshold in (0.50, 0.55, 0.60, 0.65, 0.70, 0.45):
        mask = proba >= threshold
        n = int(mask.sum())
        if n < 80:
            continue
        hit = float(y[mask].mean())
        if hit <= baseline:
            continue
        passing.append({"threshold": threshold, "n": n, "hit": hit})
    if not passing:
        return None
    at_least_half = [row for row in passing if row["threshold"] >= 0.5]
    pool = at_least_half or passing
    # Highest test-fold hit rate. Ties keep the stricter cut.
    return sorted(pool, key=lambda row: (row["hit"], row["threshold"]))[-1]


def _timing_from_mask(hits: np.ndarray, mask: np.ndarray) -> dict:
    bucket = _empty_bucket()
    for hit in hits[mask]:
        _add_hit(bucket, int(hit))
    return bucket


def lookup_bucket(fired_ids: list[str], backtest: dict, min_n: int = 25) -> dict:
    exact = backtest.get("exact") or {}
    if not fired_ids:
        base = backtest.get("baseline") or _empty_bucket()
        return {
            "bucket": base,
            "note": f"지금 켜진 사전 돌파 신호가 없어, 아직 급등하지 않은 전체 {base.get('n', 0)}건의 빈도를 씁니다.",
            "kind": "baseline",
            "key": "baseline",
        }
    key = _bucket_key(fired_ids)
    if exact.get(key, {}).get("n", 0) >= min_n:
        return {
            "bucket": exact[key],
            "note": f"정확히 같은 신호 조합 {exact[key]['n']}건",
            "kind": "exact",
            "key": key,
        }
    # Drop the weakest signals until the sample is large enough.
    weight = {
        "quiet_volume": 6,
        "squeeze": 5,
        "near_resistance": 4,
        "ma_convergence": 3,
        "obv_divergence": 2,
        "rsi_recovery": 1,
    }
    ordered = sorted(fired_ids, key=lambda s: weight.get(s, 0), reverse=True)
    dropped = []
    current = list(ordered)
    while len(current) > 1:
        dropped_id = current.pop()
        dropped.append(dropped_id)
        trial = _bucket_key(current)
        if exact.get(trial, {}).get("n", 0) >= min_n:
            names = ", ".join(SIGNAL_NAME[s] for s in dropped)
            return {
                "bucket": exact[trial],
                "note": (
                    f"같은 조합은 {exact.get(key, {}).get('n', 0)}건뿐이라 "
                    f"표본 {min_n}건이 안 됩니다. 약한 신호({names})를 뺀 조합 {exact[trial]['n']}건을 씁니다."
                ),
                "kind": "trimmed",
                "key": trial,
            }
    if len(fired_ids) == 1:
        bucket = (backtest.get("by_signal") or {}).get(fired_ids[0]) or _empty_bucket()
        if bucket["n"] >= min_n:
            return {
                "bucket": bucket,
                "note": f"이 신호 하나만 켠 날까지 포함한 {bucket['n']}건",
                "kind": "single",
                "key": fired_ids[0],
            }
    cand = backtest.get("candidates") or _empty_bucket()
    if cand["n"] >= 10:
        return {
            "bucket": cand,
            "note": f"개별 조합 표본이 부족해, 후보 조건 전체를 통과한 {cand['n']}건의 빈도를 씁니다.",
            "kind": "candidates",
            "key": "*",
        }
    base = backtest.get("baseline") or _empty_bucket()
    return {
        "bucket": base,
        "note": f"후보 표본이 부족해, 아직 급등하지 않은 전체 {base['n']}건의 빈도를 씁니다.",
        "kind": "baseline",
        "key": "baseline",
    }


def window_table(bucket: dict) -> list[dict]:
    n = bucket.get("n") or 0
    spec = [
        ("1~3거래일", "w1", 1, 3),
        ("4~7거래일", "w2", 4, 7),
        ("8~15거래일", "w3", 8, 15),
        ("16~30거래일", "w4", 16, 30),
    ]
    rows = []
    for label, key, start, end in spec:
        count = int(bucket.get(key) or 0)
        rows.append(
            {
                "label": label,
                "start": start,
                "end": end,
                "count": count,
                "probability": (count / n) if n else 0.0,
            }
        )
    none = int(bucket.get("none") or 0)
    rows.append(
        {
            "label": "30거래일 안에 +7% 없음",
            "start": None,
            "end": None,
            "count": none,
            "probability": (none / n) if n else 0.0,
        }
    )
    return rows


def best_window(rows: list[dict]) -> dict | None:
    choices = [row for row in rows if row["start"]]
    if not choices or sum(row["count"] for row in choices) == 0:
        return None
    choices = sorted(choices, key=lambda row: (row["probability"], -row["start"]), reverse=True)
    return choices[0]


def series_indicators(bars: list[dict]) -> dict:
    """Indicators aligned to an arbitrary candle series (daily or intraday)."""
    if len(bars) < 5:
        return {"bars": bars, "ma5": [], "ma20": [], "ma60": [], "bb_upper": [], "bb_mid": [], "bb_lower": [], "rsi": [], "macd": [], "macd_signal": [], "macd_hist": []}
    close = pd.Series([b["c"] for b in bars], dtype=float)
    ma5 = close.rolling(5).mean()
    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()
    std = close.rolling(20).std()
    upper = ma20 + 2 * std
    lower = ma20 - 2 * std
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    rsi = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    macd = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    signal = macd.ewm(span=9, adjust=False).mean()

    def clean(series: pd.Series) -> list:
        return [None if not _finite(v) else round(float(v), 6) for v in series]

    return {
        "ma5": clean(ma5),
        "ma20": clean(ma20),
        "ma60": clean(ma60),
        "bb_upper": clean(upper),
        "bb_mid": clean(ma20),
        "bb_lower": clean(lower),
        "rsi": clean(rsi),
        "macd": clean(macd),
        "macd_signal": clean(signal),
        "macd_hist": clean(macd - signal),
    }


def detect_geometry(bars: list[dict], currency: str) -> list[dict]:
    if len(bars) < 30:
        return []
    k = 5 if " " in bars[-1]["t"] else 3
    highs = [b["h"] for b in bars]
    lows = [b["l"] for b in bars]
    times = [b["t"] for b in bars]
    close = bars[-1]["c"]
    swing_high = []
    swing_low = []
    for i in range(k, len(bars) - k):
        window_h = highs[i - k : i + k + 1]
        window_l = lows[i - k : i + k + 1]
        if highs[i] == max(window_h):
            swing_high.append((i, highs[i]))
        if lows[i] == min(window_l):
            swing_low.append((i, lows[i]))
    lines = []
    lines.extend(_levels(swing_high, close, times, "resistance", currency))
    lines.extend(_levels(swing_low, close, times, "support", currency))
    lines.extend(_trend(swing_low, times, close, "support", currency, len(bars)))
    lines.extend(_trend(swing_high, times, close, "resistance", currency, len(bars)))
    lines.extend(_patterns(bars, swing_low, swing_high, currency))
    return lines


def _price_text(price: float, currency: str) -> str:
    if currency == "USD":
        return f"${price:,.2f}"
    return f"{price:,.0f}원"


def _levels(swings, close, times, kind, currency) -> list[dict]:
    pool = []
    for idx, price in swings[-12:]:
        if kind == "resistance" and price <= close * 1.002:
            continue
        if kind == "support" and price >= close * 0.998:
            continue
        placed = False
        for level in pool:
            if abs(price - level["price"]) / level["price"] < 0.012:
                level["idx"].append(idx)
                level["price"] = sum(level["prices"] + [price]) / (len(level["prices"]) + 1)
                level["prices"].append(price)
                placed = True
                break
        if not placed:
            pool.append({"price": price, "prices": [price], "idx": [idx]})
    pool.sort(key=lambda level: (len(level["idx"]), -abs(level["price"] - close)), reverse=True)
    out = []
    word = "저항" if kind == "resistance" else "지지"
    for level in pool[:2]:
        touches = len(level["idx"])
        if touches < 2:
            continue
        gap = level["price"] / close - 1
        label = f"{word} {_price_text(level['price'], currency)} · {touches}번 터치 · 현재가 대비 {gap*100:+.1f}%"
        out.append(
            {
                "id": f"{kind}-{int(level['price'])}",
                "type": "horizontal",
                "price": round(level["price"], 4),
                "label": label,
                "explain": {
                    "id": f"{kind}-{int(level['price'])}",
                    "title": f"{word}선",
                    "plain": f"최근 고점이나 저점이 {_price_text(level['price'], currency)} 근처에 {touches}번 모였습니다. 그 가격을 {word}으로 그었습니다.",
                    "values": [
                        {"label": f"{word} 가격", "value": _price_text(level["price"], currency)},
                        {"label": "터치 횟수", "value": f"{touches}번"},
                        {"label": "현재가와 거리", "value": f"{gap*100:+.1f}%"},
                    ],
                    "why": "돌파 전에는 저항 바로 아래에서 거래가 모이는 경우가 많습니다. 이미 그 가격을 종가로 넘어갔다면 이 선은 후보 점수를 주지 않습니다.",
                    "evidence": "터치 횟수는 이 차트의 고점·저점을 센 것이고, 과거 적중률 숫자는 아닙니다.",
                    "source": "이 화면의 가격 데이터에서 계산",
                },
            }
        )
    return out


def _trend(swings, times, close, kind, currency, n) -> list[dict]:
    if len(swings) < 2:
        return []
    i1, p1 = swings[-2]
    i2, p2 = swings[-1]
    if i2 == i1:
        return []
    slope = (p2 - p1) / (i2 - i1)
    p_end = p1 + slope * (n - 1 - i1)
    if min(p1, p2, p_end) <= 0:
        return []
    if abs(p_end - close) / close > 0.18 and abs(p2 - close) / close > 0.18:
        return []
    per_bar = slope / p1
    word = "지지 추세선" if kind == "support" else "저항 추세선"
    label = f"{word} · 한 봉마다 {per_bar*100:+.2f}% · {_price_text(p1, currency)} → {_price_text(p2, currency)}"
    return [
        {
            "id": f"trend-{kind}",
            "type": "segment",
            "t1": times[i1],
            "p1": round(p1, 4),
            "t2": times[-1],
            "p2": round(float(p_end), 4),
            "label": label,
            "explain": {
                "id": f"trend-{kind}",
                "title": word,
                "plain": "최근에 만들어진 두 고점 또는 두 저점을 자로 이은 선입니다. 가격이 이 선에 닿았다가 방향이 바뀐 적이 있다는 뜻입니다.",
                "values": [
                    {"label": "첫 점", "value": f"{times[i1]} · {_price_text(p1, currency)}"},
                    {"label": "둘째 점", "value": f"{times[i2]} · {_price_text(p2, currency)}"},
                    {"label": "봉 하나당 기울기", "value": f"{per_bar*100:+.2f}%"},
                ],
                "why": "오르기 직전에는 저점을 조금씩 높이며 저항 아래에 붙는 모양이 나오기도 합니다. 선이 그려졌다고 돌파가 예약된 것은 아닙니다.",
                "evidence": "두 점의 가격과 기울기는 이 차트에서 계산했습니다.",
                "source": "이 화면의 가격 데이터에서 계산",
            },
        }
    ]


def _patterns(bars, swing_low, swing_high, currency) -> list[dict]:
    found = []
    close = bars[-1]["c"]
    # Box: last 20 bars' high-low range.
    window = bars[-20:]
    hi = max(b["h"] for b in window)
    lo = min(b["l"] for b in window)
    width = (hi - lo) / close if close else None
    if width is not None and width <= 0.08:
        found.append(_pattern(
            "box",
            "박스 횡보",
            "최근 20봉 동안 고점과 저점 사이가 좁습니다. 가격이 한 구간에 머무르고 있습니다.",
            [
                {"label": "최근 20봉 고가", "value": _price_text(hi, currency)},
                {"label": "최근 20봉 저가", "value": _price_text(lo, currency)},
                {"label": "고저 폭", "value": f"{width*100:.1f}%", "note": "8% 이하일 때 박스로 표시"},
            ],
            "폭이 좁은 상태가 오래가면 이후 방향이 한쪽으로 나오기도 합니다. 위인지 아래인지는 이 폭만으로 알 수 없습니다.",
            f"최근 20봉 고저 폭 {width*100:.1f}%. 기준은 8% 이하입니다.",
        ))
    # Double bottom on the last swing lows.
    if len(swing_low) >= 2:
        i1, p1 = swing_low[-2]
        i2, p2 = swing_low[-1]
        gap = abs(p1 - p2) / p1 if p1 else 1
        between = bars[i1:i2 + 1]
        mid_high = max(b["h"] for b in between) if between else p1
        rebound = mid_high / min(p1, p2) - 1 if min(p1, p2) else 0
        if 5 <= (i2 - i1) <= 40 and gap <= 0.015 and rebound >= 0.02:
            found.append(_pattern(
                "double-bottom",
                "이중 바닥",
                "비슷한 가격의 저점이 두 번 나왔고, 그 사이에는 그보다 높은 고점이 있었습니다.",
                [
                    {"label": "첫 저점", "value": f"{bars[i1]['t']} · {_price_text(p1, currency)}"},
                    {"label": "둘째 저점", "value": f"{bars[i2]['t']} · {_price_text(p2, currency)}"},
                    {"label": "두 저점 차이", "value": f"{gap*100:.2f}%", "note": "1.5% 이내일 때 표시"},
                    {"label": "사이 반등", "value": f"{rebound*100:.1f}%", "note": "2% 이상일 때 표시"},
                ],
                "같은 가격에서 두 번 버텼다는 기록입니다. 세 번째에도 버틴다는 보장은 없습니다.",
                f"저점 간격 {i2-i1}봉, 가격 차이 {gap*100:.2f}%, 사이 반등 {rebound*100:.1f}%.",
            ))
    if len(swing_high) >= 3 and len(swing_low) >= 3:
        highs = [p for _, p in swing_high[-3:]]
        lows = [p for _, p in swing_low[-3:]]
        flat = (max(highs) - min(highs)) / close if close else 1
        rising = lows[2] > lows[1] > lows[0] and (lows[2] / lows[0] - 1) > 0.01
        if flat <= 0.012 and rising:
            found.append(_pattern(
                "ascending-triangle",
                "상승 삼각형에 가까운 모양",
                "고점은 비슷한 가격에 막혀 있고, 저점은 조금씩 올라오고 있습니다.",
                [
                    {"label": "최근 고점 폭", "value": f"{flat*100:.2f}%", "note": "1.2% 이내일 때 표시"},
                    {"label": "저점 변화", "value": f"{(lows[2]/lows[0]-1)*100:+.1f}%"},
                ],
                "저항은 그대로인데 저점이 높아지면, 매수 쪽이 조금씩 올라붙는 모습으로 해석하기도 합니다.",
                "최근 스윙 고점 3개와 저점 3개로 계산했습니다.",
            ))
    return found


def _pattern(pid, title, plain, values, why, evidence) -> dict:
    return {
        "id": pid,
        "type": "note",
        "label": title,
        "explain": {
            "id": pid,
            "title": title,
            "plain": plain,
            "values": values,
            "why": why,
            "evidence": evidence,
            "source": "이 화면의 가격 데이터에서 계산",
        },
    }


def ml_probability(model_pack: dict, metrics: dict) -> float | None:
    probability, _, _ = local_contributions(model_pack, metrics)
    return probability


def trade_plan(close: float, atr: float, support: float, resistance: float, base: float) -> dict:
    """Reference stop and target. Not an order."""
    choices = []
    if _finite(support) and support < close * 0.995:
        choices.append(("최근 10거래일 저가", float(support), (close - float(support)) / close))
    if _finite(atr) and atr > 0:
        atr_stop = close - 1.5 * float(atr)
        if atr_stop < close * 0.995:
            choices.append(("종가에서 ATR(14)의 1.5배를 뺀 가격", atr_stop, (close - atr_stop) / close))
    if not choices:
        stop, method, distance = close * 0.97, "지지와 ATR을 만들지 못해 현재가의 -3%", 0.03
        atr_stop = None
    else:
        near = [item for item in choices if item[2] <= 0.08]
        method, stop, distance = min(near or choices, key=lambda item: item[2])
        atr_stop = close - 1.5 * float(atr) if _finite(atr) and atr > 0 else None
    anchor = float(base) if _finite(base) and base > 0 else close
    resist = float(resistance) if _finite(resistance) and resistance > close * 1.002 else None
    return {
        "stop": float(stop),
        "stop_method": method,
        "stop_distance": float(distance),
        "atr": float(atr) if _finite(atr) else None,
        "support": float(support) if _finite(support) else None,
        "atr_stop": float(atr_stop) if atr_stop is not None and _finite(atr_stop) else None,
        "target": float(anchor * 1.07),
        "target_base": float(anchor),
        "resistance": resist,
    }


def attach_level_stats(frames: dict, ml: dict) -> None:
    """Validation-window only: did the stop print before the +7% target within 10 sessions?"""
    test_start = ml.get("test_start")
    calibration = ml.get("calibration") or []
    if not test_start or not calibration:
        return
    totals = {row["label"]: {"n": 0, "stop_first": 0, "target_first": 0, "neither": 0} for row in calibration}
    for frame in frames.values():
        probs = frame.get("probs")
        df = frame.get("df")
        if probs is None or df is None or "atr14" not in df.columns:
            continue
        dates = [str(value)[:10] for value in df["date"].tolist()]
        close = df["close"].to_numpy(dtype=float)
        high = df["high"].to_numpy(dtype=float)
        low = df["low"].to_numpy(dtype=float)
        atr = df["atr14"].to_numpy(dtype=float)
        support = df["low10"].to_numpy(dtype=float)
        resist = df["prior_high_20"].to_numpy(dtype=float)
        for index, day in enumerate(dates):
            if day < test_start or index + 10 >= len(dates):
                continue
            probability = float(probs[index])
            if probability != probability:
                continue
            label = None
            for row in calibration:
                if row["lo"] <= probability < row["hi"] or (probability >= 1 and row["hi"] >= 1):
                    label = row["label"]
                    break
            if label is None:
                continue
            plan = trade_plan(float(close[index]), float(atr[index]), float(support[index]), float(resist[index]), float(close[index]))
            outcome = "neither"
            for step in range(1, 11):
                if low[index + step] <= plan["stop"]:
                    outcome = "stop_first"
                    break
                if high[index + step] >= plan["target"]:
                    outcome = "target_first"
                    break
            bucket = totals[label]
            bucket["n"] += 1
            bucket[outcome] += 1
    for row in calibration:
        row["levels"] = totals[row["label"]]


def parse_day(text: str) -> date:
    return datetime.strptime(text[:10], "%Y-%m-%d").date()
