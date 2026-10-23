-- Treasury simulator schema (Neon PostgreSQL).
-- Safe to run more than once: every object uses IF NOT EXISTS / OR REPLACE.
-- Static tables (dim_*, fee_schedule, iv_commitment) are loaded from treasury-simulator/static/.
-- Daily tables are filled by the engines from Phase 2 onwards.

CREATE SCHEMA IF NOT EXISTS tsim;

-- ---------------------------------------------------------------
-- Static data
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tsim.dim_entity (
    entity_code     TEXT PRIMARY KEY,
    entity_name     TEXT NOT NULL,
    country         TEXT NOT NULL,
    functional_ccy  TEXT NOT NULL,
    role            TEXT NOT NULL,
    description     TEXT
);

CREATE TABLE IF NOT EXISTS tsim.dim_bank (
    bank_code   TEXT PRIMARY KEY,
    bank_name   TEXT NOT NULL,
    role        TEXT
);

CREATE TABLE IF NOT EXISTS tsim.dim_account (
    account_id       TEXT PRIMARY KEY,
    entity_code      TEXT NOT NULL REFERENCES tsim.dim_entity (entity_code),
    bank_code        TEXT NOT NULL REFERENCES tsim.dim_bank (bank_code),
    mca_id           TEXT,              -- multi-currency account the sub-account belongs to
    currency         TEXT NOT NULL,
    account_type     TEXT NOT NULL,
    purpose          TEXT,
    signatories      INTEGER,
    monthly_fee_usd  NUMERIC(18, 2)
);

CREATE TABLE IF NOT EXISTS tsim.dim_flow_code (
    flow_code    TEXT PRIMARY KEY,
    category     TEXT NOT NULL,
    description  TEXT,
    direction    TEXT NOT NULL CHECK (direction IN ('in', 'out', 'both')),
    nature       TEXT NOT NULL CHECK (nature IN ('scheduled', 'uncertain', 'treasury')),
    tier         SMALLINT NOT NULL CHECK (tier BETWEEN 1 AND 4)
);

CREATE TABLE IF NOT EXISTS tsim.fee_schedule (
    schedule_id          TEXT PRIMARY KEY,
    entity_code          TEXT NOT NULL REFERENCES tsim.dim_entity (entity_code),
    flow_code            TEXT NOT NULL REFERENCES tsim.dim_flow_code (flow_code),
    currency             TEXT NOT NULL,
    amount               NUMERIC(18, 2) NOT NULL,  -- positive = received by the entity
    frequency            TEXT NOT NULL,
    day_rule             TEXT NOT NULL,
    counterparty         TEXT,
    counterparty_entity  TEXT REFERENCES tsim.dim_entity (entity_code)
);

