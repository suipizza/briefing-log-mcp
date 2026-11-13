"""MCP 서버를 프로세스 안에서 띄워 실제 도구 호출로 검증한다. 샘플 CSV(실제 브리핑 12일치)를 임시 DB에 넣어 쓴다."""
import sqlite3

import pytest
from mcp import Client

from briefing_mcp import db


@pytest.fixture(autouse=True)
def sample_db(tmp_path, monkeypatch):
    path = tmp_path / "briefings.db"
    monkeypatch.setenv("BRIEFING_DB", str(path))
    db.load_csv(path=path)
    return path


async def call(name, args=None):
    from briefing_mcp.server import server
    async with Client(server) as c:
        return await c.call_tool(name, args or {})


def rows(result):
    return result.structured_content["result"]


@pytest.mark.anyio
async def test_tools_listed():
    from briefing_mcp.server import server
    async with Client(server) as c:
        names = {t.name for t in (await c.list_tools()).tools}
    assert names == {"recent_briefings", "state_summary", "etf_flow_streaks", "query_sql"}


@pytest.mark.anyio
async def test_recent_briefings_sorted_desc():
    r = rows(await call("recent_briefings", {"days": 3}))
    assert [x["date"] for x in r] == ["2026-11-13", "2026-11-12", "2026-11-11"]


@pytest.mark.anyio
async def test_state_summary_counts_all_days():
    r = rows(await call("state_summary"))
    assert sum(x["days"] for x in r) == 12
    assert r[0]["state"] == "혼조" and r[0]["days"] == 5


@pytest.mark.anyio
async def test_etf_streaks_skip_unconfirmed_days():
    r = rows(await call("etf_flow_streaks"))
    assert sum(x["days"] for x in r) == 10  # 미반영 2일 제외
    assert {"dir": "유출", "start": "2026-11-02", "end": "2026-11-04", "days": 3, "total_musd": -1157.5} in r


@pytest.mark.anyio
async def test_query_sql_select_ok():
    r = rows(await call("query_sql", {"sql": "SELECT date FROM briefings WHERE us10y_chg_1d_bp >= 10 ORDER BY date"}))
    assert [x["date"] for x in r] == ["2026-11-11", "2026-11-13"]


@pytest.mark.anyio
@pytest.mark.parametrize("sql", [
    "DELETE FROM briefings",
    "UPDATE briefings SET btc_price = 0",
    "SELECT 1; DROP TABLE briefings",
    "WITH x AS (SELECT 1) DELETE FROM briefings",
    "ATTACH DATABASE '/tmp/x.db' AS x",
    "PRAGMA query_only = OFF",
])
async def test_query_sql_rejects_writes(sql, sample_db):
    res = await call("query_sql", {"sql": sql})
    assert res.is_error
    con = sqlite3.connect(sample_db)
    assert con.execute("SELECT COUNT(*) FROM briefings").fetchone()[0] == 12


def test_notion_page_to_row():
    from briefing_mcp.sync_notion import page_to_row
    page = {"properties": {
        "날짜": {"date": {"start": "2026-11-13"}},
        "BTC 가격": {"number": 71423.3},
        "CVD·OI 해석": {"select": {"name": "신규 숏 주도 하락"}},
        "수급": {"select": None},
        "한줄 판단": {"rich_text": [{"plain_text": "위험회피 "}, {"plain_text": "장"}]},
    }}
    row = page_to_row(page)
    assert row["date"] == "2026-11-13" and row["btc_price"] == 71423.3
    assert row["cvd_oi_tag"] == "신규 숏 주도 하락" and row["flow_tag"] is None
    assert row["one_liner"] == "위험회피 장"
