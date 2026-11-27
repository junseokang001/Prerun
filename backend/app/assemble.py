"""Turn indicator rows into the Korean cards, reasons, and drill-down copy."""

from __future__ import annotations

from datetime import date, datetime

import numpy as np

from .calendar_util import (
    add_trading_days,
    korean_date,
    now_kst,
    offset_date,
    session_state,
    short_md,
)
from .engine import (
    FEATURE_LABEL,
    SIGNAL_NAME,
    T,
    best_window,
    decide,
    local_contributions,
    lookup_bucket,
    trade_plan,
    parse_day,
    window_table,
)

def pct(value, digits=1) -> str:
    if value is None or value != value:
        return "계산 불가"
    return f"{value * 100:+.{digits}f}%"


def num(value, digits=0) -> str:
    if value is None or value != value:
        return "계산 불가"
    return f"{value:,.{digits}f}"


def px(value, currency: str) -> str:
    if value is None or value != value:
        return "계산 불가"
    if currency == "USD":
        return f"${value:,.2f}"
    return f"{value:,.0f}원"


def _explain(eid, title, plain, values, why, evidence, source) -> dict:
    return {
        "id": eid,
        "title": title,
        "plain": plain,
        "values": values,
        "why": why,
        "evidence": evidence,
        "source": source,
    }


def _bucket_evidence(found: dict, label: str) -> str:
    bucket = found["bucket"]
    n = bucket.get("n") or 0
    hit10 = bucket.get("hit10") or 0
    rate10 = (hit10 / n) if n else 0
    return (
        f"{found['note']}. 그중 10거래일 안에 종가 기준 +7%에 처음 닿은 경우는 "
        f"{hit10}건, {rate10 * 100:.1f}%입니다. {label}"
    )


def signal_explain(sid: str, m: dict, part: float, fired: bool, found: dict, currency: str, source: str) -> dict:
    if sid == "quiet_volume":
        values = [
            {"label": "5일 평균 거래량", "value": f"{num(m['vol_ma5'])}주"},
            {"label": "20일 평균 거래량", "value": f"{num(m['vol_ma20'])}주"},
            {"label": "5일/20일", "value": f"{m['vol_ratio']:.2f}배" if m["vol_ratio"] == m["vol_ratio"] else "계산 불가", "note": "1.15~2.30배일 때 이 신호"},
            {"label": "마지막 완성 봉 거래량 / 20일", "value": f"{m['vol_today_ratio']:.2f}배" if m["vol_today_ratio"] == m["vol_today_ratio"] else "계산 불가", "note": "3배 이상이면 이미 터진 날로 보고 제외"},
            {"label": "5거래일 수익률", "value": pct(m["ret_5"]), "note": "-4%~+6%일 때 잠잠하다고 봄"},
            {"label": "20거래일 수익률", "value": pct(m["ret_20"]), "note": "-12%~+12% 밖이면 이 신호 끔"},
            {"label": "이 항목 점수", "value": f"{part:.1f}점 / 22점"},
        ]
        plain = "주가는 거의 제자리인데, 최근 5일 거래량이 20일 평균보다 조금 많아진 상태입니다. 크게 터진 거래가 아니라 조용히 늘어난 거래만 점수를 줍니다."
    elif sid == "squeeze":
        values = [
            {"label": "밴드 폭의 120일 백분위", "value": f"{m['bw_rank']*100:.1f}%" if m["bw_rank"] == m["bw_rank"] else "계산 불가", "note": "28% 이하일 때 수축"},
            {"label": "상단 밴드", "value": px(m["bb_upper"], currency)},
            {"label": "하단 밴드", "value": px(m["bb_lower"], currency)},
            {"label": "지금 가격", "value": px(m["close"], currency), "note": "상단을 종가로 넘기 전에만 신호"},
            {"label": "이 항목 점수", "value": f"{part:.1f}점 / 22점"},
        ]
        plain = "볼린저 밴드는 최근 20일 가격이 얼마나 넓게 흔들렸는지 보여 줍니다. 밴드가 최근 120일 가운데 좁은 편이면, 변동이 줄어든 수축으로 봅니다."
    elif sid == "near_resistance":
        values = [
            {"label": "직전 52주 고점", "value": px(m["prior_high_52"], currency)},
            {"label": "그 고점과의 거리", "value": pct(m["dist_52"]), "note": "-8%~-0.3%일 때 고점 바로 아래"},
            {"label": "직전 20일 고점", "value": px(m["prior_high_20"], currency)},
            {"label": "20일 고점과의 거리", "value": pct(m["dist_res"]), "note": "-5%~-0.1%일 때 짧은 저항 아래"},
            {"label": "이 항목 점수", "value": f"{part:.1f}점 / 18점"},
        ]
        plain = "고점을 이미 뚫은 상태가 아니라, 고점 바로 아래에서 아직 안 넘은 상태인지 봅니다. 52주 고점이거나 최근 20일 고점입니다."
    elif sid == "ma_convergence":
        values = [
            {"label": "5일선", "value": px(m["ma5"], currency)},
            {"label": "20일선", "value": px(m["ma20"], currency)},
            {"label": "60일선", "value": px(m["ma60"], currency)},
            {"label": "20일선 대비 5일선이 아래인 간격", "value": pct(m["ma_gap_5_20"]), "note": "0~2.5%일 때 아직 골든크로스 전"},
            {"label": "5일선 3거래일 기울기", "value": pct(m["ma5_slope"]), "note": "플러스일 때만"},
            {"label": "이 항목 점수", "value": f"{part:.1f}점 / 16점"},
        ]
        plain = "짧은 이평선이 긴 이평선을 아직 안 넘었지만, 간격이 2.5% 안으로 좁아지고 짧은 선은 위를 향하는 상태입니다. 이미 크게 벌어진 골든크로스는 점수를 주지 않습니다."
    elif sid == "obv_divergence":
        values = [
            {"label": "OBV 20일 변화 / 하루 평균 거래량", "value": f"{m['obv_norm']:+.2f}" if m["obv_norm"] == m["obv_norm"] else "계산 불가", "note": "0.30 이상일 때 매집으로 봄"},
            {"label": "20거래일 수익률", "value": pct(m["ret_20"]), "note": "-8%~+4%일 때 가격은 아직 잠잠"},
            {"label": "이 항목 점수", "value": f"{part:.1f}점 / 12점"},
        ]
        plain = "OBV는 오른 날 거래량은 더하고 내린 날 거래량은 빼는 누적값입니다. 가격은 별로 안 올랐는데 이 값이 늘면, 매수 체결이 더 쌓인 날로 해석합니다."
    else:
        values = [
            {"label": "RSI (14)", "value": f"{m['rsi']:.1f}" if m["rsi"] == m["rsi"] else "계산 불가", "note": "43~60일 때"},
            {"label": "5거래일 전 RSI", "value": f"{m['rsi_5ago']:.1f}" if m["rsi_5ago"] == m["rsi_5ago"] else "계산 불가", "note": "32~54였고, 지금보다 2포인트 이상 낮았을 때"},
            {"label": "이 항목 점수", "value": f"{part:.1f}점 / 10점"},
        ]
        plain = "RSI는 최근 14일 상승폭과 하락폭의 비율입니다. 70이 넘는 과열이 아니라, 40대에서 50대로 올라오는 회복만 봅니다."
    state = "켜짐" if fired else "꺼짐"
    return _explain(
        sid,
        SIGNAL_NAME[sid],
        plain,
        values + [{"label": "지금 상태", "value": state}],
        "이미 크게 오른 뒤의 신호가 아니라, 오르기 전에 가격이 아직 잠잠한지 같이 확인합니다. 하나라도 기준 밖이면 이 항목은 0점입니다.",
        _bucket_evidence(found, "같은 표본의 구간별 비율은 예상 시기 설명에 있습니다." if fired else "이 신호가 꺼져 있으면 조합 확률에 넣지 않습니다."),
        source,
    )


