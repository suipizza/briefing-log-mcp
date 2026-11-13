"""키 없이 돌려보기: 샘플 DB에 MCP 클라이언트로 붙어 도구를 실제로 호출하고 결과를 출력한다."""
import asyncio
import json

from mcp import Client

from briefing_mcp.server import server

CALLS = [
    ("state_summary", {}),
    ("etf_flow_streaks", {}),
    ("query_sql", {"sql": "SELECT date, us10y_chg_1d_bp, btc_chg_24h_pct, cvd_oi_tag FROM briefings "
                          "WHERE us10y_chg_1d_bp >= 10 ORDER BY date"}),
    ("query_sql", {"sql": "DELETE FROM briefings"}),
]


async def main() -> None:
    async with Client(server) as c:
        print("tools:", [t.name for t in (await c.list_tools()).tools])
        for name, args in CALLS:
            r = await c.call_tool(name, args)
            print(f"\n## {name} {json.dumps(args, ensure_ascii=False)}")
            if r.is_error:
                print("거절:", r.content[0].text)
            else:
                for row in r.structured_content["result"]:
                    print(json.dumps(row, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