CREATE TABLE IF NOT EXISTS tsim.iv_commitment (
    investment_id        TEXT PRIMARY KEY,
    investment_name      TEXT NOT NULL,
    strategy             TEXT,
    currency             TEXT NOT NULL,
    commitment           NUMERIC(18, 2) NOT NULL,
    vintage_year         SMALLINT NOT NULL,
    called_pct_at_start  NUMERIC(6, 4) NOT NULL,
    call_period_years    SMALLINT NOT NULL,
    expected_multiple    NUMERIC(6, 2) NOT NULL,
    fund_life_years      SMALLINT NOT NULL,
    status               TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tsim.dim_facility (
    facility_id                   TEXT PRIMARY KEY,
    facility_name                 TEXT NOT NULL,
    facility_type                 TEXT NOT NULL,
    currency                      TEXT NOT NULL,
    limit_amount                  NUMERIC(18, 2) NOT NULL,
    base_rate                     TEXT NOT NULL,
    margin_bp                     NUMERIC(8, 2) NOT NULL,
    commitment_fee_pct_of_margin  NUMERIC(6, 4) NOT NULL,
    secured                       BOOLEAN NOT NULL,
    advance_rate                  NUMERIC(6, 4),
    agent_bank                    TEXT REFERENCES tsim.dim_bank (bank_code),
    start_date                    DATE NOT NULL,
    maturity_date                 DATE NOT NULL
);

CREATE TABLE IF NOT EXISTS tsim.dim_mmf_fund (
    fund_id           TEXT PRIMARY KEY,
    fund_name         TEXT NOT NULL,
    currency          TEXT NOT NULL,
    bank_code         TEXT REFERENCES tsim.dim_bank (bank_code),
    limit_amount      NUMERIC(18, 2) NOT NULL,
    limit_currency    TEXT NOT NULL,
    interest_paid_bd  SMALLINT NOT NULL
);

-- ---------------------------------------------------------------
-- Market data
-- ---------------------------------------------------------------
-- FX rates come from the Daily FX Rates feed (public.fx_rates: units of currency per 1 USD).
CREATE OR REPLACE VIEW tsim.fx_rate AS
SELECT date AS rate_date, currency, fx_to_usd, fx_quality_flag
FROM public.fx_rates;

CREATE TABLE IF NOT EXISTS tsim.ir_rate (
    rate_date  DATE NOT NULL,
    currency   TEXT NOT NULL,
    tenor      TEXT NOT NULL,              -- ON, 1M, 3M, 6M, 12M, or MMF for the money market fund yield
    rate       NUMERIC(10, 6) NOT NULL,    -- annual rate, 0.045 = 4.5%
    source     TEXT NOT NULL DEFAULT 'simulated',
    PRIMARY KEY (rate_date, currency, tenor)
);

-- ---------------------------------------------------------------
-- Daily engine outputs
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tsim.cash_txn (
    txn_id               TEXT PRIMARY KEY,
    value_date           DATE NOT NULL,
    account_id           TEXT NOT NULL,
    flow_code            TEXT NOT NULL,
    currency             TEXT NOT NULL,
    amount               NUMERIC(18, 2) NOT NULL,   -- positive = money in
    counterparty         TEXT,
    counterparty_entity  TEXT,
    is_intercompany      BOOLEAN NOT NULL DEFAULT FALSE,
    position_id          TEXT,
    deal_id              TEXT
);
CREATE INDEX IF NOT EXISTS cash_txn_date_account_idx ON tsim.cash_txn (value_date, account_id);

CREATE TABLE IF NOT EXISTS tsim.cash_balance (
    balance_date  DATE NOT NULL,
    account_id    TEXT NOT NULL,
    opening       NUMERIC(18, 2) NOT NULL,
    movements     NUMERIC(18, 2) NOT NULL,
    closing       NUMERIC(18, 2) NOT NULL,
    PRIMARY KEY (balance_date, account_id)
);

-- Treasury positions: MMF holdings, bank deposits, IC loans, IC deposits, facility drawings.
CREATE TABLE IF NOT EXISTS tsim.position (
    position_id         TEXT PRIMARY KEY,
    position_type       TEXT NOT NULL CHECK (position_type IN ('MMF', 'DEPOSIT', 'IC_LOAN', 'IC_DEPOSIT', 'DRAWING')),
    counterparty        TEXT NOT NULL,      -- entity code, fund id, bank code or facility id
    currency            TEXT NOT NULL,
    principal           NUMERIC(18, 2) NOT NULL,
    rate                NUMERIC(10, 6),
    start_date          DATE NOT NULL,
    maturity_date       DATE,               -- NULL for MMF holdings and on-call deposits
    status              TEXT NOT NULL CHECK (status IN ('open', 'matured', 'rolled', 'repaid')),
    facility_id         TEXT,
    fund_id             TEXT,
    linked_position_id  TEXT                -- e.g. the IC loan funded by a facility drawing
);

CREATE TABLE IF NOT EXISTS tsim.fx_deal (
    deal_id      TEXT NOT NULL,
    leg          TEXT NOT NULL CHECK (leg IN ('single', 'near', 'far')),
    deal_type    TEXT NOT NULL CHECK (deal_type IN ('spot', 'forward', 'swap')),
    trade_date   DATE NOT NULL,
    value_date   DATE NOT NULL,
    buy_ccy      TEXT NOT NULL,
    buy_amount   NUMERIC(18, 2) NOT NULL,
    sell_ccy     TEXT NOT NULL,
    sell_amount  NUMERIC(18, 2) NOT NULL,
    rate         NUMERIC(14, 8) NOT NULL,
    counterparty TEXT NOT NULL,             -- bank code (external) or entity code (internal)
    is_internal  BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (deal_id, leg)
);

CREATE TABLE IF NOT EXISTS tsim.valuation (
    valuation_date    DATE NOT NULL,
    item_type         TEXT NOT NULL CHECK (item_type IN ('position', 'fx_deal')),
    item_id           TEXT NOT NULL,
    currency          TEXT NOT NULL,
    accrued_interest  NUMERIC(18, 2) NOT NULL DEFAULT 0,
    mtm               NUMERIC(18, 2) NOT NULL DEFAULT 0,  -- FX deals, undiscounted
    value_ccy         NUMERIC(18, 2) NOT NULL,
    value_usd         NUMERIC(18, 2) NOT NULL,
    PRIMARY KEY (valuation_date, item_type, item_id)
);

CREATE TABLE IF NOT EXISTS tsim.forecast_line (
    forecast_date  DATE NOT NULL,
    entity_code    TEXT NOT NULL,
    flow_code      TEXT NOT NULL,
    currency       TEXT NOT NULL,
    period_start   DATE NOT NULL,
    horizon        TEXT NOT NULL CHECK (horizon IN ('daily', '13w', '12m')),
    case_name      TEXT NOT NULL CHECK (case_name IN ('downside', 'base', 'upside')),
    amount         NUMERIC(18, 2) NOT NULL,
    PRIMARY KEY (forecast_date, entity_code, flow_code, currency, period_start, horizon, case_name)
);

CREATE TABLE IF NOT EXISTS tsim.nav_daily (
    nav_date              DATE NOT NULL,
    currency              TEXT NOT NULL,
    assets                NUMERIC(18, 2) NOT NULL,
    liabilities           NUMERIC(18, 2) NOT NULL,
    nav_ccy               NUMERIC(18, 2) NOT NULL,
    nav_usd               NUMERIC(18, 2) NOT NULL,
    open_fx_position_ccy  NUMERIC(18, 2) NOT NULL,
    open_fx_position_usd  NUMERIC(18, 2) NOT NULL,
    PRIMARY KEY (nav_date, currency)
);

CREATE TABLE IF NOT EXISTS tsim.scenario (
    scenario_id  TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    settings     JSONB NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------
-- Phase 2 additions
-- ---------------------------------------------------------------
-- Daily IC current account per entity and currency (positive = TRS owes the entity).
CREATE TABLE IF NOT EXISTS tsim.ic_current_account (
    balance_date      DATE NOT NULL,
    entity_code       TEXT NOT NULL,
    currency          TEXT NOT NULL,
    opening           NUMERIC(18, 2) NOT NULL,
    settlements       NUMERIC(18, 2) NOT NULL,
    interest_posted   NUMERIC(18, 2) NOT NULL,
    closing           NUMERIC(18, 2) NOT NULL,
    accrued_interest  NUMERIC(18, 2) NOT NULL,
    PRIMARY KEY (balance_date, entity_code, currency)
);

-- Daily TRS P&L by source; the parts add up to the daily change in NAV (USD).
CREATE TABLE IF NOT EXISTS tsim.pnl_daily (
    pnl_date    DATE NOT NULL,
    currency    TEXT NOT NULL,
    component   TEXT NOT NULL,
    amount_ccy  NUMERIC(18, 2) NOT NULL,
    amount_usd  NUMERIC(18, 2) NOT NULL,
    PRIMARY KEY (pnl_date, currency, component)
);

CREATE TABLE IF NOT EXISTS tsim.alert (
    alert_date  DATE NOT NULL,
    currency    TEXT NOT NULL,
    alert       TEXT NOT NULL,
    amount      NUMERIC(18, 2),
    PRIMARY KEY (alert_date, currency, alert)
);

-- ---------------------------------------------------------------
-- Phase 3 additions
-- ---------------------------------------------------------------
-- IC term deposit placements and maturities, and internal FX deal settlements, on the IC current account:
-- opening + settlements + interest_posted + transfers = closing.
ALTER TABLE tsim.ic_current_account ADD COLUMN IF NOT EXISTS transfers NUMERIC(18, 2) NOT NULL DEFAULT 0;