def tag_text(sid: str, m: dict, near_52: bool) -> str:
    if sid == "quiet_volume":
        return f"거래량 {m['vol_ratio']:.2f}배"
    if sid == "squeeze":
        return f"밴드 하위 {m['bw_rank']*100:.0f}%"
    if sid == "near_resistance":
        if near_52:
            return f"52주고 {m['dist_52']*100:+.1f}%"
        return f"저항 {m['dist_res']*100:+.1f}%"
    if sid == "ma_convergence":
        return f"이평 간격 {m['ma_gap_5_20']*100:.1f}%"
    if sid == "obv_divergence":
        return f"OBV {m['obv_norm']:+.2f}"
    return f"RSI {m['rsi']:.0f}←{m['rsi_5ago']:.0f}"


def _timing_block(fired_ids, backtest, signal_date: date, signal_index: int, bar_dates: list[date], market: str, source: str) -> dict:
    found = lookup_bucket(fired_ids, backtest)
    rows = window_table(found["bucket"])
    best = best_window(rows)
    n = found["bucket"].get("n") or 0
    if best is None:
        return {
            "available": False,
            "label": "시기 계산 불가",
            "detail": "30거래일 내 +7% 사례 없음",
            "probability": 0.0,
            "sample_n": n,
            "bucket_note": found["note"],
            "windows": rows,
            "window_start": None,
            "window_end": None,
            "target_pct": 7,
            "explain": _explain(
                "timing",
                "예상 상승 시기",
                "과거 비슷한 신호에서 신호일 종가보다 7% 위로 처음 마감한 날을 셉니다. 이번 표본에서는 30거래일 안에 그 일이 한 번도 없습니다.",
                [{"label": "표본", "value": f"{n}건"}, {"label": "기준", "value": "신호일 종가 대비 종가 +7%"}],
                "사례가 없으면 날짜를 만들어 적지 않습니다.",
                found["note"],
                source,
            ),
        }
    start = offset_date(bar_dates, signal_index, best["start"], market, signal_date)
    end = offset_date(bar_dates, signal_index, best["end"], market, signal_date)
    explain_values = [
        {"label": "신호일", "value": korean_date(signal_date)},
        {"label": "가장 흔했던 구간", "value": f"{short_md(start)}~{short_md(end)} ({best['label']})"},
        {"label": "그 구간에서 처음 +7%에 닿은 비율", "value": f"{best['count']}건 / {n}건 = {best['probability']*100:.1f}%"},
        {"label": "표본 설명", "value": found["note"]},
    ]
    for row in rows:
        if row["start"] is None:
            explain_values.append({"label": row["label"], "value": f"{row['count']}건 · {row['probability']*100:.1f}%"})
        else:
            explain_values.append(
                {"label": row["label"], "value": f"{row['count']}건 · {row['probability']*100:.1f}%"}
            )
    return {
        "available": True,
        "label": f"{short_md(start)}~{short_md(end)}",
        "detail": f"{best['label']} 내",
        "probability": best["probability"],
        "sample_n": n,
        "bucket_note": found["note"],
        "windows": [
            {
                **row,
                "range_label": (
                    None
                    if row["start"] is None
                    else f"{short_md(offset_date(bar_dates, signal_index, row['start'], market, signal_date))}~{short_md(offset_date(bar_dates, signal_index, row['end'], market, signal_date))}"
                ),
            }
            for row in rows
        ],
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "target_pct": 7,
        "explain": _explain(
            "timing",
            "예상 상승 시기",
            "과거에 비슷한 신호가 켜진 날, 그 날 종가보다 7% 높은 가격으로 처음 마감한 시점을 모았습니다. 가장 자주 나왔던 구간을 예상 시기로 적습니다. 그 구간에 꼭 오른다는 뜻이 아닙니다.",
            explain_values,
            "주말과 휴장일은 거래일에서 뺍니다. 휴장일은 코드에 넣어 둔 한국거래소·미국 휴장일이고, 임시 휴장은 빠질 수 있습니다. 이 구간이 지나도 +7%가 없으면 타이밍 지남으로 옮깁니다.",
            found["note"] + " 확률은 그 표본의 빈도입니다.",
            source,
        ),
    }


def _reason(kind: str, m: dict, gain: float, timing: dict, decision: dict, currency: str) -> str:
    if kind == "reached":
        return f"신호일 종가 대비 {pct(gain)}로 +7% 기준에 이미 닿았습니다. 최근 1·3·5거래일 수익률은 {pct(m['ret_1'])}, {pct(m['ret_3'])}, {pct(m['ret_5'])}입니다."
    if kind == "surge":
        bits = []
        if m["ret_1"] == m["ret_1"] and m["ret_1"] >= T["surge_1"]:
            bits.append(f"최근 1거래일 {pct(m['ret_1'])} (기준 +8%)")
        if m["ret_3"] == m["ret_3"] and m["ret_3"] >= T["surge_3"]:
            bits.append(f"최근 3거래일 {pct(m['ret_3'])} (기준 +12%)")
        if m["ret_5"] == m["ret_5"] and m["ret_5"] >= T["surge_5"]:
            bits.append(f"최근 5거래일 {pct(m['ret_5'])} (기준 +15%)")
        return "급등이 이미 나왔습니다. " + " · ".join(bits)
    if kind == "hot":
        return (
            f"20일선 이격 {pct(m['dist_ma20'])} (기준 +8% 이상) 또는 RSI {m['rsi']:.1f} (기준 72 이상). "
            "이미 많이 벌어진 상태로 보고 후보에서 뺍니다."
        )
    if kind == "breakout":
        return (
            f"가격 {px(m['close'], currency)}가 직전 52주 고점 {px(m['prior_high_52'], currency)} 이상입니다. "
            f"5거래일 {pct(m['ret_5'])}, 당일 거래량비 {m['vol_today_ratio']:.2f}배. 돌파는 이미 나온 것으로 봅니다."
        )
    if kind == "breakdown":
        return (
            f"셋업이 아래로 깨졌습니다. 20일선 이격 {pct(m['dist_ma20'])} (기준 -6% 이하), "
            f"5거래일 {pct(m['ret_5'])} (기준 -4.5% 이하)."
        )
    if kind == "expired":
        return (
            f"예상 구간 {timing.get('label')} ({timing.get('detail')})이 지났고, "
            f"신호일 종가 대비 {pct(gain)}로 +7%에 못 미쳤습니다."
        )
    if kind == "below":
        calibrated_now = decision.get("calibrated_probability")
        threshold = decision.get("threshold")
        shown = f"{calibrated_now * 100:.1f}%" if isinstance(calibrated_now, float) else "계산 불가"
        cut = f"{threshold * 100:.0f}%" if isinstance(threshold, float) else "검증 기준"
        return f"보정 점수 {shown}로 후보 기준 {cut}보다 낮아졌습니다."
    missed = []
    if not decision["fired"]["quiet_volume"]:
        missed.append(f"거래량비 {m['vol_ratio']:.2f}배·5거래일 {pct(m['ret_5'])}")
    if not decision["fired"]["squeeze"]:
        missed.append(f"밴드 백분위 {m['bw_rank']*100:.0f}%")
    if not decision["fired"]["near_resistance"]:
        missed.append(f"52주 거리 {pct(m['dist_52'])}")
    if not decision["fired"]["ma_convergence"]:
        missed.append(f"5·20 이평 간격 {pct(m['ma_gap_5_20'])}")
    return (
        f"신호 조건이 꺼졌습니다. 점수 {decision['score']:.1f}점 (기준 {T['min_score']:.0f}점). "
        + " / ".join(missed[:3])
    )


