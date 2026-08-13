1) In VS Code, create a new file:

.github/workflows/name_310am.yml - time you are running the workflow

2) Paste this workflow:

name: Treasury Cashflow - 3:10 AM UTC

on:
  schedule:
    - cron: '10 3 * * *'
  workflow_dispatch:

permissions:
  contents: write

concurrency:
  group: treasury-cashflow-310am
  cancel-in-progress: false

jobs:
  run-treasury-cashflow:
    runs-on: ubuntu-latest

    steps:
      - name: Check out repository code
        uses: actions/checkout@v4.2.2

      - name: Set up Python
        uses: actions/setup-python@v5.4.0
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Run Treasury cashflow simulation
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
        run: |
          python treasury-cashflow-simulation/run_pipeline.py

      - name: Upload generated CSV files
        uses: actions/upload-artifact@v4
        with:
          name: treasury-cashflow-csv
          path: |
            treasury-cashflow-simulation/data/Balances/*.csv
            treasury-cashflow-simulation/data/Movements/*.csv

      - name: Commit updated CSV backups
        run: |
          git config --global user.name "github-actions[bot]"
          git config --global user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add treasury-cashflow-simulation/data/Balances/*.csv
          git add treasury-cashflow-simulation/data/Movements/*.csv

          if [ -z "$(git status --porcelain)" ]; then
            echo "No changes to commit."
          else
            git commit -m "auto: update treasury cashflow CSVs [skip ci]"
            git push
          fi


3. Confirm that the repository has a GitHub Actions secret named DATABASE_URL:

GitHub repository -> Settings -> Secrets and variables -> Actions -> New repository secret.

Its value should be the same PostgreSQL/Neon connection string you use locally.

4. Commit and push the workflow file to GitHub.

5. Open GitHub -> Actions -> Treasury Cashflow - 3:10 AM UTC -> Run workflow. Run it once manually.

6. Check the log for the “Run Treasury cashflow simulation” step. A successful run creates or updates:

treasury_balances - these are example of tables created
treasury_movements - these are example of tables created

7. In PostgreSQL, verify:

SELECT COUNT(*) FROM treasury_balances;
SELECT COUNT(*) FROM treasury_movements;
SELECT MAX(date) FROM treasury_balances;