import sys, site
print('sys.executable', sys.executable)
print('sys.path:')
for p in sys.path:
    print(' -', p)
print('\nsite.getsitepackages():')
try:
    for p in site.getsitepackages():
        print(' -', p)
except Exception as e:
    print('getsitepackages error', e)
print('\nsite.USER_SITE', site.USER_SITE)
