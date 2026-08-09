import traceback
import matplotlib
matplotlib.use('Agg')
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
import os

try:
    print('cwd', os.getcwd())
    latest = pd.DataFrame({'account_number':['1001','1002','1003'],'closing_balance':[120000,80000,45000]})
    print('latest df', latest.shape)
    fig = plt.figure(figsize=(7,3))
    ax = fig.add_subplot(111)
    ax.bar(latest['account_number'], latest['closing_balance'])
    ax.set_title('Sample latest closing balances by account')
    out = Path('debug_treasury_plot2.png')
    print('saving to', out)
    fig.savefig(out)
    print('after save exists?', out.exists(), 'size', out.stat().st_size if out.exists() else None)
    plt.close(fig)
except Exception:
    traceback.print_exc()
