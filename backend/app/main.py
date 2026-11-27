"""PreRun API. Real prices only; a failed source becomes an error, never a filled-in number."""

from __future__ import annotations

import asyncio
import logging
import math
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import assemble, ledger, news, regime, sectors, sources
from .calendar_util import KST, now_kst, session_state
from .engine import (
    SIGNAL_NAME,
    add_context_features,
    attach_level_stats,
    attach_probabilities,
    build_backtest,
    compute_features,
    detect_geometry,
    scan_history,
    series_indicators,
)
from .universe import BY_SYMBOL, UNIVERSE

log = logging.getLogger("prerun")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

state = {
    "status": "warming",
    "error": None,
    "frames": {},
    "rows": {},
    "backtest": None,
    "quotes": {},
    "indices": [],
    "news": {"items": [], "errors": ["아직 불러오는 중입니다."], "updated_at": None, "mode": "규칙"},
    "errors": [],
    "updated_at": None,
    "news_at": 0.0,
    "sectors": {"status": "warming", "industries": [], "themes": [], "error": None, "updated_at": None},
    "flags": {},
    "regime": {"available": False, "weak": False, "badge": "국면 데이터 없음", "missing": [], "applied_threshold": None, "cap": None},
    "freshness": {"ok": True, "warnings": []},
    "risk": {"count": 0, "names": [], "floors": {}},
    "ledger": {"headline": "기록 시작됨", "closed": 0, "open": 0, "d20": {}, "d60": {}},
    "kospi_dates": [],
}
lock = asyncio.Lock()


def sanitize(value):
    if isinstance(value, dict):
        return {k: sanitize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize(v) for v in value]
    if isinstance(value, (np.floating, float)):
        value = float(value)
        return None if not math.isfinite(value) else value
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    return value


def _prepare_frame(meta: dict, payload: dict) -> dict:
    bars, dropped = sources.drop_partial_bar(payload["bars"], meta["market"])
    df = compute_features(bars)
    return {
        "df": df,
        "days": [],
        "source": payload["source"],
        "stale": bool(payload.get("stale")),
        "dropped_today": dropped,
        "error": payload.get("error"),
    }


async def _quotes(client, frames: dict) -> dict:
    codes = [meta["code"] for meta in UNIVERSE if meta["market"] != "US" and meta["symbol"] in frames]
    quotes = {}
    if codes:
        try:
            live = await sources.fetch_kr_quotes(client, codes)
            for meta in UNIVERSE:
                if meta["code"] in live:
                    quotes[meta["symbol"]] = live[meta["code"]]
        except Exception as exc:
            log.warning("KR quotes failed: %s", exc)
    us = [meta for meta in UNIVERSE if meta["market"] == "US" and meta["symbol"] in frames]
    if session_state("US") == "open" and us:
        async def one(meta):
            try:
                bars = await sources.fetch_us_chart(client, meta["symbol"], "5d", "1d")
                if len(bars) < 2:
                    return meta["symbol"], None
                price = bars[-1]["c"]
                prev = bars[-2]["c"]
                return meta["symbol"], {
                    "price": price,
                    "prev_close": prev,
                    "change": price - prev,
                    "change_pct": (price - prev) / prev if prev else 0,
                    "volume": bars[-1]["v"],
                    "source": "Yahoo Finance chart API",
                    "time": now_kst().isoformat(),
                }
            except Exception:
                return meta["symbol"], None
        pairs = await asyncio.gather(*(one(meta) for meta in us))
        for symbol, quote in pairs:
            if quote:
                quotes[symbol] = quote
    return quotes


def _assemble(frames, backtest, quotes):
    rows = {}
    errors = []
    for meta in UNIVERSE:
        frame = frames.get(meta["symbol"])
        if not frame:
            continue
        try:
            rows[meta["symbol"]] = assemble.classify_stock(meta, frame, backtest, quotes.get(meta["symbol"]))
        except Exception as exc:
            log.exception("classify %s", meta["symbol"])
            errors.append({"symbol": meta["symbol"], "message": str(exc)})
    return rows, errors