FEATURE_SHORT = {
    "vol_ratio": "거래량",
    "ret_5": "5일 수익",
    "ret_20": "20일 수익",
    "bw_rank": "밴드 백분위",
    "dist_52": "52주 고점",
    "dist_res": "20일 고점",
    "ma_gap_5_20": "5·20일선",
    "ma_gap_20_60": "20·60일선",
    "obv_norm": "OBV",
    "rsi": "RSI",
    "dist_ma20": "20일선 이격",
    "rsi_delta": "RSI 변화",
    "atr_pct": "변동폭",
    "vol_flat": "잠잠할 때 거래량",
    "kospi_ret_5": "코스피 5일",
    "kospi_ret_20": "코스피 20일",
    "nasdaq_ret_5": "나스닥 5일",
    "nasdaq_ret_20": "나스닥 20일",
    "rs_5": "지수대비 5일",
    "rs_20": "지수대비 20일",
    "sector_rs_5": "업종대비 5일",
}


def _fmt_feature(name: str, value: float) -> str:
    if value != value:
        return "계산 불가"
    if name == "vol_ratio":
        return f"{value:.2f}배"
    if name in {
        "ret_5", "ret_20", "dist_52", "dist_res", "ma_gap_5_20", "ma_gap_20_60", "dist_ma20",
        "atr_pct", "kospi_ret_5", "kospi_ret_20", "nasdaq_ret_5", "nasdaq_ret_20",
        "rs_5", "rs_20", "sector_rs_5",
    }:
        return f"{value * 100:+.1f}%"
    if name == "vol_flat":
        return f"{value:.2f}배"
    if name == "bw_rank":
        return f"{value * 100:.0f}% (낮을수록 좁음)"
    if name == "rsi":
        return f"{value:.1f}"
    if name == "rsi_delta":
        return f"{value:+.1f}포인트"
    if name == "obv_norm":
        return f"{value:+.2f}"
    return f"{value:.3f}"


def _bucket_for(probability: float | None, ml: dict) -> dict | None:
    if probability is None:
        return None
    rows = ml.get("calibration") or []
    for index, row in enumerate(rows):
        last = index == len(rows) - 1
        if row["lo"] <= probability < row["hi"] or (last and probability >= row["lo"]):
            return row
    return None


def _timing_from_model(calibrated, raw_score, backtest, signal_date, signal_index, bar_dates, market, source) -> dict:
    ml = backtest.get("ml") or {}
    chosen = None
    note = "모델 검증 표본이 없습니다."
    bucket = _bucket_for(raw_score, ml)
    baseline = ml.get("baseline_hit_rate")
    bucket_is_selected = (
        bucket is not None
        and (bucket.get("timing") or {}).get("n", 0) >= 40
        and isinstance(bucket.get("actual_hit_rate"), float)
        and isinstance(baseline, float)
        and bucket["actual_hit_rate"] > baseline
    )
    if bucket_is_selected:
        chosen = bucket["timing"]
        note = (
            f"시험 구간 {bucket['label']} {chosen['n']}건이 "
            "신호일 종가 대비 +7%에 처음 닿은 시점입니다."
        )
    elif (ml.get("selected_timing") or {}).get("n", 0) >= 20:
        chosen = ml["selected_timing"]
        cut = ml.get("threshold")
        cut_txt = f"{cut * 100:.0f}% 이상" if isinstance(cut, float) else "후보 기준 이상"
        note = f"검증 구간에서 확률이 {cut_txt}이었던 {chosen['n']}건이 +7%에 처음 닿은 시점입니다."
    if not chosen or not chosen.get("n"):
        return {
            "available": False,
            "label": "시기 계산 불가",
            "detail": "모델이 고른 과거 사례가 없습니다",
            "probability": 0.0,
            "sample_n": 0,
            "bucket_note": note,
            "windows": [],
            "window_start": None,
            "window_end": None,
            "target_pct": 7,
            "explain": _explain(
                "timing",
                "예상 상승 시기",
                "시기는 모델이 후보로 골랐던 과거 날짜가 그 뒤 언제 +7%에 처음 닿았는지로 정합니다. 지금 그 표본이 없습니다.",
                [{"label": "표본", "value": "0건"}],
                "표본이 없으면 날짜를 만들지 않습니다.",
                note,
                source,
            ),
        }
    rows = window_table(chosen)
    best = best_window(rows)
    n = chosen.get("n") or 0
    if best is None:
        explain = _explain(
            "timing",
            "예상 상승 시기",
            "모델이 고른 과거 사례 안에, 30거래일 내 종가 +7%에 닿은 날이 없습니다.",
            [{"label": "표본", "value": f"{n}건"}],
            "사례가 없으면 날짜를 적지 않습니다.",
            note,
            source,
        )
        return {
            "available": False,
            "label": "30거래일 내 사례 없음",
            "detail": "상승 시점 없음",
            "probability": 0.0,
            "sample_n": n,
            "bucket_note": note,
            "windows": rows,
            "window_start": None,
            "window_end": None,
            "target_pct": 7,
            "explain": explain,
        }
    start = offset_date(bar_dates, signal_index, best["start"], market, signal_date)
    end = offset_date(bar_dates, signal_index, best["end"], market, signal_date)
    values = [
        {"label": "신호일", "value": korean_date(signal_date)},
        {"label": "가장 많았던 구간", "value": f"{short_md(start)}~{short_md(end)} ({best['label']})"},
        {"label": "그 구간에 처음 닿은 비율", "value": f"{best['count']}건 / {n}건 = {best['probability'] * 100:.1f}%"},
        {"label": "표본", "value": note},
    ]
    for row in rows:
        values.append({"label": row["label"], "value": f"{row['count']}건 · {row['probability'] * 100:.1f}%"})
    return {
        "available": True,
        "label": f"{short_md(start)}~{short_md(end)}",
        "detail": f"{best['label']} 내",
        "probability": best["probability"],
        "sample_n": n,
        "bucket_note": note,
        "windows": [
            {
                **row,
                "range_label": (
                    None
                    if row["start"] is None
                    else (
                        f"{short_md(offset_date(bar_dates, signal_index, row['start'], market, signal_date))}"
                        f"~{short_md(offset_date(bar_dates, signal_index, row['end'], market, signal_date))}"
                    )
                ),
            }
            for row in rows
        ],
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "target_pct": 7,
        "explain": _explain(
            "timing",
            "예상 상승 시기",
            "검증 구간에서 모델이 후보로 본 날들만 모았습니다. 그 날 종가보다 7% 높은 가격으로 처음 마감한 시점이 언제였는지를 센 것입니다. 가장 자주 나온 구간을 예상 시기로 적습니다.",
            values,
            "주말과 휴장일은 거래일에서 뺍니다. 휴장일은 코드에 넣어 둔 한국거래소·미국 휴장일이고, 임시 휴장은 빠질 수 있습니다. 이 구간이 지나도 +7%가 없으면 타이밍 지남으로 옮깁니다.",
            note,
            source,
        ),
    }


