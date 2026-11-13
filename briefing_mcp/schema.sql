-- 마켓 브리핑 하루치 = 한 행. 노션 DB(Market Direction Log)의 숫자·태그 속성을 그대로 옮긴다.
CREATE TABLE IF NOT EXISTS briefings (
    date               TEXT PRIMARY KEY,      -- YYYY-MM-DD (브리핑 날짜)
    btc_price          REAL,
    btc_chg_24h_pct    REAL,
    oi_chg_24h_pct     REAL,                  -- 미결제약정 24h 변화율
    oi_chg_7d_pct      REAL,
    funding_rate_pct   REAL,
    futures_cvd_btc    REAL,                  -- 선물 CVD 24h 변화
    spot_cvd_btc       REAL,                  -- 현물 CVD 24h 변화
    etf_net_flow_musd  REAL,                  -- 미국 BTC 현물 ETF 순유입($M), 미반영이면 NULL
    us10y_pct          REAL,
    us10y_chg_1d_bp    REAL,
    dxy_chg_1d_pct     REAL,
    nasdaq_chg_1d_pct  REAL,
    flow_tag           TEXT CHECK (flow_tag IN ('유입', '유출') OR flow_tag IS NULL),
    risk_tag           TEXT CHECK (risk_tag IN ('강함', '중립', '약함') OR risk_tag IS NULL),
    position_tag       TEXT,
    cvd_oi_tag         TEXT,                  -- 코드가 판정한 7가지 시장 상태 중 하나
    run_status         TEXT,                  -- 성공 / 일부 실패 / 실패
    flow_data_status   TEXT,                  -- 확정 / 정상 / 잠정 / 미반영 / 휴장 / 실패
    one_liner          TEXT,                  -- LLM이 쓴 한 줄 판단
    synced_at          TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_briefings_cvd_oi ON briefings (cvd_oi_tag);

-- ETF 수급이 확정된 날만 모은 뷰 (잠정·미반영 제외)
CREATE VIEW IF NOT EXISTS confirmed_flows AS
SELECT date, etf_net_flow_musd, flow_tag
FROM briefings
WHERE flow_data_status IN ('확정', '정상') AND etf_net_flow_musd IS NOT NULL;
