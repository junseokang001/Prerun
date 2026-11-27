"""Liquid names the screener scans. Detail pages exist only for these symbols."""

from __future__ import annotations

UNIVERSE: list[dict] = [
    # KOSPI
    {"symbol": "005930.KS", "code": "005930", "name": "삼성전자", "market": "KOSPI", "currency": "KRW", "aliases": ["삼전"]},
    {"symbol": "000660.KS", "code": "000660", "name": "SK하이닉스", "market": "KOSPI", "currency": "KRW", "aliases": ["하이닉스"]},
    {"symbol": "373220.KS", "code": "373220", "name": "LG에너지솔루션", "market": "KOSPI", "currency": "KRW", "aliases": ["LG엔솔"]},
    {"symbol": "207940.KS", "code": "207940", "name": "삼성바이오로직스", "market": "KOSPI", "currency": "KRW", "aliases": ["삼성바이오"]},
    {"symbol": "005380.KS", "code": "005380", "name": "현대차", "market": "KOSPI", "currency": "KRW", "aliases": ["현대자동차"]},
    {"symbol": "000270.KS", "code": "000270", "name": "기아", "market": "KOSPI", "currency": "KRW", "aliases": ["기아차"]},
    {"symbol": "068270.KS", "code": "068270", "name": "셀트리온", "market": "KOSPI", "currency": "KRW", "aliases": []},
    {"symbol": "005490.KS", "code": "005490", "name": "POSCO홀딩스", "market": "KOSPI", "currency": "KRW", "aliases": ["포스코홀딩스"]},
    {"symbol": "035420.KS", "code": "035420", "name": "NAVER", "market": "KOSPI", "currency": "KRW", "aliases": ["네이버"]},
    {"symbol": "035720.KS", "code": "035720", "name": "카카오", "market": "KOSPI", "currency": "KRW", "aliases": []},
    {"symbol": "105560.KS", "code": "105560", "name": "KB금융", "market": "KOSPI", "currency": "KRW", "aliases": ["KB금융지주"]},
    {"symbol": "055550.KS", "code": "055550", "name": "신한지주", "market": "KOSPI", "currency": "KRW", "aliases": []},
    {"symbol": "066570.KS", "code": "066570", "name": "LG전자", "market": "KOSPI", "currency": "KRW", "aliases": []},
    {"symbol": "006400.KS", "code": "006400", "name": "삼성SDI", "market": "KOSPI", "currency": "KRW", "aliases": []},
    {"symbol": "051910.KS", "code": "051910", "name": "LG화학", "market": "KOSPI", "currency": "KRW", "aliases": []},
    {"symbol": "003670.KS", "code": "003670", "name": "포스코퓨처엠", "market": "KOSPI", "currency": "KRW", "aliases": []},
    {"symbol": "012450.KS", "code": "012450", "name": "한화에어로스페이스", "market": "KOSPI", "currency": "KRW", "aliases": ["한화에어로"]},
    {"symbol": "329180.KS", "code": "329180", "name": "HD현대중공업", "market": "KOSPI", "currency": "KRW", "aliases": []},
    {"symbol": "267260.KS", "code": "267260", "name": "HD현대일렉트릭", "market": "KOSPI", "currency": "KRW", "aliases": []},
    {"symbol": "009150.KS", "code": "009150", "name": "삼성전기", "market": "KOSPI", "currency": "KRW", "aliases": []},
    {"symbol": "011070.KS", "code": "011070", "name": "LG이노텍", "market": "KOSPI", "currency": "KRW", "aliases": []},
    {"symbol": "042700.KS", "code": "042700", "name": "한미반도체", "market": "KOSPI", "currency": "KRW", "aliases": []},
    {"symbol": "003230.KS", "code": "003230", "name": "삼양식품", "market": "KOSPI", "currency": "KRW", "aliases": []},
    {"symbol": "028260.KS", "code": "028260", "name": "삼성물산", "market": "KOSPI", "currency": "KRW", "aliases": []},
    {"symbol": "096770.KS", "code": "096770", "name": "SK이노베이션", "market": "KOSPI", "currency": "KRW", "aliases": []},
    {"symbol": "015760.KS", "code": "015760", "name": "한국전력", "market": "KOSPI", "currency": "KRW", "aliases": ["한전"]},
    {"symbol": "034730.KS", "code": "034730", "name": "SK", "market": "KOSPI", "currency": "KRW", "aliases": []},
    {"symbol": "010130.KS", "code": "010130", "name": "고려아연", "market": "KOSPI", "currency": "KRW", "aliases": []},
    # KOSDAQ
    {"symbol": "247540.KQ", "code": "247540", "name": "에코프로비엠", "market": "KOSDAQ", "currency": "KRW", "aliases": []},
    {"symbol": "086520.KQ", "code": "086520", "name": "에코프로", "market": "KOSDAQ", "currency": "KRW", "aliases": []},
    {"symbol": "196170.KQ", "code": "196170", "name": "알테오젠", "market": "KOSDAQ", "currency": "KRW", "aliases": []},
    {"symbol": "028300.KQ", "code": "028300", "name": "HLB", "market": "KOSDAQ", "currency": "KRW", "aliases": []},
    {"symbol": "035900.KQ", "code": "035900", "name": "JYP Ent.", "market": "KOSDAQ", "currency": "KRW", "aliases": ["JYP", "JYP엔터"]},
    {"symbol": "041510.KQ", "code": "041510", "name": "에스엠", "market": "KOSDAQ", "currency": "KRW", "aliases": ["SM엔터"]},
    {"symbol": "263750.KQ", "code": "263750", "name": "펄어비스", "market": "KOSDAQ", "currency": "KRW", "aliases": []},
    {"symbol": "039030.KQ", "code": "039030", "name": "이오테크닉스", "market": "KOSDAQ", "currency": "KRW", "aliases": []},
    {"symbol": "058470.KQ", "code": "058470", "name": "리노공업", "market": "KOSDAQ", "currency": "KRW", "aliases": []},
    {"symbol": "403870.KQ", "code": "403870", "name": "HPSP", "market": "KOSDAQ", "currency": "KRW", "aliases": []},
    {"symbol": "214450.KQ", "code": "214450", "name": "파마리서치", "market": "KOSDAQ", "currency": "KRW", "aliases": []},
    {"symbol": "087010.KQ", "code": "087010", "name": "펩트론", "market": "KOSDAQ", "currency": "KRW", "aliases": []},
    {"symbol": "000250.KQ", "code": "000250", "name": "삼천당제약", "market": "KOSDAQ", "currency": "KRW", "aliases": []},
    {"symbol": "067310.KQ", "code": "067310", "name": "하나마이크론", "market": "KOSDAQ", "currency": "KRW", "aliases": []},
    {"symbol": "145020.KQ", "code": "145020", "name": "휴젤", "market": "KOSDAQ", "currency": "KRW", "aliases": []},
    # US
    {"symbol": "AAPL", "code": "AAPL", "name": "애플", "market": "US", "currency": "USD", "aliases": ["Apple"]},
    {"symbol": "MSFT", "code": "MSFT", "name": "마이크로소프트", "market": "US", "currency": "USD", "aliases": ["Microsoft"]},
    {"symbol": "NVDA", "code": "NVDA", "name": "엔비디아", "market": "US", "currency": "USD", "aliases": ["NVIDIA", "Nvidia"]},
    {"symbol": "AMZN", "code": "AMZN", "name": "아마존", "market": "US", "currency": "USD", "aliases": ["Amazon"]},
    {"symbol": "GOOGL", "code": "GOOGL", "name": "알파벳", "market": "US", "currency": "USD", "aliases": ["구글", "Google", "Alphabet"]},
    {"symbol": "META", "code": "META", "name": "메타", "market": "US", "currency": "USD", "aliases": ["Meta", "페이스북"]},
    {"symbol": "TSLA", "code": "TSLA", "name": "테슬라", "market": "US", "currency": "USD", "aliases": ["Tesla"]},
    {"symbol": "AMD", "code": "AMD", "name": "AMD", "market": "US", "currency": "USD", "aliases": []},
]

BY_SYMBOL = {row["symbol"]: row for row in UNIVERSE}


def names_for_match() -> list[tuple[str, str]]:
    """Longer aliases first so '삼성바이오로직스' wins over a shorter fragment."""
    pairs: list[tuple[str, str]] = []
    for row in UNIVERSE:
        pairs.append((row["name"], row["symbol"]))
        for alias in row["aliases"]:
            if len(alias) >= 2:
                pairs.append((alias, row["symbol"]))
    pairs.sort(key=lambda x: len(x[0]), reverse=True)
    return pairs
