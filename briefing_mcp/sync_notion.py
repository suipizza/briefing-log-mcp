"""노션 브리핑 DB → SQLite 동기화.

노션은 조회(data source query)만 한다. 쓰기·검색·삭제 API는 호출하지 않는다.
필요한 환경변수: NOTION_TOKEN (읽기 권한만 준 integration), NOTION_DATA_SOURCE_ID
"""
from __future__ import annotations

import os

import requests
from dotenv import load_dotenv

from briefing_mcp.db import connect_rw, db_path, upsert

API = "https://api.notion.com/v1"
VERSION = "2025-09-03"

# 노션 속성 이름 → SQLite 컬럼
NUMBER_PROPS = {
    "BTC 가격": "btc_price", "BTC 24h 변동률(%)": "btc_chg_24h_pct", "OI 24h 변화율(%)": "oi_chg_24h_pct",
    "OI 7일 변화율(%)": "oi_chg_7d_pct", "펀딩비(%)": "funding_rate_pct", "선물 CVD 변화(BTC)": "futures_cvd_btc",
    "현물 CVD 변화(BTC)": "spot_cvd_btc", "ETF 순유입($M)": "etf_net_flow_musd", "US10Y(%)": "us10y_pct",
    "US10Y 1일(bp)": "us10y_chg_1d_bp", "DXY 1일(%)": "dxy_chg_1d_pct", "나스닥 변동률(%)": "nasdaq_chg_1d_pct",
}
SELECT_PROPS = {
    "수급": "flow_tag", "위험선호": "risk_tag", "포지션": "position_tag", "CVD·OI 해석": "cvd_oi_tag",
    "실행 상태": "run_status", "수급 데이터 상태": "flow_data_status",
}
TEXT_PROPS = {"한줄 판단": "one_liner"}


def _plain(rich: list[dict]) -> str | None:
    text = "".join(t.get("plain_text", "") for t in rich)
    return text or None


def page_to_row(page: dict) -> dict | None:
    props = page["properties"]
    date = (props.get("날짜", {}).get("date") or {}).get("start")
    if not date:
        return None
    row: dict = {"date": date[:10]}
    for name, col in NUMBER_PROPS.items():
        row[col] = props.get(name, {}).get("number")
    for name, col in SELECT_PROPS.items():
        sel = props.get(name, {}).get("select")
        row[col] = sel["name"] if sel else None
    for name, col in TEXT_PROPS.items():
        row[col] = _plain(props.get(name, {}).get("rich_text", []))
    return row


def fetch_pages(token: str, data_source_id: str) -> list[dict]:
    headers = {"Authorization": f"Bearer {token}", "Notion-Version": VERSION, "Content-Type": "application/json"}
    pages, cursor = [], None
    while True:
        body = {"page_size": 100, **({"start_cursor": cursor} if cursor else {})}
        r = requests.post(f"{API}/data_sources/{data_source_id}/query", headers=headers, json=body, timeout=30)
        r.raise_for_status()
        data = r.json()
        pages += data["results"]
        if not data.get("has_more"):
            return pages
        cursor = data["next_cursor"]


def main() -> None:
    load_dotenv()
    token, ds = os.getenv("NOTION_TOKEN", ""), os.getenv("NOTION_DATA_SOURCE_ID", "")
    if not token or not ds:
        raise SystemExit("NOTION_TOKEN, NOTION_DATA_SOURCE_ID를 .env에 넣어 주세요.")
    rows = [r for r in map(page_to_row, fetch_pages(token, ds)) if r]
    with connect_rw() as con:
        n = upsert(con, rows)
    print(f"{n} rows → {db_path()}")


if __name__ == "__main__":
    main()
