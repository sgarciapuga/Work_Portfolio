import os, sys
import matplotlib
import psutil

print('matplotlib', matplotlib.__version__)
print('backend', matplotlib.get_backend())

p = psutil.Process(os.getpid())
print('pid', p.pid)

maps = p.memory_maps()
count = 0
for m in maps:
    path = m.path.lower() if m.path else ''
    if path.endswith('.dll') or any(x in path for x in ('freetype','libpng','agg','python','vcruntime','msvcp','libjpeg')):
        print(m.path)
        count += 1
print('found', count, 'relevant mapped files')