def classify_stock(meta: dict, frame: dict, backtest: dict, quote: dict | None) -> dict:
    df = frame["df"]
    days = frame["days"]
    if not days:
        return {"status": "skip", "error": "지표를 계산할 일봉이 부족합니다."}
    m = dict(days[-1]["metrics"])
    price = float(m["close"])
    prev_close = float(df.iloc[-2]["close"]) if len(df) > 1 else price
    price_source = frame["source"]
    price_time = days[-1]["date"]
    live_session = session_state(meta["market"]) == "open"
    if quote and quote.get("price"):
        price = float(quote["price"])
        prev_close = float(quote.get("prev_close") or prev_close)
        price_source = quote.get("source") or price_source
        price_time = quote.get("time") or price_time
        if live_session:
            n = len(df)

            def back(k):
                idx = n - k
                return float(df.iloc[idx]["close"]) if idx >= 0 else float("nan")

            m["close"] = price
            m["ret_1"] = price / back(1) - 1
            m["ret_3"] = price / back(3) - 1
            m["ret_5"] = price / back(5) - 1
            m["ret_20"] = price / back(20) - 1
            if m["ma20"] == m["ma20"]:
                m["dist_ma20"] = price / m["ma20"] - 1
            if m["prior_high_52"] == m["prior_high_52"]:
                m["dist_52"] = price / m["prior_high_52"] - 1
            if m["prior_high_20"] == m["prior_high_20"]:
                m["dist_res"] = price / m["prior_high_20"] - 1
            bench5 = "nasdaq_ret_5" if meta["market"] == "US" else "kospi_ret_5"
            bench20 = "nasdaq_ret_20" if meta["market"] == "US" else "kospi_ret_20"
            if m["ret_5"] == m["ret_5"] and m.get(bench5) == m.get(bench5):
                m["rs_5"] = m["ret_5"] - m[bench5]
            if m["ret_20"] == m["ret_20"] and m.get(bench20) == m.get(bench20):
                m["rs_20"] = m["ret_20"] - m[bench20]
            if m["ret_5"] == m["ret_5"] and m.get("vol_ratio") == m.get("vol_ratio"):
                m["vol_flat"] = m["vol_ratio"] if abs(m["ret_5"]) < 0.04 else 0.0
    decision = decide(m)
    ml = backtest.get("ml") or {}
    calibrated, contribs, raw_score = local_contributions(ml, m)
    threshold = ml.get("threshold")
    bucket_preview = _bucket_for(raw_score, ml)
    probability = calibrated
    decision["probability"] = probability
    decision["calibrated_probability"] = calibrated
    decision["threshold"] = threshold
    today = now_kst().date()
    market = meta["market"]
    bar_dates = [parse_day(str(value)[:10]) for value in df["date"].tolist()]
    recent = [day for day in days if (bar_dates[-1] - parse_day(day["date"])).days <= 40]
    probs = frame.get("probs")

    def hist_on(day) -> bool:
        if probs is None or not isinstance(threshold, float):
            return False
        value = float(probs[day["i"]])
        if value != value or value < threshold:
            return False
        if day["excl"]["surge"] or day["excl"]["hot"] or day["excl"]["breakout"]:
            return False
        return True

    blocked = decision["excl"]["surge"] or decision["excl"]["hot"] or decision["excl"]["breakout"]
    today_on = isinstance(calibrated, float) and isinstance(threshold, float) and calibrated >= threshold and not blocked

    def streak_start(end_pos: int):
        pos = end_pos
        while pos > 0 and hist_on(recent[pos - 1]) and recent[pos]["i"] - recent[pos - 1]["i"] == 1:
            pos -= 1
        return recent[pos]

    status = "neutral"
    demote_kind = None
    demoted_at = None
    signal_date = today
    signal_index = len(df)
    gain = 0.0

    if today_on:
        if recent and hist_on(recent[-1]):
            start = streak_start(len(recent) - 1)
            signal_date = parse_day(start["date"])
            signal_index = start["i"]
            base = float(df.iloc[signal_index]["close"])
        else:
            signal_date = today
            signal_index = len(df)
            base = float(df.iloc[-1]["close"])
        gain = price / base - 1 if base else 0.0
        timing = _timing_from_model(calibrated, raw_score, backtest, signal_date, signal_index, bar_dates, market, frame["source"])
        window_end = timing.get("window_end")
        end_date = parse_day(window_end) if window_end else None
        if gain >= T["target"]:
            status = "demoted"
            demote_kind = "reached"
            demoted_at = today
        elif end_date and today > end_date:
            status = "demoted"
            demote_kind = "expired"
            demoted_at = add_trading_days(end_date, 1, market)
        else:
            status = "candidate"
    else:
        on_positions = [i for i, day in enumerate(recent) if hist_on(day)]
        anchor = parse_day(recent[-1]["date"]) if recent else today
        anchor_index = recent[-1]["i"] if recent else len(df) - 1
        if on_positions:
            start = streak_start(on_positions[-1])
            signal_date = parse_day(start["date"])
            signal_index = start["i"]
            base = float(df.iloc[signal_index]["close"])
            gain = price / base - 1 if base else 0.0
            timing = _timing_from_model(calibrated, raw_score, backtest, signal_date, signal_index, bar_dates, market, frame["source"])
            status = "demoted"
            if decision["excl"]["surge"] or gain >= T["target"]:
                demote_kind = "surge" if decision["excl"]["surge"] else "reached"
            elif decision["excl"]["breakout"]:
                demote_kind = "breakout"
            elif decision["excl"]["hot"]:
                demote_kind = "hot"
            else:
                end_date = parse_day(timing["window_end"]) if timing.get("window_end") else None
                if end_date and today > end_date and gain < T["target"]:
                    demote_kind = "expired"
                else:
                    demote_kind = "below"
            last_on = recent[on_positions[-1]]
            if last_on["i"] + 1 < len(df):
                demoted_at = parse_day(str(df.iloc[last_on["i"] + 1]["date"])[:10])
            else:
                demoted_at = today
        else:
            gain = m["ret_5"] if m["ret_5"] == m["ret_5"] else 0.0
            timing = _timing_from_model(calibrated, raw_score, backtest, anchor, anchor_index, bar_dates, market, frame["source"])

    reason = _reason(demote_kind, m, gain, timing, decision, meta["currency"]) if demote_kind else None
    source = frame["source"]
    bucket = _bucket_for(raw_score, ml)
    bucket_public = None
    if bucket:
        bucket_public = {
            "label": bucket["label"],
            "n": bucket["n"],
            "predicted_mean": bucket["predicted_mean"],
            "actual_hit_rate": bucket["actual_hit_rate"],
            "legacy_hit_rate": bucket.get("legacy_hit_rate"),
        }
    hit_txt = "검증 표본 없음"
    if bucket and bucket.get("n") and bucket.get("actual_hit_rate") is not None:
        base_txt = f"{ml.get('baseline_hit_rate') * 100:.1f}%" if isinstance(ml.get("baseline_hit_rate"), float) else "기준선 없음"
        hit_txt = (
            f"검증 구간에서 확률이 {bucket['label']}였던 {bucket['n']}건의 실제 적중률은 "
            f"{bucket['actual_hit_rate'] * 100:.1f}%입니다. 같은 구간 전체는 {base_txt}입니다."
        )
    prob_txt = f"{probability * 100:.1f}%" if isinstance(probability, float) else "계산 불가"
    cut_txt = f"{threshold * 100:.0f}%" if isinstance(threshold, float) else "없음"
    explain_score = _explain(
        "probability",
        "보정 확률",
        "카드의 큰 숫자는 구간 밖 점수로만 맞춘 보정 확률입니다. 같은 칸에 시험 구간의 실제 적중률, 건수, 기준선을 같이 적습니다. 보정 전 94% 같은 원점수는 카드에 나오지 않습니다.",
        [
            {"label": "보정 확률", "value": prob_txt},
            {"label": "이 점수대의 시험 적중률", "value": hit_txt},
            {"label": "보정 전 점수", "value": f"{raw_score * 100:.1f}%" if isinstance(raw_score, float) else "계산 불가", "note": "시험 적중률이 아닙니다. 검증 표의 평균으로만 비교합니다."},
            {"label": "후보 기준", "value": f"보정 점수 {cut_txt} 이상, 이미 급등·과열·돌파한 종목은 제외"},
            {"label": "나누는 방법", "value": ml.get("threshold_reason") or "모델을 맞추지 못했습니다."},
            {"label": "이 구간의 검증", "value": hit_txt},
        ],
        "이 숫자가 높아도 오르기로 예약된 것은 아닙니다. 시험 구간의 실제 비율과 기준선을 같이 봐야 합니다.",
        hit_txt,
        "서버 시작과 시세 갱신 때 다시 학습한 모델",
    )
    contributions = []
    for item in contribs:
        direction = "올렸습니다" if item["delta"] >= 0 else "내렸습니다"
        explain = _explain(
            item["feature"],
            FEATURE_LABEL[item["feature"]],
            f"이 값 하나만 학습 구간 중앙값으로 바꾸면, 모델 확률이 {abs(item['delta']) * 100:.1f}%포인트 {direction}. 가격이 그래서 움직인다는 뜻이 아니라, 모델 안에서 이 숫자가 확률을 민 크기입니다.",
            [
                {"label": "이 종목 값", "value": _fmt_feature(item["feature"], item["value"])},
                {"label": "학습 구간 중앙값", "value": _fmt_feature(item["feature"], item["median"])},
                {"label": "확률 변화", "value": f"{item['delta'] * 100:+.1f}%포인트"},
                {"label": "바꾸기 전 확률", "value": prob_txt},
            ],
            "양수면 이 값이 확률을 높인 쪽이고, 음수면 낮춘 쪽입니다. 한 번에 하나씩만 바꿉니다.",
            hit_txt,
            "서버 시작과 시세 갱신 때 다시 학습한 모델",
        )
        contributions.append(
            {
                **item,
                "text": f"{FEATURE_SHORT[item['feature']]} {_fmt_feature(item['feature'], item['value'])} · {item['delta'] * 100:+.1f}%p",
                "explain": explain,
            }
        )
    tags = [
        {"id": item["feature"], "text": item["text"], "explain": item["explain"]}
        for item in contributions[:3]
    ]
    explains = {}
    for sid in SIGNAL_NAME:
        found = lookup_bucket([sid], backtest)
        explains[sid] = signal_explain(sid, m, decision["parts"][sid], bool(decision["fired"][sid]), found, meta["currency"], source)
    last = df.iloc[-1]
    base_close = float(df.iloc[signal_index]["close"]) if 0 <= signal_index < len(df) else float(last["close"])
    raw_plan = trade_plan(
        float(price),
        float(last["atr14"]) if last["atr14"] == last["atr14"] else float("nan"),
        float(last["low10"]) if last["low10"] == last["low10"] else float("nan"),
        float(last["prior_high_20"]) if last["prior_high_20"] == last["prior_high_20"] else float("nan"),
        base_close,
    )
    level_stats = (bucket or {}).get("levels") or {}
    level_n = int(level_stats.get("n") or 0)

    def _rate(key: str) -> str:
        if not level_n:
            return "표본 없음"
        count = int(level_stats.get(key) or 0)
        return f"{count}건 / {level_n}건 = {count / level_n * 100:.1f}%"

    level_evidence = (
        f"검증 구간 확률 {bucket['label']} {level_n}건에서 10거래일 안을 봤습니다. "
        f"손절이 목표보다 먼저 {_rate('stop_first')}. 목표가 먼저 {_rate('target_first')}. 둘 다 아니면 {_rate('neither')}."
        if bucket and level_n
        else "이 확률 구간에서 손절과 목표의 선후를 셀 검증 표본이 없습니다."
    )
    note = "참고 가격입니다. 매매 지시가 아닙니다."
    explain_stop = _explain(
        "plan-stop",
        "손절 참고가",
        f"고른 기준은 {raw_plan['stop_method']}입니다. 그 가격 아래로 내려가면 이번 계산의 자리가 깨진 것으로 봅니다. {note}",
        [
            {"label": "손절 참고가", "value": px(raw_plan["stop"], meta["currency"])},
            {"label": "현재가와의 거리", "value": pct(-raw_plan["stop_distance"])},
            {"label": "최근 10거래일 저가", "value": px(raw_plan["support"], meta["currency"]) if raw_plan["support"] else "계산 불가"},
            {"label": "ATR(14)", "value": px(raw_plan["atr"], meta["currency"]) if raw_plan["atr"] else "계산 불가"},
            {"label": "종가 − 1.5×ATR", "value": px(raw_plan["atr_stop"], meta["currency"]) if raw_plan["atr_stop"] else "계산 불가"},
        ],
        "현재가보다 낮고 8% 안에서 더 가까운 가격을 골랐습니다. 8% 안이 없으면 계산된 것 중 더 가까운 가격입니다.",
        level_evidence,
        source,
    )
    explain_target = _explain(
        "plan-target",
        "+7% 참고 목표",
        f"모델이 학습한 사건은 신호일 종가보다 7% 높은 가격입니다. {note}",
        [
            {"label": "신호일 종가", "value": px(raw_plan["target_base"], meta["currency"])},
            {"label": "참고 목표", "value": px(raw_plan["target"], meta["currency"]), "note": "신호일 종가 × 1.07"},
            {"label": "현재가와의 거리", "value": pct(raw_plan["target"] / price - 1) if price else "계산 불가"},
        ],
        "7%는 화면을 채우려고 정한 숫자가 아니라, 모델을 학습할 때 쓴 기준입니다.",
        level_evidence,
        source,
    )
    explain_resist = None
    if raw_plan["resistance"]:
        explain_resist = _explain(
            "plan-resist",
            "가까운 저항",
            f"직전 20거래일 고점 {px(raw_plan['resistance'], meta['currency'])}이 현재가 위에 있습니다. {note}",
            [
                {"label": "저항", "value": px(raw_plan["resistance"], meta["currency"])},
                {"label": "현재가와의 거리", "value": pct(raw_plan["resistance"] / price - 1) if price else "계산 불가"},
            ],
            "+7% 목표와 별개로, 최근에 막힌 가격입니다.",
            "직전 20거래일 고점은 오늘 봉을 뺀 일봉으로 계산했습니다.",
            source,
        )
    plan = {
        "stop": raw_plan["stop"],
        "target": raw_plan["target"],
        "resistance": raw_plan["resistance"],
        "stop_method": raw_plan["stop_method"],
        "evidence": level_evidence,
        "explain_stop": explain_stop,
        "explain_target": explain_target,
        "explain_resistance": explain_resist,
        "lines": [
            {"id": "plan-stop", "type": "horizontal", "price": raw_plan["stop"], "label": f"손절 참고 {px(raw_plan['stop'], meta['currency'])}", "explain": explain_stop},
            {"id": "plan-target", "type": "horizontal", "price": raw_plan["target"], "label": f"+7% 참고 {px(raw_plan['target'], meta['currency'])}", "explain": explain_target},
        ]
        + (
            [{"id": "plan-resist", "type": "horizontal", "price": raw_plan["resistance"], "label": f"저항 {px(raw_plan['resistance'], meta['currency'])}", "explain": explain_resist}]
            if explain_resist
            else []
        ),
    }
    spark = [round(float(c), 4) for c in df["close"].tail(30).tolist()]
    change = price - prev_close
    change_pct = change / prev_close if prev_close else 0.0
    return {
        "status": status,
        "symbol": meta["symbol"],
        "code": meta["code"],
        "name": meta["name"],
        "market": meta["market"],
        "currency": meta["currency"],
        "price": price,
        "prev_close": prev_close,
        "change": change,
        "change_pct": change_pct,
        "volume": float(quote.get("volume") or m.get("volume") or 0) if quote else float(m.get("volume") or 0),
        "value20": m.get("value20"),
        "vol_ratio": m.get("vol_ratio"),
        "score": decision["score"],
        "probability": probability,
        "calibrated_probability": calibrated,
        "threshold": threshold,
        "bucket": bucket_public,
        "baseline_hit_rate": ml.get("baseline_hit_rate") if isinstance(ml.get("baseline_hit_rate"), float) else None,
        "contributions": contributions,
        "plan": plan,
        "signal_date": signal_date.isoformat(),
        "demoted_at": demoted_at.isoformat() if isinstance(demoted_at, date) else None,
        "demote_reason": reason,
        "demote_kind": demote_kind,
        "gain_since_signal": gain,
        "timing": {k: v for k, v in timing.items() if k != "explain"} | {"explain": timing["explain"]},
        "tags": tags[:3],
        "all_tags": tags,
        "explains": explains,
        "explain_score": explain_score,
        "explain_timing": timing["explain"],
        "spark": spark,
        "source": source,
        "price_source": price_source,
        "price_time": price_time,
        "signal_bar_date": days[-1]["date"],
        "dropped_today": frame["dropped_today"],
        "metrics": m,
        "decision": {
            "fired": decision["fired"],
            "parts": decision["parts"],
            "score": decision["score"],
            "excl": decision["excl"],
            "near_52": decision["near_52"],
        },
        "stale": frame.get("stale", False),
    }


