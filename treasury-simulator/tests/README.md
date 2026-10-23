# Tests

What each test file checks. Each phase adds its own test file, and a row here.

| Area | Test file | Checks |
|---|---|---|
| Static data | `test_static_data.py` | The seed CSVs load and validate. Six entities with TRS as the in-house bank, IV commitments of about USD 1.5bn, and facilities and config that match the design. Broken links are caught. Every flow currency has an account. |
| Calendars and schedules | `test_calendars_schedule.py` | Business days per currency and date rolls, due dates by frequency, and schedules that are reproducible but vary a little. Flows land on business days and IC recharges net to zero. |
| Overnight rates | `test_rates.py` | The SOFR, €STR, SONIA and SARON parsers return decimal rates and fail loudly if a source changes format. Daily rates fill weekends, and the MMF and IC margins are applied. |
| Market data | `test_market.py` | FX in market convention, forward points that follow the rate differential, and rate history and differentials. |
| Daily engine | `test_engine.py` | Entity accounts are zero every day, settlements mirror group flows, and TRS keeps the operating minimum with no overdraft. MMF interest is paid on BD2 and matches the accrual, and the IV deposit earns MMF − 10 bp. The opening NAV is TRS equity, the P&L parts add up to the NAV change, FX gaps are filled, and runs are deterministic. |
| Schema | `test_schema_sql.py` | `tsim_schema.sql` creates every design table and static table, every statement can be re-run, and the file parses as PostgreSQL. |
| App *(local only)* | `test_app.py` | The main app and every page run without an exception. |
| App with history *(local only)* | `test_app_with_history.py` | Overview, Balance sheet and Market data render with a simulated history (synthetic flat rates). |

## Running

```bash
python -m pytest treasury-simulator/tests
```

Run locally in `env_1`, which has everything including streamlit and pglast, so nothing skips.

CI (`.github/workflows/treasury_simulator_7pm.yml`) leaves out both app tests, because they need streamlit. pglast isn't installed there either, so the schema parse check skips.
