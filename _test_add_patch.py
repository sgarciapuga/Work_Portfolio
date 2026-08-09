import traceback
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from pathlib import Path
import os

print('cwd', os.getcwd())
try:
    fig = plt.figure()
    ax = fig.add_subplot(111)
    print('created axes')
    r = Rectangle((0,0), 1, 1)
    print('created rect')
    ax.add_patch(r)
    print('added patch')
    fig.savefig('test_patch.png')
    print('saved test_patch.png exists?', Path('test_patch.png').exists())
except Exception:
    traceback.print_exc()
