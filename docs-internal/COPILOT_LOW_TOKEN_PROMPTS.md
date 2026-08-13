# Low-Token Prompt Templates

Use these prompts as copy-paste templates so requests stay short and repeatable.

## Template A: Phase 1 CSV setup

Task: create Phase 1 CSV pipeline for [PROJECT_PATH].
Entry script: [ENTRY_SCRIPT].
Outputs: [CSV_PATH_1], [CSV_PATH_2], [CSV_PATH_3].
Requirements file: [PROJECT_REQUIREMENTS_PATH].
Do only:
1. Implement script updates.
2. Add or update targeted tests in [TEST_PATH].
3. Update README in [README_PATH].
4. Run only targeted tests and script once.
No Git commands.

## Template B: Phase 2 DB migration

Task: migrate [PROJECT_PATH] from CSV-only to CSV + DB upsert.
Entry script: [ENTRY_SCRIPT].
Load DATABASE_URL from repo .env.
Tables and unique keys:
- [TABLE_1]: [KEY_COL_A], [KEY_COL_B]
- [TABLE_2]: [KEY_COL_A]
- [TABLE_3]: [KEY_COL_A], [KEY_COL_B], [KEY_COL_C]
Use this exact pattern per table:
CREATE TABLE IF NOT EXISTS, dedupe legacy keys, CREATE UNIQUE INDEX IF NOT EXISTS, TEMP staging, INSERT ON CONFLICT DO UPDATE.
Keep CSV outputs unchanged.
Update [PROJECT_REQUIREMENTS_PATH] and [README_PATH].
Run targeted tests and run script twice to verify idempotency.
No Git commands.

## Template C: Phase 3 scheduled workflow

Task: add GitHub Action for [ENTRY_SCRIPT].
Follow same setup as existing workflows in this repo.
Schedule: [CRON_UTC].
Use secrets: DATABASE_URL and optional SLACK_WEBHOOK.
Install dependencies from [PROJECT_REQUIREMENTS_PATH].
Upload artifacts: [CSV_PATHS].
No Git commands.

## Template D: Validation only

Validate current implementation for [PROJECT_PATH].
Run:
1. [TEST_COMMAND]
2. [RUN_SCRIPT_COMMAND]
3. Query row counts for [TABLE_LIST]
Return only:
- pass/fail summary
- row counts
- blocking errors with file paths
No code edits unless a failure is found.
