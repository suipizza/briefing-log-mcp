"""SQLite 저장소. 쓰기는 이 파일의 upsert/load 함수만, MCP 서버는 읽기 전용 연결만 쓴다."""
from __future__ import annotations

import csv
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = Path(__file__).with_name("schema.sql")
DEFAULT_DB = ROOT / "data" / "briefings.db"
SAMPLE_CSV = ROOT / "data" / "sample_briefings.csv"

COLUMNS = [
    "date", "btc_price", "btc_chg_24h_pct", "oi_chg_24h_pct", "oi_chg_7d_pct", "funding_rate_pct",
    "futures_cvd_btc", "spot_cvd_btc", "etf_net_flow_musd", "us10y_pct", "us10y_chg_1d_bp",
    "dxy_chg_1d_pct", "nasdaq_chg_1d_pct", "flow_tag", "risk_tag", "position_tag", "cvd_oi_tag",
    "run_status", "flow_data_status", "one_liner",
]
TEXT_COLUMNS = {"date", "flow_tag", "risk_tag", "position_tag", "cvd_oi_tag", "run_status", "flow_data_status", "one_liner"}


def db_path() -> Path:
    return Path(os.getenv("BRIEFING_DB", DEFAULT_DB))


def connect_rw(path: Path | None = None) -> sqlite3.Connection:
    path = path or db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    return con


def connect_ro(path: Path | None = None) -> sqlite3.Connection:
    """읽기 전용 연결. 파일을 mode=ro로 열어서 SQL로도 쓰기가 불가능하다."""
    path = path or db_path()
    if not path.exists():
        raise FileNotFoundError(f"DB가 없습니다: {path} (python -m briefing_mcp.load_sample 먼저 실행)")
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _coerce(col: str, value):
    if value in ("", None):
        return None
    return value if col in TEXT_COLUMNS else float(value)


def upsert(con: sqlite3.Connection, rows: list[dict]) -> int:
    placeholders = ", ".join("?" for _ in COLUMNS)
    updates = ", ".join(f"{c}=excluded.{c}" for c in COLUMNS if c != "date")
    sql = (f"INSERT INTO briefings ({', '.join(COLUMNS)}) VALUES ({placeholders}) "
           f"ON CONFLICT(date) DO UPDATE SET {updates}, synced_at=datetime('now')")
    con.executemany(sql, [[_coerce(c, r.get(c)) for c in COLUMNS] for r in rows])
    con.commit()
    return len(rows)


def load_csv(csv_path: Path = SAMPLE_CSV, path: Path | None = None) -> int:
    with open(csv_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    with connect_rw(path) as con:
        return upsert(con, rows)