async def full_refresh() -> None:
    async with sources._client() as client:
        sem = asyncio.Semaphore(6)

        async def one(meta):
            async with sem:
                try:
                    payload = await sources.load_daily(client, meta)
                    return meta, payload, None
                except Exception as exc:
                    return meta, None, f"{meta['name']}: {exc}"

        fetched = await asyncio.gather(*(one(meta) for meta in UNIVERSE))
        indices = await sources.fetch_indices(client)
    errors = [{"symbol": meta["symbol"], "message": err} for meta, payload, err in fetched if err]
    payloads = [(meta, payload) for meta, payload, err in fetched if payload]
    if not payloads:
        async with lock:
            state["status"] = "error"
            state["error"] = "시세를 한 종목도 받지 못했습니다. 숫자를 만들지 않았습니다."
            state["errors"] = errors
        return

    kospi_bars: list[dict] = []
    kosdaq_bars: list[dict] = []
    nasdaq_bars: list[dict] = []
    fx_bars: list[dict] = []
    sector_of: dict = {}
    flags: dict = {}
    async with sources._client() as client:
        try:
            kospi_bars = await sources.fetch_index_daily(client, "^KS11", "KOSPI")
        except Exception:
            log.exception("KOSPI history failed")
        try:
            kosdaq_bars = await sources.fetch_index_daily(client, "^KQ11", "KOSDAQ")
        except Exception:
            log.exception("KOSDAQ history failed")
        try:
            nasdaq_bars = await sources.fetch_index_daily(client, "^IXIC", "US")
        except Exception:
            log.exception("NASDAQ history failed")
        try:
            fx_bars = await sources.fetch_index_daily(client, "KRW=X", "US")
        except Exception:
            log.exception("USD/KRW history failed")
        try:
            sector_of = await sources.load_sector_map(client, [meta for meta, _payload in payloads])
        except Exception:
            log.exception("sector map failed")
        try:
            flags = await sources.fetch_trade_flags(client, [meta for meta, _payload in payloads])
        except Exception:
            log.exception("trade flags failed")

    def compute():
        frames = {}
        for meta, payload in payloads:
            frames[meta["symbol"]] = _prepare_frame(meta, payload)
        market_of = {meta["symbol"]: meta["market"] for meta, _payload in payloads}
        add_context_features(frames, kospi_bars, nasdaq_bars, sector_of, market_of)
        per_symbol = []
        for symbol, frame in frames.items():
            frame["days"] = scan_history(frame["df"])
            per_symbol.append((symbol, frame["days"]))
        backtest = build_backtest(per_symbol)
        attach_probabilities(frames, backtest.get("ml") or {})
        attach_level_stats(frames, backtest.get("ml") or {})
        return frames, backtest

    frames, backtest = await asyncio.to_thread(compute)
    async with sources._client() as client:
        quotes = await _quotes(client, frames)
    rows, more_errors = _assemble(frames, backtest, quotes)
    risk = assemble.apply_exclusions(rows, flags)
    regime_info = regime.assess(kospi_bars, kosdaq_bars, fx_bars)
    warnings = []
    stale_names = [meta["name"] for meta, payload in payloads if payload.get("stale")]
    if stale_names:
        shown = ", ".join(stale_names[:6])
        suffix = " 외" if len(stale_names) > 6 else ""
        warnings.append(f"오래된 일봉을 그대로 둡니다. 빈 값을 0으로 바꾸지 않았습니다. {shown}{suffix}")
    if not kospi_bars:
        warnings.append("코스피 일봉을 받지 못했습니다.")
    if not kosdaq_bars:
        warnings.append("코스닥 일봉을 받지 못했습니다.")
    if not fx_bars:
        warnings.append("원/달러 일봉을 받지 못했습니다.")
    for item in indices:
        if item.get("error"):
            warnings.append(item["error"])
    kospi_dates = [str(bar["date"])[:10] for bar in kospi_bars if bar.get("date")]
    async with lock:
        state["frames"] = frames
        state["backtest"] = backtest
        state["quotes"] = quotes
        state["rows"] = rows
        state["indices"] = indices
        state["errors"] = errors + more_errors
        state["flags"] = flags
        state["regime"] = regime_info
        state["risk"] = risk
        state["freshness"] = {"ok": not warnings, "warnings": warnings}
        state["kospi_dates"] = kospi_dates
        state["status"] = "ready"
        state["error"] = None
        state["updated_at"] = now_kst().isoformat()
    candidates, _demoted = _lists()
    try:
        ledger.record(candidates)
        ledger.score(frames)
        state["ledger"] = ledger.summary(state.get("kospi_dates") or [])
    except Exception:
        log.exception("ledger failed")
    ranked = sorted(rows.values(), key=lambda r: r.get("calibrated_probability") if r.get("calibrated_probability") is not None else -1, reverse=True)
    ml = (state["backtest"] or {}).get("ml") or {}
    log.info(
        "ready symbols=%s candidates=%s demoted=%s threshold=%s",
        len(rows),
        len(candidates),
        sum(1 for r in rows.values() if r["status"] == "demoted"),
        ml.get("threshold"),
    )
    for row in ranked[:12]:
        log.info(
            "rank %s %s p=%s status=%s",
            row["symbol"],
            row["name"],
            None if row.get("probability") is None else round(row["probability"], 3),
            row["status"],
        )