def indicator_explains(m: dict, currency: str, source: str) -> dict:
    return {
        "ma": _explain(
            "ma",
            "이동평균선",
            "이동평균은 최근 며칠 종가를 평균 낸 선입니다. 5일선은 이번 주, 20일선은 한 달, 60일선은 한 분기 정도의 평균 가격입니다.",
            [
                {"label": "5일선", "value": px(m["ma5"], currency)},
                {"label": "20일선", "value": px(m["ma20"], currency)},
                {"label": "60일선", "value": px(m["ma60"], currency)},
                {"label": "현재가와 20일선 차이", "value": pct(m["dist_ma20"]), "note": "+8% 이상이면 과열로 보고 후보에서 제외"},
            ],
            "짧은 선이 긴 선 아래에 바짝 붙으면, 아직 골든크로스 전으로 보고 점수를 조금 줍니다. 이미 멀리 위로 벌어지면 점수를 주지 않습니다.",
            "평균은 이 종목의 일봉 종가로 계산했습니다. 장중에는 오늘 봉을 빼고 어제까지의 일봉을 씁니다.",
            source,
        ),
        "bollinger": _explain(
            "bollinger",
            "볼린저 밴드",
            "20일 평균을 가운데 두고, 그 위아래로 변동폭(표준편차의 2배)만큼 선을 그린 것입니다. 선 사이가 좁으면 최근 가격이 덜 흔들린 것입니다.",
            [
                {"label": "상단", "value": px(m["bb_upper"], currency)},
                {"label": "가운데(20일선)", "value": px(m["bb_mid"], currency)},
                {"label": "하단", "value": px(m["bb_lower"], currency)},
                {"label": "폭의 120일 백분위", "value": f"{m['bw_rank']*100:.1f}%" if m["bw_rank"] == m["bw_rank"] else "계산 불가", "note": "숫자가 낮을수록 최근보다 좁음. 28% 이하를 수축으로 봄"},
            ],
            "좁아진 뒤에 가격이 한쪽으로 나가기도 합니다. 어느 쪽인지는 밴드 폭만으로 알 수 없고, 이미 상단 밖으로 나간 경우는 수축 점수를 주지 않습니다.",
            "밴드 값은 일봉 종가 20개와 그 표준편차로 계산했습니다.",
            source,
        ),
        "rsi": _explain(
            "rsi",
            "RSI",
            "RSI는 최근 14일 동안 오른 폭과 내린 폭을 비교한 0~100 숫자입니다. 70이 넘으면 보통 과열, 30 아래는 과매도로 부릅니다. 프리런은 70 넘는 종목을 후보로 두지 않습니다.",
            [
                {"label": "오늘 기준 RSI", "value": f"{m['rsi']:.1f}" if m["rsi"] == m["rsi"] else "계산 불가"},
                {"label": "5거래일 전", "value": f"{m['rsi_5ago']:.1f}" if m["rsi_5ago"] == m["rsi_5ago"] else "계산 불가"},
                {"label": "회복 신호 기준", "value": "43~60이고, 5일 전보다 2포인트 이상 높을 것"},
                {"label": "제외 기준", "value": "72 이상"},
            ],
            "바닥에서 막 돌아 올라오는 50 전후를 '아직 안 뜨거운 회복'으로 봅니다. 이미 70을 넘으면 오르기 전이 아니라 오른 뒤로 봅니다.",
            "와일더 방식으로 14일 평균 상승폭·하락폭을 나눴습니다.",
            source,
        ),
        "macd": _explain(
            "macd",
            "MACD",
            "MACD는 12일 평균에서 26일 평균을 뺀 값입니다. 신호선은 그 값을 다시 9일 평균 낸 것입니다. 막대는 둘의 차이입니다.",
            [
                {"label": "MACD", "value": f"{m['macd']:.4f}" if m["macd"] == m["macd"] else "계산 불가"},
                {"label": "신호선", "value": f"{m['macd_signal']:.4f}" if m["macd_signal"] == m["macd_signal"] else "계산 불가"},
                {"label": "막대", "value": f"{m['macd_hist']:.4f}" if m["macd_hist"] == m["macd_hist"] else "계산 불가"},
            ],
            "막대가 0 위에서 커지면 짧은 평균이 긴 평균보다 빨라진 상태입니다. 프리런 점수에는 넣지 않고, 차트에서 참고로만 보여 줍니다.",
            "일봉 종가의 지수이동평균으로 계산했습니다. 급등 확률 숫자는 아닙니다.",
            source,
        ),
        "obv": _explain(
            "obv",
            "OBV",
            "가격이 전일보다 오르면 그날 거래량을 더하고, 내리면 뺍니다. 가격은 그대로인데 이 누적만 늘면 매수 쪽이 더 체결된 날로 해석합니다.",
            [
                {"label": "20일 OBV 변화 ÷ 하루 평균 거래량", "value": f"{m['obv_norm']:+.2f}" if m["obv_norm"] == m["obv_norm"] else "계산 불가", "note": "0.30 이상이고 가격이 잠잠할 때 신호"},
                {"label": "20거래일 수익률", "value": pct(m["ret_20"])},
            ],
            "거래량 누적과 가격이 어긋나 있는지 보려는 숫자입니다. 0.30은 '20일 동안 평균 거래량 6일치 정도가 순매수 방향으로 쌓임'에 해당합니다.",
            "일봉 종가 방향과 거래량으로 계산했습니다.",
            source,
        ),
    }


