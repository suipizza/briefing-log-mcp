"""키 없이 돌려보기: 저장된 실제 브리핑 12일치(CSV)를 SQLite에 넣는다."""
from briefing_mcp.db import db_path, load_csv

if __name__ == "__main__":
    n = load_csv()
    print(f"{n} rows → {db_path()}")