async def live_refresh() -> None:
    async with lock:
        frames = state["frames"]
        backtest = state["backtest"]
        if state["status"] != "ready" or not frames or not backtest:
            return
    async with sources._client() as client:
        quotes = await _quotes(client, frames)
        indices = await sources.fetch_indices(client)
    rows, errors = _assemble(frames, backtest, quotes)
    async with lock:
        flags = dict(state.get("flags") or {})
    risk = assemble.apply_exclusions(rows, flags)
    warnings = list((state.get("freshness") or {}).get("warnings") or [])
    for item in indices:
        if item.get("error") and item["error"] not in warnings:
            warnings.append(item["error"])
    async with lock:
        state["quotes"] = quotes
        state["rows"] = rows
        state["indices"] = indices
        state["risk"] = risk
        state["freshness"] = {"ok": not warnings, "warnings": warnings}
        kept = [e for e in state["errors"] if e.get("symbol") not in frames]
        state["errors"] = kept + errors
        state["updated_at"] = now_kst().isoformat()
    try:
        candidates, _demoted = _lists()
        ledger.record(candidates)
        ledger.score(frames)
        state["ledger"] = ledger.summary(state.get("kospi_dates") or [])
    except Exception:
        log.exception("ledger failed")


async def refresh_sectors() -> None:
    codes = {
        row["code"]
        for row in state["rows"].values()
        if row.get("status") == "candidate" and row.get("market") != "US"
    }
    try:
        async with sources._client() as client:
            payload = await sectors.load_flows(client, codes)
    except Exception as exc:
        log.exception("sectors failed")
        payload = {"status": "error", "error": str(exc), "industries": [], "themes": [], "updated_at": now_kst().isoformat()}
    async with lock:
        state["sectors"] = payload


async def refresh_news() -> None:
    try:
        async with sources._client() as client:
            payload = await news.load_news(client)
        async with lock:
            state["news"] = payload
            state["news_at"] = datetime.now().timestamp()
    except Exception as exc:
        log.warning("news failed: %s", exc)


async def loop() -> None:
    try:
        await full_refresh()
    except Exception as exc:
        log.exception("full refresh failed")
        async with lock:
            state["status"] = "error"
            state["error"] = str(exc)
    await refresh_news()
    asyncio.create_task(refresh_sectors())
    tick = 0
    while True:
        await asyncio.sleep(45)
        tick += 1
        try:
            if tick % 25 == 0:
                await full_refresh()
            else:
                await live_refresh()
        except Exception:
            log.exception("refresh failed")
        if tick % 4 == 0:
            await refresh_news()
        if tick % 12 == 0:
            asyncio.create_task(refresh_sectors())


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(loop())
    yield
    task.cancel()


