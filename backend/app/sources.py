"""Free market data. Naver Finance for Korea, Yahoo chart API for the US and NASDAQ."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx

from .calendar_util import KST, session_state

CACHE = Path(__file__).resolve().parent.parent / "data" / "cache"
DAILY_DIR = CACHE / "daily"
DAILY_DIR.mkdir(parents=True, exist_ok=True)

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
}

DAILY_TTL = 20 * 60


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(headers=UA, timeout=httpx.Timeout(25.0), follow_redirects=True)


def parse_ko_number(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "").replace("%", "").replace("+", "")
    if text in {"", "-", "N/A"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _cache_path(symbol: str) -> Path:
    safe = symbol.replace("/", "_")
    return DAILY_DIR / f"{safe}.json"


def read_daily_cache(symbol: str) -> dict | None:
    path = _cache_path(symbol)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None


def write_daily_cache(symbol: str, payload: dict) -> None:
    _cache_path(symbol).write_text(json.dumps(payload, ensure_ascii=False))


def cache_fresh(payload: dict | None, ttl: int = DAILY_TTL) -> bool:
    if not payload or not payload.get("bars"):
        return False
    return time.time() - float(payload.get("fetched_at", 0)) < ttl


def _bars_from_naver(rows: list[dict]) -> list[dict]:
    bars = []
    for row in rows:
        raw = str(row.get("localDate") or "")
        if len(raw) != 8:
            continue
        close = row.get("closePrice")
        if close is None:
            continue
        bars.append(
            {
                "date": f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}",
                "open": float(row.get("openPrice") or close),
                "high": float(row.get("highPrice") or close),
                "low": float(row.get("lowPrice") or close),
                "close": float(close),
                "volume": float(row.get("accumulatedTradingVolume") or 0),
            }
        )
    bars.sort(key=lambda b: b["date"])
    dedup: dict[str, dict] = {}
    for bar in bars:
        dedup[bar["date"]] = bar
    return list(dedup.values())


def _bars_from_yahoo(payload: dict, market: str) -> list[dict]:
    result = payload["chart"]["result"][0]
    timestamps = result.get("timestamp") or []
    quote = result["indicators"]["quote"][0]
    tz = ZoneInfo("America/New_York") if market == "US" else KST
    bars = []
    for i, ts in enumerate(timestamps):
        close = quote["close"][i]
        if close is None or float(close) <= 0:
            continue
        d = datetime.fromtimestamp(ts, tz).date().isoformat()
        bars.append(
            {
                "date": d,
                "open": float(quote["open"][i] or close),
                "high": float(quote["high"][i] or close),
                "low": float(quote["low"][i] or close),
                "close": float(close),
                "volume": float(quote["volume"][i] or 0),
            }
        )
    dedup: dict[str, dict] = {}
    for bar in bars:
        dedup[bar["date"]] = bar
    return list(dedup.values())


async def fetch_kr_daily(client: httpx.AsyncClient, code: str) -> list[dict]:
    start = "20240101"
    end = datetime.now(KST).strftime("%Y%m%d")
    url = (
        "https://api.stock.naver.com/chart/domestic/item/"
        f"{code}/day?startDateTime={start}000000&endDateTime={end}235959"
    )
    response = await client.get(url)
    response.raise_for_status()
    return _bars_from_naver(response.json())


async def fetch_index_daily(client: httpx.AsyncClient, symbol: str, market: str) -> list[dict]:
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{quote(symbol, safe='')}?range=2y&interval=1d&includePrePost=false"
    )
    response = await client.get(url)
    response.raise_for_status()
    return _bars_from_yahoo(response.json(), market)


async def load_sector_map(client: httpx.AsyncClient, metas: list[dict]) -> dict:
    path = CACHE / "sector_map.json"
    if path.exists() and time.time() - path.stat().st_mtime < 7 * 86400:
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            pass
    mapping = {}

    async def one(meta: dict):
        if meta["market"] == "US":
            return meta["symbol"], "US"
        try:
            response = await client.get(f"https://m.stock.naver.com/api/stock/{meta['code']}/integration")
            response.raise_for_status()
            body = response.json()
            return meta["symbol"], str(body.get("industryCode") or "KR")
        except Exception:
            return meta["symbol"], "KR"

    for meta in metas:
        symbol, sector = await one(meta)
        mapping[symbol] = sector
    path.write_text(json.dumps(mapping))
    return mapping


async def fetch_trade_flags(client: httpx.AsyncClient, metas: list[dict]) -> dict[str, str | None]:
    """Halt / non-tradable flags from Naver basic. A failed lookup is not treated as a halt."""

    async def one(meta: dict) -> tuple[str, str | None]:
        if meta.get("market") == "US":
            return meta["symbol"], None
        try:
            response = await client.get(f"https://m.stock.naver.com/api/stock/{meta['code']}/basic")
            response.raise_for_status()
            body = response.json()
        except Exception:
            return meta["symbol"], None
        reasons = []
        stop = body.get("tradeStopType") or {}
        stop_name = str(stop.get("name") or "")
        if stop_name and stop_name != "TRADING":
            reasons.append(str(stop.get("text") or stop_name))
        status = str(body.get("tradableStatus") or "")
        code = str(body.get("tradableStatusCode") or "")
        if status and status != "tradable":
            reasons.append("매매불가")
        if code and code != "ok":
            reasons.append(code)
        blob = json.dumps(body, ensure_ascii=False)
        for word in ("관리종목", "투자경고", "투자주의", "투자위험", "환기종목", "거래정지"):
            if word in blob and word not in reasons:
                reasons.append(word)
        return meta["symbol"], (" · ".join(reasons) if reasons else None)

    pairs = await asyncio.gather(*(one(meta) for meta in metas))
    return {symbol: flag for symbol, flag in pairs}


async def fetch_us_daily(client: httpx.AsyncClient, symbol: str) -> list[dict]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=2y&interval=1d&includePrePost=false"
    response = await client.get(url)
    response.raise_for_status()
    return _bars_from_yahoo(response.json(), "US")


async def load_daily(client: httpx.AsyncClient, meta: dict, force: bool = False) -> dict:
    cached = read_daily_cache(meta["symbol"])
    if not force and cache_fresh(cached):
        return cached
    try:
        if meta["market"] == "US":
            bars = await fetch_us_daily(client, meta["symbol"])
            source = "Yahoo Finance chart API"
        else:
            bars = await fetch_kr_daily(client, meta["code"])
            source = "네이버 금융 차트 API"
        if len(bars) < 80:
            raise RuntimeError(f"일봉이 {len(bars)}개뿐이라 지표를 계산하지 않습니다.")
        if any(not bar.get("close") or float(bar["close"]) <= 0 for bar in bars[-5:]):
            raise RuntimeError("최근 일봉 종가가 비어 있어 0으로 바꾸지 않고 거절했습니다.")
        payload = {
            "symbol": meta["symbol"],
            "source": source,
            "fetched_at": time.time(),
            "bars": bars,
            "stale": False,
        }
        write_daily_cache(meta["symbol"], payload)
        return payload
    except Exception as exc:
        if cached and cached.get("bars"):
            cached = dict(cached)
            cached["stale"] = True
            cached["error"] = str(exc)
            return cached
        raise


def drop_partial_bar(bars: list[dict], market: str) -> tuple[list[dict], bool]:
    """Drop today's unfinished daily bar so volume ratios are not cut in half mid-session."""
    if not bars:
        return bars, False
    today = datetime.now(KST if market != "US" else ZoneInfo("America/New_York")).date().isoformat()
    if bars[-1]["date"] == today and session_state(market) == "open":
        return bars[:-1], True
    return bars, False