def public_card(row: dict) -> dict:
    timing = row["timing"]
    return {
        "symbol": row["symbol"],
        "code": row["code"],
        "name": row["name"],
        "market": row["market"],
        "currency": row["currency"],
        "price": row["price"],
        "change": row["change"],
        "change_pct": row["change_pct"],
        "volume": row["volume"],
        "value20": row["value20"],
        "vol_ratio": row["vol_ratio"],
        "score": row["score"],
        "probability": row.get("probability"),
        "calibrated_probability": row.get("calibrated_probability"),
        "threshold": row.get("threshold"),
        "bucket": row.get("bucket"),
        "baseline_hit_rate": row.get("baseline_hit_rate"),
        "contributions": [
            {
                "feature": item["feature"],
                "label": item["label"],
                "value": item["value"],
                "median": item["median"],
                "delta": item["delta"],
                "text": item["text"],
                "explain": item["explain"],
            }
            for item in row.get("contributions") or []
        ],
        "plan": None if not row.get("plan") else {key: value for key, value in row["plan"].items() if key != "lines"},
        "status": row["status"],
        "signal_date": row["signal_date"],
        "demoted_at": row["demoted_at"],
        "demote_reason": row["demote_reason"],
        "gain_since_signal": row["gain_since_signal"],
        "timing": {
            "label": timing.get("label"),
            "detail": timing.get("detail"),
            "probability": timing.get("probability"),
            "sample_n": timing.get("sample_n"),
            "bucket_note": timing.get("bucket_note"),
            "window_start": timing.get("window_start"),
            "window_end": timing.get("window_end"),
            "windows": timing.get("windows"),
            "available": timing.get("available"),
            "explain": timing.get("explain"),
        },
        "tags": row["tags"],
        "explain_score": row["explain_score"],
        "explain_timing": row["explain_timing"],
        "spark": row["spark"],
        "source": row["source"],
        "price_source": row["price_source"],
        "price_time": row["price_time"],
        "signal_bar_date": row["signal_bar_date"],
        "dropped_today": row["dropped_today"],
    }


