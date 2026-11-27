"""Market headlines from public RSS, with a keyword summary and an optional LLM pass."""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from urllib.parse import quote
from xml.etree import ElementTree as ET

import httpx

from .calendar_util import KST
from .universe import BY_SYMBOL, names_for_match

FEEDS = [
    ("구글 뉴스", "https://news.google.com/rss/search?q=%EC%BD%94%EC%8A%A4%ED%94%BC+OR+%EC%BD%94%EC%8A%A4%EB%8B%A5+OR+%EC%A6%9D%EC%8B%9C&hl=ko&gl=KR&ceid=KR:ko"),
    ("매일경제", "https://www.mk.co.kr/rss/30100041/"),
    ("서울경제", "https://www.sedaily.com/rss/finance"),
    ("연합뉴스", "https://www.yna.co.kr/rss/economy.xml"),
    ("CNBC", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664"),
]

POS = ["급등", "수주", "호재", "상향", "흑자", "최대", "신고가", "성장", "계약", "인수", "호실적", "상회", "개선", "반등", "확대", "beat", "upgrade", "rally", "surge", "gain", "soar", "raises", "record"]
NEG = ["급락", "악재", "하향", "적자", "감소", "리콜", "조사", "하락", "위기", "부진", "손실", "축소", "우려", "제재", "폭락", "miss", "downgrade", "fall", "drop", "plunge", "lawsuit", "cut", "slump"]

SECTORS = [
    (["반도체", "HBM", "하이닉스", "파운드리", "삼성전자"], "반도체"),
    (["2차전지", "배터리", "양극재", "에코프로", "LG에너지"], "2차전지"),
    (["바이오", "임상", "셀트리온", "알테오젠"], "바이오"),
    (["금리", "FOMC", "연준", "국채", "yield"], "금리"),
    (["환율", "달러", "원/달러"], "환율"),
    (["조선", "방산", "한화에어로", "중공업"], "조선·방산"),
    (["자동차", "현대차", "기아"], "자동차"),
]


def _sentiment(title: str) -> tuple[str, list[str]]:
    found_pos = [w for w in POS if w.lower() in title.lower()]
    found_neg = [w for w in NEG if w.lower() in title.lower()]
    if len(found_pos) > len(found_neg):
        return "positive", found_pos
    if len(found_neg) > len(found_pos):
        return "negative", found_neg
    if found_pos or found_neg:
        return "neutral", found_pos + found_neg
    return "neutral", []


def _sectors(text: str) -> list[str]:
    found = []
    for words, name in SECTORS:
        if any(word.lower() in text.lower() for word in words):
            found.append(name)
    return found


def _hit(name: str, text: str) -> bool:
    if len(name) < 3:
        return re.search(rf"(?<![A-Za-z0-9가-힣]){re.escape(name)}(?![A-Za-z0-9가-힣])", text) is not None
    return name in text


def _related(text: str) -> list[dict]:
    hits = []
    seen = set()
    for name, symbol in names_for_match():
        if name and _hit(name, text) and symbol not in seen:
            seen.add(symbol)
            meta = BY_SYMBOL[symbol]
            hits.append({"symbol": symbol, "name": meta["name"], "market": meta["market"]})
    return hits[:4]


def _clean(text: str | None) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_time(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(KST).isoformat()
    except (TypeError, ValueError):
        return None


def _summary(title: str, sentiment: str, keywords: list[str], sectors: list[str], related: list[dict]) -> str:
    label = {"positive": "호재 쪽", "negative": "악재 쪽", "neutral": "중립"}[sentiment]
    bits = [f"{label} · 단어: {', '.join(keywords)}" if keywords else f"{label} · 제목에 호재·악재 단어 없음"]
    if sectors:
        bits.append("업종 " + ", ".join(sectors))
    if related:
        bits.append("종목 " + ", ".join(item["name"] for item in related))
    return " · ".join(bits)


def _explain(title: str, sentiment: str, keywords: list[str], source: str, published: str | None) -> dict:
    label = {"positive": "호재", "negative": "악재", "neutral": "중립"}[sentiment]
    icon = {"positive": "빨간 ▲", "negative": "파란 ▼", "neutral": "회색 대시"}[sentiment]
    return {
        "id": f"news-{abs(hash(title)) % 10**8}",
        "title": f"뉴스 심리 · {label}",
        "plain": f"이 표시는 기자가 단정한 호재/악재가 아닙니다. 제목에 자주 쓰이는 단어를 세어 {icon}을 붙인 것입니다. 오를지 내릴지는 알려 주지 않습니다.",
        "values": [
            {"label": "제목", "value": title},
            {"label": "판별", "value": label},
            {"label": "센 단어", "value": ", ".join(keywords) if keywords else "없음"},
            {"label": "출처", "value": source},
            {"label": "시각", "value": published or "시각 없음"},
        ],
        "why": "급등 후보와 같은 이름이 제목에 있으면 그 종목으로 이어 줍니다. 기사가 있다고 그 종목이 오르는 것은 아닙니다.",
        "evidence": "심리 점수는 모델 적중률이 아니라 제목 단어 개수입니다. 긍정 단어가 더 많으면 ▲, 부정 단어가 더 많으면 ▼, 같거나 없으면 회색 대시입니다.",
        "source": source,
    }


def parse_feed(xml_text: str, source_name: str) -> list[dict]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    items = []
    for node in root.iter("item"):
        title = _clean(node.findtext("title"))
        link = (node.findtext("link") or "").strip()
        if not title or not link:
            continue
        source_node = node.find("source")
        source = source_name
        if source_node is not None and source_node.text:
            source = f"{source_name} · {_clean(source_node.text)}"
        published = _parse_time(node.findtext("pubDate"))
        description = _clean(node.findtext("description"))
        blob = f"{title} {description}"
        sentiment, keywords = _sentiment(blob)
        sectors = _sectors(blob)
        related = _related(blob)
        items.append(
            {
                "title": title,
                "url": link,
                "source": source,
                "published_at": published,
                "sentiment": sentiment,
                "keywords": keywords,
                "sectors": sectors,
                "related": related,
                "summary": _summary(title, sentiment, keywords, sectors, related),
                "summary_mode": "규칙",
                "explain": _explain(title, sentiment, keywords, source, published),
            }
        )
    return items


async def _llm_summaries(items: list[dict]) -> None:
    key = os.environ.get("OPENAI_API_KEY")
    if not key or not items:
        return
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    lines = [f"{i}. {item['title']}" for i, item in enumerate(items[:20])]
    prompt = (
        "한국 개인투자자용으로 각 헤드라인을 한 문장으로 요약하라. "
        "JSON 배열만 반환. 각 원소는 {\"i\":번호,\"summary\":\"한국어 한 문장\",\"sentiment\":\"positive|negative|neutral\"}. "
        "기사에 없는 숫자나 종목을 만들지 마라.\n" + "\n".join(lines)
    )
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.post(
                f"{base}/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": model,
                    "temperature": 0.2,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        match = re.search(r"\[.*\]", content, re.S)
        if not match:
            return
        import json

        parsed = json.loads(match.group(0))
        for row in parsed:
            idx = row.get("i")
            if not isinstance(idx, int) or not 0 <= idx < len(items):
                continue
            summary = str(row.get("summary") or "").strip()
            if summary:
                items[idx]["summary"] = summary
                items[idx]["summary_mode"] = "LLM"
            sentiment = row.get("sentiment")
            if sentiment in {"positive", "negative", "neutral"}:
                items[idx]["sentiment"] = sentiment
                items[idx]["explain"] = _explain(
                    items[idx]["title"],
                    sentiment,
                    items[idx]["keywords"],
                    items[idx]["source"],
                    items[idx]["published_at"],
                )
    except Exception:
        return


async def load_news(client: httpx.AsyncClient) -> dict:
    collected = []
    errors = []
    for name, url in FEEDS:
        try:
            response = await client.get(url)
            response.raise_for_status()
            collected.extend(parse_feed(response.text, name))
        except Exception as exc:
            errors.append(f"{name}: {exc}")
    dedup = []
    seen = set()
    for item in collected:
        key = item["title"]
        if key in seen:
            continue
        seen.add(key)
        dedup.append(item)
    dedup.sort(key=lambda item: item["published_at"] or "", reverse=True)
    dedup = dedup[:40]
    await _llm_summaries(dedup)
    return {
        "items": dedup,
        "errors": errors,
        "updated_at": datetime.now(KST).isoformat(),
        "mode": "LLM" if os.environ.get("OPENAI_API_KEY") else "규칙",
    }


async def company_news(client: httpx.AsyncClient, name: str) -> list[dict]:
    url = (
        "https://news.google.com/rss/search?q="
        + quote(f"{name} 주가")
        + "&hl=ko&gl=KR&ceid=KR:ko"
    )
    try:
        response = await client.get(url)
        response.raise_for_status()
        items = parse_feed(response.text, "구글 뉴스")
        items.sort(key=lambda item: item["published_at"] or "", reverse=True)
        return items[:6]
    except Exception:
        return []
