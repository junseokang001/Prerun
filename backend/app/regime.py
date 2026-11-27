"""Market-regime brake from KOSPI, KOSDAQ, and USD/KRW. Missing series stay missing."""

from __future__ import annotations

import math

import numpy as np


def _closes(bars: list[dict]) -> list[float]:
    out = []
    for bar in bars or []:
        close = bar.get("close")
        if isinstance(close, (int, float)) and math.isfinite(float(close)) and float(close) > 0:
            out.append(float(close))
    return out


def _vs_ma(bars: list[dict], window: int = 60) -> dict | None:
    closes = _closes(bars)
    if len(closes) < window:
        return None
    ma = float(np.mean(closes[-window:]))
    if ma <= 0:
        return None
    last = closes[-1]
    return {"close": last, "ma": ma, "distance": last / ma - 1}


def _realized_vol(bars: list[dict]) -> dict | None:
    closes = _closes(bars)
    if len(closes) < 40:
        return None
    rets = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes)) if closes[i - 1] > 0]
    if len(rets) < 40:
        return None
    window = np.array(rets, dtype=float)
    rvs = []
    for index in range(20, len(window) + 1):
        rvs.append(float(np.std(window[index - 20 : index], ddof=0) * math.sqrt(252)))
    if not rvs:
        return None
    recent = rvs[-252:]
    median = float(np.median(recent))
    return {"rv20": rvs[-1], "median": median, "high": bool(median > 0 and rvs[-1] > median * 1.5)}


def _fx_return(bars: list[dict]) -> float | None:
    closes = _closes(bars)
    if len(closes) < 21 or closes[-21] <= 0:
        return None
    return closes[-1] / closes[-21] - 1


def assess(kospi_bars: list[dict], kosdaq_bars: list[dict], fx_bars: list[dict]) -> dict:
    kospi = _vs_ma(kospi_bars)
    kosdaq = _vs_ma(kosdaq_bars)
    vol = _realized_vol(kospi_bars)
    fx = _fx_return(fx_bars)
    missing = []
    if kospi is None:
        missing.append("코스피 60일선")
    if kosdaq is None:
        missing.append("코스닥 60일선")
    if vol is None:
        missing.append("코스피 변동성")
    if fx is None:
        missing.append("원/달러 20일")
    both_below = bool(kospi and kosdaq and kospi["distance"] < 0 and kosdaq["distance"] < 0)
    vol_stress = bool(vol and vol["high"])
    fx_stress = bool(fx is not None and fx > 0.03)
    kospi_below = bool(kospi and kospi["distance"] < 0)
    weak = both_below or (kospi_below and (vol_stress or fx_stress))
    if kospi is None:
        weak = False
        badge = "국면 데이터 없음"
        available = False
    elif weak and both_below:
        badge = "약세장 주의 — 기준 상향 적용"
        available = True
    elif weak:
        badge = "변동성·환율 스트레스 — 기준 상향 적용"
        available = True
    else:
        badge = "국면 보통 — 기준 유지"
        available = True
    return {
        "available": available,
        "weak": weak and available,
        "badge": badge,
        "both_below_ma60": both_below,
        "vol_stress": vol_stress,
        "fx_stress": fx_stress,
        "kospi_distance": None if kospi is None else kospi["distance"],
        "kosdaq_distance": None if kosdaq is None else kosdaq["distance"],
        "rv20": None if vol is None else vol["rv20"],
        "rv_median": None if vol is None else vol["median"],
        "fx_ret_20": fx,
        "missing": missing,
        "applied_threshold": None,
        "cap": None,
    }
