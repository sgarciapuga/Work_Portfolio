import faulthandler
faulthandler.enable()
import traceback
import matplotlib
matplotlib.use('Agg')
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
import os

print('starting')
try:
    print('cwd', os.getcwd())
    latest = pd.DataFrame({'account_number':['1001','1002','1003'],'closing_balance':[120000,80000,45000]})
    fig = plt.figure(figsize=(7,3))
    ax = fig.add_subplot(111)
    ax.bar(latest['account_number'], latest['closing_balance'])
    out = Path('debug_faulthandler_plot.png')
    print('about to save to', out)
    fig.savefig(out)
    print('after save exists?', out.exists())
    plt.close(fig)
except Exception:
    traceback.print_exc()
print('finished')