async def fetch_kr_quotes(client: httpx.AsyncClient, codes: list[str]) -> dict[str, dict]:
    url = "https://polling.finance.naver.com/api/realtime?query=SERVICE_ITEM:" + ",".join(codes)
    response = await client.get(url)
    response.raise_for_status()
    body = json.loads(response.content.decode("euc-kr", "replace"))
    out: dict[str, dict] = {}
    areas = body.get("result", {}).get("areas", [])
    for area in areas:
        for row in area.get("datas") or []:
            code = row.get("cd")
            price = row.get("nv")
            prev = row.get("sv") or row.get("pcv")
            if not code or not price or not prev:
                continue
            price = float(price)
            prev = float(prev)
            out[code] = {
                "price": price,
                "prev_close": prev,
                "change": price - prev,
                "change_pct": (price - prev) / prev if prev else 0.0,
                "volume": float(row.get("aq") or 0),
                "name": row.get("nm"),
                "source": "네이버 금융 실시간",
                "time": datetime.now(KST).isoformat(),
            }
    return out


async def fetch_indices(client: httpx.AsyncClient) -> list[dict]:
    items: list[dict] = []
    now = datetime.now(KST).isoformat()
    try:
        url = "https://polling.finance.naver.com/api/realtime?query=SERVICE_INDEX:KOSPI,KOSDAQ"
        response = await client.get(url)
        response.raise_for_status()
        body = json.loads(response.content.decode("euc-kr", "replace"))
        name_map = {"KOSPI": "코스피", "KOSDAQ": "코스닥"}
        for area in body.get("result", {}).get("areas", []):
            for row in area.get("datas") or []:
                code = row.get("cd")
                nv_raw = row.get("nv")
                cv_raw = row.get("cv")
                if nv_raw in (None, "") or cv_raw in (None, ""):
                    continue
                nv = float(nv_raw)
                cv = float(cv_raw)
                if nv <= 0:
                    continue
                level = nv / 100.0
                change = cv / 100.0
                prev = level - change
                items.append(
                    {
                        "id": code,
                        "name": name_map.get(code, code),
                        "price": level,
                        "change": change,
                        "change_pct": (change / prev) if prev else 0.0,
                        "source": "네이버 금융 실시간",
                        "updated_at": now,
                        "currency": "KRW",
                        "error": None,
                    }
                )
    except Exception as exc:
        for code, name in (("KOSPI", "코스피"), ("KOSDAQ", "코스닥")):
            items.append(
                {
                    "id": code,
                    "name": name,
                    "price": None,
                    "change": None,
                    "change_pct": None,
                    "source": "네이버 금융 실시간",
                    "updated_at": now,
                    "currency": "KRW",
                    "error": f"지수를 가져오지 못했습니다. {exc}",
                }
            )
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/%5EIXIC?range=5d&interval=1d"
        response = await client.get(url)
        response.raise_for_status()
        result = response.json()["chart"]["result"][0]
        meta = result["meta"]
        closes = [c for c in result["indicators"]["quote"][0]["close"] if c is not None]
        price = meta.get("regularMarketPrice") or (closes[-1] if closes else None)
        if price is None or float(price) <= 0:
            raise RuntimeError("나스닥 가격이 비어 있습니다.")
        price = float(price)
        prev = float(closes[-2]) if len(closes) >= 2 else None
        # If the last bar is a finished session and equals the printed price, previous is the bar before.
        if prev and abs(closes[-1] - price) / price < 0.0001 and len(closes) >= 2:
            prev = float(closes[-2])
        change = price - prev if prev else None
        items.append(
            {
                "id": "NASDAQ",
                "name": "나스닥",
                "price": price,
                "change": change,
                "change_pct": (change / prev) if prev else None,
                "source": "Yahoo Finance chart API (^IXIC)",
                "updated_at": now,
                "currency": "USD",
                "error": None,
            }
        )
    except Exception as exc:
        items.append(
            {
                "id": "NASDAQ",
                "name": "나스닥",
                "price": None,
                "change": None,
                "change_pct": None,
                "source": "Yahoo Finance chart API (^IXIC)",
                "updated_at": now,
                "currency": "USD",
                "error": f"나스닥을 가져오지 못했습니다. {exc}",
            }
        )
    return items


