import os, sys
from pathlib import Path
print('sys.executable', sys.executable)
print('sys.prefix', sys.prefix)
print('CONDA_PREFIX', os.environ.get('CONDA_PREFIX'))
print('CONDA_DEFAULT_ENV', os.environ.get('CONDA_DEFAULT_ENV'))
print('\nFull PATH entries:')
for p in os.environ.get('PATH','').split(os.pathsep):
    print(p)
