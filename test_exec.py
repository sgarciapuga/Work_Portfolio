import matplotlib
matplotlib.use('Agg')
import sqlite3, pandas as pd, matplotlib.pyplot as plt
from pathlib import Path

# Check DB
db = Path('portfolio-data/treasury.db')
if db.exists():
    conn = sqlite3.connect(db)
    try:
        df = pd.read_sql('SELECT * FROM movements ORDER BY date DESC LIMIT 5', conn)
        print(df.head())
    except Exception as e:
        print('read_sql fail', e)
    finally:
        conn.close()
else:
    print('db missing')

# Plot sample balances
balances_dir = Path('treasury-cashflow-simulation/data/Balances')
if balances_dir.exists():
    csvs = sorted(balances_dir.glob('balances_*.csv'))
    if csvs:
        frames = [pd.read_csv(p) for p in csvs[-7:]]
        df_all = pd.concat(frames, ignore_index=True)
        latest = df_all.groupby('account_number')['closing_balance'].last().reset_index()
    else:
        latest = pd.DataFrame({'account_number': ['1001', '1002'], 'closing_balance': [1000, 2000]})
else:
    latest = pd.DataFrame({'account_number': ['1001', '1002'], 'closing_balance': [1000, 2000]})

plt.bar(latest['account_number'], latest['closing_balance'])
plt.savefig('test_report_plot.png')
print('plot saved')
import matplotlib
matplotlib.use('Agg')
import sqlite3, pandas as pd, matplotlib.pyplot as plt
from pathlib import Path

db=Path('portfolio-data/treasury.db')
if db.exists():
    conn=sqlite3.connect(db)
    try:
        df=pd.read_sql('SELECT * FROM movements ORDER BY date DESC LIMIT 5',conn)
        print(df.head())
    except Exception as e:
        print('read_sql fail',e)
    finally:
        conn.close()
else:
    print('db missing')

balances_dir=Path('treasury-cashflow-simulation/data/Balances')
if balances_dir.exists():
    csvs=sorted(balances_dir.glob('balances_*.csv'))
    if csvs:
        frames=[pd.read_csv(p) for p in csvs[-7:]]
        df_all=pd.concat(frames,ignore_index=True)
        latest=df_all.groupby('account_number')['closing_balance'].last().reset_index()
    else:
        latest=pd.DataFrame({'account_number':['1001','1002'],'closing_balance':[1000,2000]})
else:
    latest=pd.DataFrame({'account_number':['1001','1002'],'closing_balance':[1000,2000]})

plt.bar(latest['account_number'], latest['closing_balance'])
plt.savefig('test_report_plot.png')
print('plot saved')