async def fetch_orderbook(client: httpx.AsyncClient, code: str) -> dict:
    url = f"https://m.stock.naver.com/api/stock/{code}/askingPrice"
    response = await client.get(url)
    response.raise_for_status()
    data = response.json()
    sells = []
    buys = []
    for row in data.get("sellInfo") or []:
        price = parse_ko_number(row.get("price"))
        count = parse_ko_number(row.get("count"))
        if price is None or count is None:
            continue
        sells.append({"price": price, "qty": count})
    for row in data.get("buyInfos") or data.get("buyInfo") or []:
        price = parse_ko_number(row.get("price"))
        count = parse_ko_number(row.get("count"))
        if price is None or count is None:
            continue
        buys.append({"price": price, "qty": count})
    sells.sort(key=lambda x: x["price"], reverse=True)
    buys.sort(key=lambda x: x["price"], reverse=True)
    return {
        "available": True,
        "source": "네이버 금융 호가",
        "source_url": f"https://m.stock.naver.com/domestic/stock/{code}/total",
        "updated_at": datetime.now(KST).isoformat(),
        "total_sell": parse_ko_number(data.get("totalSell")),
        "total_buy": parse_ko_number(data.get("totalBuy")),
        "sells": sells,
        "buys": buys,
        "reason": None,
    }


