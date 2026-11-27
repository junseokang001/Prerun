"""Sector and theme flow from Naver. Missing series stay empty instead of being guessed."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import httpx

from .calendar_util import KST
from .sources import parse_ko_number


async def _get(client: httpx.AsyncClient, url: str) -> dict:
    response = await client.get(url)
    response.raise_for_status()
    return response.json()


def _rate(raw) -> float | None:
    value = parse_ko_number(raw)
    if value is None:
        return None
    return value / 100.0


async def _pages(client: httpx.AsyncClient, kind: str, page_size: int) -> list[dict]:
    groups: list[dict] = []
    page = 1
    total = None
    while page <= 4:
        body = await _get(client, f"https://m.stock.naver.com/api/stocks/{kind}?page={page}&pageSize={page_size}")
        groups.extend(body.get("groups") or [])
        total = body.get("totalCount") or total
        if total is not None and page * page_size >= int(total):
            break
        if not body.get("groups"):
            break
        page += 1
    return groups


async def _detail(client: httpx.AsyncClient, kind: str, number: int) -> dict | None:
    try:
        return await _get(client, f"https://m.stock.naver.com/api/stocks/{kind}/{number}?page=1&pageSize=8")
    except Exception:
        return None


async def _leader_paths(client: httpx.AsyncClient, code: str) -> tuple[float | None, float | None, str | None]:
    end = datetime.now(KST)
    start = end - timedelta(days=70)
    url = (
        "https://api.stock.naver.com/chart/domestic/item/"
        f"{code}/day?startDateTime={start.strftime('%Y%m%d')}000000&endDateTime={end.strftime('%Y%m%d')}235959"
    )
    try:
        rows = await _get(client, url)
    except Exception:
        return None, None, "대장주 일봉을 받지 못했습니다."
    if not isinstance(rows, list) or len(rows) < 6:
        return None, None, "대장주 일봉이 6거래일보다 짧습니다."
    closes = [float(row["closePrice"]) for row in rows if row.get("closePrice")]
    if len(closes) < 6:
        return None, None, "대장주 종가가 비어 있습니다."
    week = closes[-1] / closes[-6] - 1
    month = closes[-1] / closes[-22] - 1 if len(closes) >= 22 else None
    note = "1주·1달은 업종 지수가 아니라 대장주 일봉 수익률입니다. 네이버 업종 차트는 빈 목록입니다."
    return week, month, note


async def _leader_flow(client: httpx.AsyncClient, code: str, name: str) -> dict:
    try:
        rows = await _get(client, f"https://m.stock.naver.com/api/stock/{code}/trend?pageSize=1")
        if not rows:
            raise RuntimeError("빈 응답")
        row = rows[0]
        raw = str(row.get("bizdate") or "")
        day = f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}" if len(raw) == 8 else raw
        return {
            "available": True,
            "name": name,
            "date": day,
            "foreign_net": parse_ko_number(row.get("foreignerPureBuyQuant")),
            "institution_net": parse_ko_number(row.get("organPureBuyQuant")),
            "reason": "업종 합산이 아니라 대장주 최근 확정일 순매수입니다.",
        }
    except Exception as exc:
        return {
            "available": False,
            "name": name,
            "date": None,
            "foreign_net": None,
            "institution_net": None,
            "reason": f"업종 합산 수급은 없고, 대장주 수급도 받지 못했습니다. {exc}",
        }


def _stock_row(stock: dict, candidate_codes: set[str]) -> dict:
    code = str(stock.get("itemCode") or "")
    change = _rate(stock.get("fluctuationsRatio"))
    direction = ((stock.get("compareToPreviousPrice") or {}).get("name") or "").upper()
    if change is not None and direction == "FALLING":
        change = -abs(change)
    elif change is not None and direction == "RISING":
        change = abs(change)
    exchange = (stock.get("stockExchangeType") or {}).get("name")
    return {
        "code": code,
        "name": stock.get("stockName"),
        "price": parse_ko_number(stock.get("closePrice")),
        "change_pct": change,
        "value": parse_ko_number(stock.get("accumulatedTradingValueRaw") or stock.get("accumulatedTradingValue")),
        "market_value": parse_ko_number(stock.get("marketValueRaw") or stock.get("marketValue")),
        "candidate": code in candidate_codes,
        "market": "KOSDAQ" if exchange == "KOSDAQ" or str(stock.get("sosok")) == "1" else "KOSPI",
    }


async def _hydrate(client: httpx.AsyncClient, group: dict, kind: str, candidate_codes: set[str], deep: bool) -> dict:
    item = {
        "id": group.get("no"),
        "name": group.get("name"),
        "kind": "업종" if kind == "industry" else "테마",
        "count": group.get("totalCount"),
        "change_1d": _rate(group.get("changeRate")),
        "rise_count": group.get("riseCount"),
        "fall_count": group.get("fallCount"),
        "change_1w": None,
        "change_1m": None,
        "return_note": "네이버 업종·테마 목록은 당일 등락률만 줍니다.",
        "leader": None,
        "stocks": [],
        "value_today": None,
        "volume_surge": {
            "available": False,
            "reason": "업종 거래량이 20일 평균의 몇 배인지는 이 API에 없습니다. 보여 주는 금액은 구성 종목 당일 거래대금 합입니다.",
        },
        "foreign": {
            "available": False,
            "reason": "업종 전체 외국인·기관 순매수는 무료 API에 없습니다.",
            "foreign_net": None,
            "institution_net": None,
            "date": None,
            "name": None,
        },
        "has_candidate": False,
        "source": "네이버 금융 업종·테마",
    }
    if not deep:
        return item
    detail = await _detail(client, kind, int(group["no"]))
    stocks = [_stock_row(stock, candidate_codes) for stock in (detail or {}).get("stocks") or []]
    stocks = [stock for stock in stocks if stock["code"]]
    item["stocks"] = stocks
    item["has_candidate"] = any(stock["candidate"] for stock in stocks)
    valued = [stock["value"] for stock in stocks if isinstance(stock["value"], (int, float))]
    item["value_today"] = sum(valued) if valued else None
    leaders = [stock for stock in stocks if isinstance(stock["market_value"], (int, float))]
    leader = max(leaders, key=lambda stock: stock["market_value"]) if leaders else (stocks[0] if stocks else None)
    item["leader"] = leader
    if leader:
        week, month, note = await _leader_paths(client, leader["code"])
        item["change_1w"] = week
        item["change_1m"] = month
        item["return_note"] = note
        item["foreign"] = await _leader_flow(client, leader["code"], leader["name"])
    elif detail is None:
        item["return_note"] = "구성 종목을 받지 못해 대장주와 1주·1달 수익률이 없습니다."
    return item


async def load_flows(client: httpx.AsyncClient, candidate_codes: set[str]) -> dict:
    try:
        industries = await _pages(client, "industry", 80)
        head = await _get(client, "https://m.stock.naver.com/api/stocks/theme?page=1&pageSize=12")
        total = int(head.get("totalCount") or 0)
        last_page = max(1, (total + 11) // 12)
        tail = (
            await _get(client, f"https://m.stock.naver.com/api/stocks/theme?page={last_page}&pageSize=12")
            if last_page > 1
            else {"groups": []}
        )
        themes = (head.get("groups") or []) + (tail.get("groups") or [])
    except Exception as exc:
        return {
            "status": "error",
            "error": f"업종·테마 목록을 받지 못했습니다. {exc}",
            "industries": [],
            "themes": [],
            "updated_at": datetime.now(KST).isoformat(),
        }
    industries = sorted(industries, key=lambda group: _rate(group.get("changeRate")) if _rate(group.get("changeRate")) is not None else -999, reverse=True)
    chosen_i = []
    seen = set()
    for group in industries[:8] + list(reversed(industries[-8:])):
        if group.get("no") in seen:
            continue
        seen.add(group.get("no"))
        chosen_i.append(group)
    chosen_t = []
    seen_t = set()
    for group in themes:
        if group.get("no") in seen_t:
            continue
        seen_t.add(group.get("no"))
        chosen_t.append(group)
    hydrated_i = list(await asyncio.gather(*(_hydrate(client, group, "industry", candidate_codes, True) for group in chosen_i)))
    hydrated_t = list(await asyncio.gather(*(_hydrate(client, group, "theme", candidate_codes, True) for group in chosen_t[:10])))
    expanded = {item["id"] for item in hydrated_i}
    known = {stock["code"] for item in hydrated_i for stock in item["stocks"]}
    for code in list(candidate_codes):
        if code in known:
            continue
        try:
            body = await _get(client, f"https://m.stock.naver.com/api/stock/{code}/integration")
        except Exception:
            continue
        number = body.get("industryCode")
        if not number or number in expanded:
            continue
        match = next((group for group in industries if group.get("no") == number), {"no": number, "name": str(number), "changeRate": None, "totalCount": None})
        extra = await _hydrate(client, match, "industry", candidate_codes, True)
        hydrated_i.append(extra)
        expanded.add(number)
        known.update(stock["code"] for stock in extra["stocks"])
    rest = [await _hydrate(client, group, "industry", candidate_codes, False) for group in industries if group.get("no") not in expanded]
    combined = hydrated_i + rest
    combined.sort(key=lambda item: item["change_1d"] if item["change_1d"] is not None else -999, reverse=True)
    hydrated_t.sort(key=lambda item: item["change_1d"] if item["change_1d"] is not None else -999, reverse=True)
    return {
        "status": "ready",
        "error": None,
        "updated_at": datetime.now(KST).isoformat(),
        "industries": combined,
        "themes": hydrated_t,
        "source": "네이버 금융 업종·테마",
    }