app = FastAPI(title="PreRun", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _lists():
    rows = list(state["rows"].values())
    ml = (state.get("backtest") or {}).get("ml") or {}
    regime_info = dict(state.get("regime") or {})
    threshold = ml.get("threshold")
    cutoff = threshold
    cap = None
    if regime_info.get("weak") and isinstance(threshold, float):
        cutoff = min(0.90, round(float(threshold) + 0.10, 4))
        cap = 3
    regime_info["applied_threshold"] = cutoff
    regime_info["cap"] = cap
    state["regime"] = regime_info

    def passes(row: dict) -> bool:
        if row.get("status") != "candidate":
            return False
        if not isinstance(cutoff, float):
            return False
        score = row.get("calibrated_probability")
        return isinstance(score, float) and score >= cutoff

    candidates = sorted(
        (r for r in rows if passes(r)),
        key=lambda r: r.get("calibrated_probability") if r.get("calibrated_probability") is not None else -1,
        reverse=True,
    )
    if cap is not None:
        candidates = candidates[:cap]
    demoted = sorted(
        (r for r in rows if r["status"] == "demoted"),
        key=lambda r: r["demoted_at"] or "",
        reverse=True,
    )
    return candidates, demoted


@app.get("/health")
async def health():
    return {"status": state["status"], "updated_at": state["updated_at"], "error": state["error"]}


@app.get("/indices")
async def indices():
    return {"items": sanitize(state["indices"]), "updated_at": state["updated_at"], "status": state["status"]}


@app.get("/news")
async def news_feed():
    return sanitize(state["news"])


@app.get("/screener")
async def screener():
    if state["status"] != "ready":
        return {
            "status": state["status"],
            "error": state["error"],
            "candidates": [],
            "demoted": [],
            "updated_at": state["updated_at"],
        }
    candidates, demoted = _lists()
    scanned = len(state["frames"])
    return sanitize(
        {
            "status": "ready",
            "updated_at": state["updated_at"],
            "signal_session": {
                "kr": session_state("KOSPI"),
                "us": session_state("US"),
                "note": "장중에는 오늘 미완성 일봉을 빼고, 현재가로 급등 여부와 모델 입력만 다시 계산합니다.",
            },
            "scanned": scanned,
            "universe": len(UNIVERSE),
            "errors": state["errors"],
            "candidates": [assemble.public_card(r) for r in candidates],
            "demoted": [assemble.public_card(r) for r in demoted],
            "backtest": assemble.backtest_public(state["backtest"]),
            "passed": len(candidates),
            "tracked": [_tracked(row) for row in state["rows"].values() if row.get("status") != "skip"],
            "regime": state.get("regime"),
            "risk": state.get("risk"),
            "freshness": state.get("freshness"),
            "ledger": state.get("ledger"),
        }
    )


def _tracked(row: dict) -> dict:
    plan = row.get("plan") or {}
    return {
        "symbol": row["symbol"],
        "name": row["name"],
        "code": row["code"],
        "market": row["market"],
        "currency": row["currency"],
        "price": row["price"],
        "change": row["change"],
        "change_pct": row["change_pct"],
        "probability": row.get("probability"),
        "status": row["status"],
        "demoted_at": row.get("demoted_at"),
        "demote_reason": row.get("demote_reason"),
        "stop": plan.get("stop"),
        "target": plan.get("target"),
    }


@app.get("/sectors")
async def sector_flow():
    return sanitize(state["sectors"])


@app.get("/stock/{symbol}")
async def stock(symbol: str, range: str = "3m"):
    if state["status"] != "ready":
        raise HTTPException(503, "시세를 아직 계산하는 중입니다.")
    meta = BY_SYMBOL.get(symbol)
    row = state["rows"].get(symbol)
    frame = state["frames"].get(symbol)
    if not meta or not row or frame is None:
        raise HTTPException(404, "이 종목은 프리런이 매일 계산하는 목록에 없습니다.")
    range = range if range in {"1d", "1w", "1m", "3m", "1y"} else "3m"
    chart_error = None
    bars = []
    try:
        async with sources._client() as client:
            if meta["market"] == "US":
                if range == "1d":
                    bars = await sources.fetch_us_chart(client, symbol, "1d", "2m")
                elif range == "1w":
                    bars = await sources.fetch_us_chart(client, symbol, "5d", "15m")
                else:
                    width = {"1m": 22, "3m": 66, "1y": 252}[range]
                    bars = sources.slice_daily_bars(_daily(frame), width)
            else:
                if range in {"1d", "1w"}:
                    end = datetime.now(KST)
                    start = end - (timedelta(hours=8) if range == "1d" else timedelta(days=7))
                    if range == "1d":
                        start = end.replace(hour=9, minute=0, second=0, microsecond=0)
                    bars = await sources.fetch_kr_intraday(client, meta["code"], start, end)
                else:
                    width = {"1m": 22, "3m": 66, "1y": 252}[range]
                    bars = sources.slice_daily_bars(_daily(frame), width)
            if meta["market"] == "US":
                orderbook = {
                    "available": False,
                    "reason": "미국 종목 호가는 무료 시세에 없습니다. 없는 호가를 만들지 않습니다.",
                    "sells": [],
                    "buys": [],
                    "total_sell": None,
                    "total_buy": None,
                    "source": None,
                    "source_url": f"https://finance.yahoo.com/quote/{symbol}",
                }
                investors = {
                    "available": False,
                    "reason": "외국인·기관·개인 순매수는 한국거래소 기준입니다. 미국 종목에는 같은 구분이 없습니다.",
                    "rows": [],
                    "source": None,
                    "source_url": f"https://finance.yahoo.com/quote/{symbol}",
                }
            else:
                try:
                    orderbook = await sources.fetch_orderbook(client, meta["code"])
                except Exception as exc:
                    orderbook = {
                        "available": False,
                        "reason": f"호가를 가져오지 못했습니다. {exc}",
                        "sells": [],
                        "buys": [],
                        "total_sell": None,
                        "total_buy": None,
                    }
                try:
                    investors = await sources.fetch_investors(client, meta["code"])
                except Exception as exc:
                    investors = {
                        "available": False,
                        "reason": f"투자자별 매매동향을 가져오지 못했습니다. {exc}",
                        "rows": [],
                    }
            company = await news.company_news(client, meta["name"])
    except Exception as exc:
        chart_error = str(exc)
        orderbook = {"available": False, "reason": f"시세 부가 자료를 가져오지 못했습니다. {exc}", "sells": [], "buys": []}
        investors = {"available": False, "reason": str(exc), "rows": []}
        company = []
    if not bars and not chart_error:
        chart_error = "이 구간의 봉 데이터를 소스에서 받지 못했습니다."
    indicators = series_indicators(bars) if bars else {}
    lines = list((row.get("plan") or {}).get("lines") or [])
    if bars:
        lines.extend(detect_geometry(bars, meta["currency"]))
    articles = list(company)
    for item in state["news"].get("items") or []:
        if any(rel.get("symbol") == symbol for rel in item.get("related") or []) or meta["name"] in item.get("title", ""):
            if all(a["url"] != item["url"] for a in articles):
                articles.append(item)
    why = assemble.build_why(row, state["indices"], articles, investors if investors.get("available") else None)
    card = assemble.public_card(row)
    card.update(
        {
            "chart_range": range,
            "bars": bars,
            "indicator_series": indicators,
            "lines": lines,
            "chart_error": chart_error,
            "orderbook": orderbook,
            "investors": investors,
            "buy_sell": {
                "available": False,
                "reason": "당일 매수체결과 매도체결을 나눈 숫자는 네이버·야후 무료 API에 없습니다. 호가 잔량만 표시합니다.",
            },
            "why": why,
            "forecast": assemble.forecast_block(row, state["backtest"]),
            "signals": [
                {
                    "id": sid,
                    "name": SIGNAL_NAME[sid],
                    "fired": bool(row["decision"]["fired"][sid]),
                    "contribution": row["decision"]["parts"][sid],
                    "explain": row["explains"][sid],
                }
                for sid in SIGNAL_NAME
            ],
            "indicator_explain": assemble.indicator_explains(row["metrics"], meta["currency"], row["source"]),
            "session": session_state(meta["market"]),
        }
    )
    return sanitize(card)


def _daily(frame) -> list[dict]:
    df = frame["df"]
    rows = []
    for _, row in df.iterrows():
        rows.append(
            {
                "date": str(row["date"])[:10],
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
            }
        )
    return rows