async def fetch_investors(client: httpx.AsyncClient, code: str) -> dict:
    url = f"https://m.stock.naver.com/api/stock/{code}/trend?pageSize=8"
    response = await client.get(url)
    response.raise_for_status()
    rows = []
    for row in response.json():
        raw = str(row.get("bizdate") or "")
        day = f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}" if len(raw) == 8 else raw
        rows.append(
            {
                "date": day,
                "foreign_net": parse_ko_number(row.get("foreignerPureBuyQuant")),
                "institution_net": parse_ko_number(row.get("organPureBuyQuant")),
                "individual_net": parse_ko_number(row.get("individualPureBuyQuant")),
                "foreign_ratio": parse_ko_number(row.get("foreignerHoldRatio")),
                "close": parse_ko_number(row.get("closePrice")),
                "volume": parse_ko_number(row.get("accumulatedTradingVolume")),
            }
        )
    return {
        "available": True,
        "source": "네이버 금융 투자자별 매매동향",
        "source_url": f"https://m.stock.naver.com/domestic/stock/{code}/total",
        "rows": rows,
        "ownership_note": "외국인 숫자는 네이버가 주는 외인소진율(%)입니다. 외국인 한도 대비 보유 비율이라 단순 지분율과 다를 수 있습니다. 기관·개인 지분율은 이 API에 없습니다.",
        "buy_sell_note": "당일 매수체결량·매도체결량 구분은 무료 API에 없습니다.",
        "reason": None,
    }


async def fetch_kr_intraday(client: httpx.AsyncClient, code: str, start: datetime, end: datetime) -> list[dict]:
    url = (
        "https://api.stock.naver.com/chart/domestic/item/"
        f"{code}/minute?startDateTime={start.strftime('%Y%m%d%H%M%S')}"
        f"&endDateTime={end.strftime('%Y%m%d%H%M%S')}"
    )
    response = await client.get(url)
    response.raise_for_status()
    rows = response.json()
    parsed = []
    for row in rows:
        raw = str(row.get("localDateTime") or "")
        if len(raw) < 12:
            continue
        close = row.get("currentPrice")
        if close is None:
            continue
        parsed.append(
            {
                "t": f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]} {raw[8:10]}:{raw[10:12]}",
                "acc": float(row.get("accumulatedTradingVolume") or 0),
                "o": float(row.get("openPrice") or close),
                "h": float(row.get("highPrice") or close),
                "l": float(row.get("lowPrice") or close),
                "c": float(close),
            }
        )
    parsed.sort(key=lambda x: x["t"])
    out = []
    prev = None
    for row in parsed:
        acc = row["acc"]
        vol = acc if prev is None or acc < prev else acc - prev
        prev = acc
        out.append({"t": row["t"], "o": row["o"], "h": row["h"], "l": row["l"], "c": row["c"], "v": vol})
    return out


async def fetch_us_chart(client: httpx.AsyncClient, symbol: str, range_: str, interval: str) -> list[dict]:
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?range={range_}&interval={interval}&includePrePost=false"
    )
    response = await client.get(url)
    response.raise_for_status()
    result = response.json()["chart"]["result"][0]
    timestamps = result.get("timestamp") or []
    quote = result["indicators"]["quote"][0]
    tz = ZoneInfo("America/New_York")
    out = []
    for i, ts in enumerate(timestamps):
        close = quote["close"][i]
        if close is None:
            continue
        dt = datetime.fromtimestamp(ts, tz)
        label = dt.strftime("%Y-%m-%d") if interval == "1d" else dt.strftime("%Y-%m-%d %H:%M")
        out.append(
            {
                "t": label,
                "o": float(quote["open"][i] or close),
                "h": float(quote["high"][i] or close),
                "l": float(quote["low"][i] or close),
                "c": float(close),
                "v": float(quote["volume"][i] or 0),
            }
        )
    return out


def slice_daily_bars(bars: list[dict], trading_days: int) -> list[dict]:
    cut = bars[-trading_days:]
    return [
        {"t": b["date"], "o": b["open"], "h": b["high"], "l": b["low"], "c": b["close"], "v": b["volume"]}
        for b in cut
    ]
