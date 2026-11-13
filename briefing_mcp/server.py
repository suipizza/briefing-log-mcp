"""브리핑 기록을 Claude가 조회·분석할 수 있게 여는 MCP 서버 (읽기 전용).

도구
- recent_briefings   최근 N일 브리핑 (숫자·태그·한 줄 판단)
- state_summary      시장 상태(CVD·OI 해석)별 일수와 평균 지표
- etf_flow_streaks   ETF 순유입/순유출 연속 구간 (윈도 함수)
- query_sql          SELECT 한 문장만 허용하는 읽기 전용 SQL
리소스
- briefing://schema  테이블 정의 (Claude가 SQL을 쓰기 전에 읽는다)

안전장치: DB를 mode=ro로 열고, query_only를 켜고, authorizer로 읽기 외 동작을 막는다.
"""
from __future__ import annotations

import sqlite3

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from briefing_mcp.db import SCHEMA, connect_ro

MAX_ROWS = 200

server = MCPServer(
    name="briefing-log",
    instructions=(
        "BTC 선물 데스크의 일일 마켓 브리핑 기록(SQLite)을 조회한다. "
        "자유 SQL이 필요하면 먼저 briefing://schema를 읽고 query_sql을 쓴다. 쓰기는 불가능하다."
    ),
)

_ALLOWED_ACTIONS = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}


def _authorizer(action, *_):
    return sqlite3.SQLITE_OK if action in _ALLOWED_ACTIONS else sqlite3.SQLITE_DENY


def _rows(sql: str, params: tuple = ()) -> list[dict]:
    con = connect_ro()
    try:
        con.execute("PRAGMA query_only = ON")
        con.set_authorizer(_authorizer)
        cur = con.execute(sql, params)
        return [dict(r) for r in cur.fetchmany(MAX_ROWS)]
    finally:
        con.close()


def check_select(sql: str) -> str:
    """SELECT/WITH 한 문장만 통과. 통과 못 하면 ValueError."""
    s = sql.strip().rstrip(";").strip()
    if not s:
        raise ValueError("빈 쿼리입니다.")
    if ";" in s:
        raise ValueError("한 번에 한 문장만 실행할 수 있습니다.")
    if s.split(None, 1)[0].lower() not in ("select", "with"):
        raise ValueError("SELECT 또는 WITH로 시작하는 조회만 허용됩니다.")
    return s


@server.resource("briefing://schema", name="schema", description="briefings 테이블과 confirmed_flows 뷰 정의")
def schema() -> str:
    return SCHEMA.read_text(encoding="utf-8")


@server.tool(description="최근 N일(기본 5)의 브리핑을 날짜 내림차순으로 돌려준다.")
def recent_briefings(days: int = 5) -> list[dict]:
    days = max(1, min(days, 60))
    return _rows(
        """SELECT date, btc_price, btc_chg_24h_pct, oi_chg_24h_pct, etf_net_flow_musd,
                  cvd_oi_tag, flow_tag, risk_tag, one_liner
           FROM briefings ORDER BY date DESC LIMIT ?""",
        (days,),
    )


@server.tool(description="시장 상태(CVD·OI 해석)별 일수, 평균 BTC 변동률, 평균 OI 변화율, 평균 ETF 순유입. 날짜는 YYYY-MM-DD.")
def state_summary(start: str = "0000-01-01", end: str = "9999-12-31") -> list[dict]:
    return _rows(
        """SELECT cvd_oi_tag AS state,
                  COUNT(*) AS days,
                  ROUND(AVG(btc_chg_24h_pct), 2) AS avg_btc_chg_pct,
                  ROUND(AVG(oi_chg_24h_pct), 2) AS avg_oi_chg_pct,
                  ROUND(AVG(etf_net_flow_musd), 1) AS avg_etf_flow_musd,
                  SUM(risk_tag = '약함') AS weak_risk_days
           FROM briefings
           WHERE date BETWEEN ? AND ?
           GROUP BY cvd_oi_tag
           ORDER BY days DESC, state""",
        (start, end),
    )


@server.tool(description="수급이 확정된 날만으로 ETF 순유입/순유출 연속 구간(시작일, 종료일, 일수, 합계)을 구한다.")
def etf_flow_streaks() -> list[dict]:
    return _rows(
        """WITH f AS (
               SELECT date, etf_net_flow_musd AS flow,
                      CASE WHEN etf_net_flow_musd >= 0 THEN '유입' ELSE '유출' END AS dir,
                      ROW_NUMBER() OVER (ORDER BY date) AS rn
               FROM confirmed_flows
           ), g AS (
               SELECT *, rn - ROW_NUMBER() OVER (PARTITION BY dir ORDER BY date) AS grp FROM f
           )
           SELECT dir, MIN(date) AS start, MAX(date) AS "end", COUNT(*) AS days,
                  ROUND(SUM(flow), 1) AS total_musd
           FROM g GROUP BY dir, grp ORDER BY start"""
    )


@server.tool(description=f"읽기 전용 SQL(SELECT/WITH 한 문장). 최대 {MAX_ROWS}행. 테이블: briefings, 뷰: confirmed_flows.")
def query_sql(sql: str) -> list[dict]:
    try:
        return _rows(check_select(sql))
    except (ValueError, sqlite3.DatabaseError) as e:  # 거절 사유를 Claude에게 그대로 돌려준다
        raise ToolError(f"쿼리 거절: {e}") from e


def main() -> None:
    server.run()  # stdio


if __name__ == "__main__":
    main()