def build_why(row: dict, indices: list[dict], articles: list[dict], investors: dict | None) -> dict:
    m = row["metrics"]
    currency = row["currency"]
    direction = "상승" if row["change_pct"] > 0.0005 else "하락" if row["change_pct"] < -0.0005 else "보합"
    factors = []
    factors.append(
        {
            "title": f"오늘 가격은 {direction}",
            "detail": (
                f"현재가 {px(row['price'], currency)}, 전일 대비 {px(row['change'], currency)} ({pct(row['change_pct'])}). "
                f"5거래일 {pct(m['ret_5'])}, 20거래일 {pct(m['ret_20'])}."
            ),
            "url": None,
            "source": row["price_source"],
        }
    )
    index_id = "NASDAQ" if row["market"] == "US" else ("KOSDAQ" if row["market"] == "KOSDAQ" else "KOSPI")
    index = next((item for item in indices if item.get("id") == index_id and item.get("price") is not None), None)
    if index:
        same = (index["change_pct"] or 0) * row["change_pct"] > 0
        factors.append(
            {
                "title": f"{index['name']}와 {'같은 방향' if same else '다른 방향'}",
                "detail": (
                    f"{index['name']} {index['price']:,.2f}, 등락 {pct(index['change_pct'])}. "
                    f"이 종목은 {pct(row['change_pct'])}. "
                    + ("지수와 같이 움직인 날로 볼 수 있습니다." if same else "지수와 반대로 움직였습니다. 지수만으로 설명되지 않습니다.")
                ),
                "url": None,
                "source": index["source"],
            }
        )
    if investors and investors.get("available") and investors.get("rows"):
        latest = investors["rows"][0]
        factors.append(
            {
                "title": f"투자자 수급 ({latest['date']} 마감)",
                "detail": (
                    f"외국인 순매수 {num(latest['foreign_net'])}주, 기관 {num(latest['institution_net'])}주, "
                    f"개인 {num(latest['individual_net'])}주. 외인소진율 {latest['foreign_ratio']:.2f}%. "
                    "오늘 장중 수급이 아니라 가장 최근 확정일입니다."
                    if latest["foreign_ratio"] is not None
                    else "순매수 수량이 있습니다. 지분율은 없습니다."
                ),
                "url": investors.get("source_url"),
                "source": investors.get("source"),
            }
        )
    elif row["market"] == "US":
        factors.append(
            {
                "title": "투자자 수급 데이터 없음",
                "detail": "외국인·기관·개인 순매수는 한국거래소 기준입니다. 미국 종목에는 같은 숫자가 없습니다.",
                "url": None,
                "source": "해당 없음",
            }
        )
    matched = []
    for article in articles:
        names = {item["name"] for item in article.get("related") or []}
        text = article.get("title") or ""
        if row["name"] in text or row["name"] in names or any(alias and alias in text for alias in []):
            matched.append(article)
    # company news already filtered; also keep ones that mention the name
    if not matched:
        matched = [a for a in articles if row["name"] in (a.get("title") or "")]
    if matched:
        up_news = sum(1 for a in matched if a["sentiment"] == "positive")
        down_news = sum(1 for a in matched if a["sentiment"] == "negative")
        factors.append(
            {
                "title": f"이름 들어간 최근 기사 {len(matched)}건",
                "detail": (
                    f"제목 기준 호재 단어가 더 많은 기사 {up_news}건, 악재 단어가 더 많은 기사 {down_news}건. "
                    "가격이 기사 때문에 움직였다고 단정하지 않습니다."
                ),
                "url": matched[0]["url"],
                "source": matched[0]["source"],
            }
        )
    else:
        factors.append(
            {
                "title": "직접 연결되는 기사 없음",
                "detail": "방금 모은 뉴스 제목에서 이 종목 이름을 찾지 못했습니다. 없는 이유를 만들어 적지 않습니다.",
                "url": None,
                "source": "RSS",
            }
        )
    factors.append(
        {
            "title": "기술 지표 위치",
            "detail": (
                f"20일선 이격 {pct(m['dist_ma20'])}, RSI {m['rsi']:.1f}, "
                f"밴드 폭 백분위 {m['bw_rank']*100:.0f}%, 거래량비 {m['vol_ratio']:.2f}배. "
                f"신호 기준 일봉은 {row['signal_bar_date']}입니다."
            ),
            "url": None,
            "source": row["source"],
        }
    )
    return {
        "direction": direction,
        "lead": (
            f"{row['name']}은 전일 대비 {pct(row['change_pct'])}입니다. "
            "아래에서 같이 움직인 숫자만 모았습니다. 원인 하나를 찍어 말하지 않습니다."
        ),
        "factors": factors,
        "articles": [
            {
                "title": a["title"],
                "url": a["url"],
                "source": a["source"],
                "published_at": a["published_at"],
                "sentiment": a["sentiment"],
                "summary": a["summary"],
                "explain": a["explain"],
            }
            for a in matched[:5]
        ],
    }


