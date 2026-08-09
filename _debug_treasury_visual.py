import traceback
import matplotlib
matplotlib.use('Agg')
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

try:
    balances_dir = Path('treasury-cashflow-simulation/data/Balances')
    csvs = sorted(balances_dir.glob('balances_*.csv')) if balances_dir.exists() else []
    if csvs:
        frames = [pd.read_csv(p) for p in csvs[-7:]]
        df_all = pd.concat(frames, ignore_index=True)
        latest = df_all.groupby('account_number')['closing_balance'].last().reset_index()
    else:
        latest = pd.DataFrame({'account_number':['1001','1002','1003'],'closing_balance':[120000,80000,45000]})

    print('latest dataframe:')
    print(latest)

    plt.figure(figsize=(7,3))
    plt.bar(latest['account_number'], latest['closing_balance'])
    plt.title('Sample latest closing balances by account')
    plt.xlabel('Account')
    plt.ylabel('Closing balance')
    plt.tight_layout()
    out='debug_treasury_plot.png'
    plt.savefig(out)
    print('saved plot to', out, 'exists?', Path(out).exists())
except Exception as e:
    print('Exception during visual example:')
    traceback.print_exc()
