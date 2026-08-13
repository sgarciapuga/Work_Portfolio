# Repeatable Data Project Playbook

Purpose: run the same delivery pattern with minimal chat and low token usage.

## Standard lifecycle

Phase 1: CSV project first
- Build generator script that writes deterministic CSV outputs.
- Add local tests for shape, key columns, and idempotent file generation.
- Add project-local requirements file.
- Add README with run command and outputs.

Phase 2: database migration
- Keep CSV outputs unchanged.
- Add DATABASE_URL loading from repo .env.
- Add SQLAlchemy persistence for each dataset table.
- For each table apply this exact sequence:
  1. CREATE TABLE IF NOT EXISTS
  2. Delete legacy duplicates by unique key
  3. CREATE UNIQUE INDEX IF NOT EXISTS
  4. Stage rows in TEMP TABLE
  5. INSERT ON CONFLICT DO UPDATE
- Add dependencies: sqlalchemy, psycopg2-binary, python-dotenv.
- Update README with required secret and target tables.

Phase 3: scheduled automation
- Create workflow with schedule + workflow_dispatch.
- Install only project-local requirements.
- Pass DATABASE_URL from GitHub Secrets.
- Run generator script.
- Upload CSV artifacts.
- Optional: commit CSV snapshots and Slack failure notice.

## Required inputs to start any new project

- Project folder name
- Script entry point path
- CSV output file paths
- Database table names
- Unique key columns per table
- Schedule time and timezone policy (fixed UTC or local-time gate)

## Default decisions to avoid extra questions

- Keep existing coding style.
- Use project-local requirements file.
- Use targeted tests only.
- Preserve current outputs while adding DB support.
- Prefer additive changes, no broad refactors.

## Definition of done

- Tests pass.
- Script runs locally.
- DB tables receive upserts.
- Re-run script and row counts do not increase unexpectedly.
- README and workflow are updated.