def forecast_block(row: dict, backtest: dict) -> dict:
    ml = backtest.get("ml") or {}
    prob = row.get("probability")
    ml_view = {
        "available": bool(ml.get("available")),
        "probability": prob,
        "threshold": ml.get("threshold"),
        "threshold_reason": ml.get("threshold_reason"),
        "train_end": ml.get("train_end"),
        "test_start": ml.get("test_start"),
        "test_end": ml.get("test_end"),
        "test_n": ml.get("test_n"),
        "baseline_hit_rate": ml.get("baseline_hit_rate"),
        "precision_at_threshold": ml.get("precision_at_threshold"),
        "precision_at_50": ml.get("precision_at_50"),
        "alerts": ml.get("alerts"),
        "top_quintile_n": ml.get("top_quintile_n"),
        "top_quintile_hit_rate": ml.get("top_quintile_hit_rate"),
        "reason": ml.get("reason"),
        "bucket": row.get("bucket"),
    }
    if row["status"] == "candidate":
        headline = "아직 급등 전으로 보고, 모델이 고른 과거 사례의 +7% 도달 시점을 예상 시기로 씁니다."
    elif row["status"] == "demoted":
        headline = "이 종목은 후보에서 빠졌습니다. 빠진 이유의 숫자가 전망보다 앞입니다."
    else:
        headline = "지금 확률은 검증으로 정한 기준보다 낮거나, 이미 급등한 상태입니다. 후보는 아닙니다."
    return {
        "headline": headline,
        "timing": public_card(row)["timing"],
        "ml": ml_view,
        "explain": row["explain_timing"],
    }


def backtest_public(backtest: dict) -> dict:
    ml = backtest.get("ml") or {}
    def pack(bucket):
        n = bucket.get("n") or 0
        return {
            "n": n,
            "hit10": bucket.get("hit10") or 0,
            "hit10_rate": ((bucket.get("hit10") or 0) / n) if n else 0,
            "windows": window_table(bucket),
        }
    return {
        "sample_start": backtest.get("sample_start"),
        "sample_end": backtest.get("sample_end"),
        "target": "모델은 10거래일 삼중 장벽. 신호별 빈도는 종가 +7%가 30거래일 안에 처음 온 시점입니다.",
        "baseline": pack(backtest.get("baseline") or {}),
        "candidates": pack(backtest.get("candidates") or {}),
        "by_signal": {sid: pack(bucket) for sid, bucket in (backtest.get("by_signal") or {}).items()},
        "ml": {
            key: value
            for key, value in ml.items()
            if key not in {"model", "medians", "isotonic", "logit", "scaler"}
        },
        "note": "학습 라벨은 10거래일 안에 손절보다 목표가 먼저인지입니다. 목표는 +7%와 +1.5×ATR 중 작은 쪽, 손절은 −5%와 −1×ATR 중 작은 쪽이고, 같은 봉에서 둘 다 닿으면 손절로 셉니다. 종가 +7%는 비교용으로만 남깁니다. 외국인·기관 수급은 최근 며칠만 공개되어 학습에 넣지 않습니다.",
    }


def _positive(value) -> bool:
    return isinstance(value, (int, float)) and value == value and value > 0


def apply_exclusions(rows: dict, flags: dict | None = None) -> dict:
    """Drop SPACs, sub-1000 KRW names, the least liquid fifth, and halt/warning flags.

    A missing trading value is not treated as zero.
    """
    flags = flags or {}
    grouped: dict[str, list[float]] = {}
    for row in rows.values():
        if row.get("status") == "skip":
            continue
        if _positive(row.get("value20")):
            grouped.setdefault(row.get("currency") or "KRW", []).append(float(row["value20"]))
    floors = {currency: float(np.percentile(values, 20)) for currency, values in grouped.items() if len(values) >= 5}
    excluded = []
    for row in rows.values():
        if row.get("status") == "skip":
            continue
        reasons = []
        name = row.get("name") or ""
        if "스팩" in name or "기업인수목적" in name:
            reasons.append("스팩·기업인수목적")
        if row.get("currency") == "KRW" and _positive(row.get("price")) and float(row["price"]) < 1000:
            reasons.append("1000원 미만")
        flag = flags.get(row.get("symbol"))
        if flag:
            reasons.append(str(flag))
        floor = floors.get(row.get("currency") or "KRW")
        value = row.get("value20")
        if floor and _positive(value) and float(value) < floor:
            reasons.append("20일 평균 거래대금 하위 20%")
        if reasons:
            row["status"] = "excluded"
            row["exclude_reasons"] = reasons
            excluded.append({"symbol": row.get("symbol"), "name": name, "reasons": reasons})
    return {
        "count": len(excluded),
        "floors": floors,
        "names": excluded[:12],
    }
