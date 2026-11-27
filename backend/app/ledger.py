"""Paper ledger. Records the names we actually showed and scores them on later bars."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "data" / "ledger.sqlite"


def _connect() -> sqlite3.Connection:
    DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS picks (
            symbol TEXT NOT NULL,
            signal_date TEXT NOT NULL,
            name TEXT,
            market TEXT,
            currency TEXT,
            entry REAL,
            stop REAL,
            target REAL,
            probability REAL,
            status TEXT NOT NULL,
            resolved_on TEXT,
            return_pct REAL,
            recorded_at TEXT,
            PRIMARY KEY (symbol, signal_date)
        )
        """
    )
    return conn


def _finite(value) -> bool:
    return isinstance(value, (int, float)) and value == value and value > 0


def record(candidates: list[dict]) -> int:
    now = datetime.now(timezone.utc).isoformat()
    added = 0
    with _connect() as conn:
        for row in candidates:
            plan = row.get("plan") or {}
            entry = row.get("price")
            stop = plan.get("stop")
            target = plan.get("target")
            signal_date = row.get("signal_date")
            if not signal_date or not _finite(entry) or not _finite(stop) or not _finite(target):
                continue
            if float(stop) >= float(entry) or float(target) <= float(entry):
                continue
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO picks
                (symbol, signal_date, name, market, currency, entry, stop, target, probability, status, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)
                """,
                (
                    row.get("symbol"),
                    signal_date,
                    row.get("name"),
                    row.get("market"),
                    row.get("currency"),
                    float(entry),
                    float(stop),
                    float(target),
                    row.get("calibrated_probability"),
                    now,
                ),
            )
            added += cur.rowcount or 0
    return added


def score(frames: dict) -> None:
    with _connect() as conn:
        opens = conn.execute("SELECT * FROM picks WHERE status = 'open'").fetchall()
        for pick in opens:
            frame = frames.get(pick["symbol"])
            if not frame:
                continue
            df = frame.get("df")
            if df is None or len(df) < 2:
                continue
            dates = [str(value)[:10] for value in df["date"].tolist()]
            if pick["signal_date"] not in dates:
                continue
            start = dates.index(pick["signal_date"])
            entry = float(pick["entry"])
            stop = float(pick["stop"])
            target = float(pick["target"])
            status = "open"
            resolved_on = None
            ret = None
            future = list(range(start + 1, min(len(df), start + 11)))
            for offset in future:
                high = float(df.iloc[offset]["high"])
                low = float(df.iloc[offset]["low"])
                hit_stop = low <= stop
                hit_target = high >= target
                if hit_stop:
                    status = "stop_first"
                    resolved_on = dates[offset]
                    ret = stop / entry - 1
                    break
                if hit_target:
                    status = "target_first"
                    resolved_on = dates[offset]
                    ret = target / entry - 1
                    break
            if status == "open" and len(future) >= 10:
                close = float(df.iloc[future[-1]]["close"])
                if close > 0 and entry > 0:
                    status = "expired"
                    resolved_on = dates[future[-1]]
                    ret = close / entry - 1
            if status != "open":
                conn.execute(
                    "UPDATE picks SET status = ?, resolved_on = ?, return_pct = ? WHERE symbol = ? AND signal_date = ?",
                    (status, resolved_on, ret, pick["symbol"], pick["signal_date"]),
                )


def _window_stats(rows: list[sqlite3.Row]) -> dict:
    closed = [row for row in rows if row["status"] in {"target_first", "stop_first", "expired"}]
    n = len(closed)
    if n == 0:
        return {
            "n": 0,
            "open": sum(1 for row in rows if row["status"] == "open"),
            "hit_rate": None,
            "avg_return": None,
            "stop_first_rate": None,
            "target_n": 0,
            "stop_n": 0,
            "expired_n": 0,
        }
    target_n = sum(1 for row in closed if row["status"] == "target_first")
    stop_n = sum(1 for row in closed if row["status"] == "stop_first")
    expired_n = sum(1 for row in closed if row["status"] == "expired")
    returns = [float(row["return_pct"]) for row in closed if row["return_pct"] is not None]
    return {
        "n": n,
        "open": sum(1 for row in rows if row["status"] == "open"),
        "hit_rate": target_n / n,
        "avg_return": (sum(returns) / len(returns)) if returns else None,
        "stop_first_rate": stop_n / n,
        "target_n": target_n,
        "stop_n": stop_n,
        "expired_n": expired_n,
    }


def summary(trading_dates: list[str]) -> dict:
    dates = sorted({day for day in trading_dates if day})
    with _connect() as conn:
        rows = list(conn.execute("SELECT * FROM picks").fetchall())
    closed = [row for row in rows if row["status"] != "open"]

    def cutoff(n: int) -> str | None:
        if not dates:
            return None
        return dates[-n] if len(dates) >= n else dates[0]

    def in_window(n: int) -> list[sqlite3.Row]:
        start = cutoff(n)
        if start is None:
            return []
        return [row for row in rows if row["signal_date"] >= start]

    total_closed = len(closed)
    return {
        "headline": "기록 시작됨" if total_closed < 5 else "실전 기록",
        "closed": total_closed,
        "open": sum(1 for row in rows if row["status"] == "open"),
        "d20": _window_stats(in_window(20)),
        "d60": _window_stats(in_window(60)),
    }
