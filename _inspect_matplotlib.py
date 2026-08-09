import sys
import importlib
import traceback

print('python', sys.version)
try:
    import matplotlib
    print('matplotlib', matplotlib.__version__, 'file', getattr(matplotlib, '__file__', None))
    print('backend', matplotlib.get_backend())
    try:
        import matplotlib._path as _mpath
        print('_path', getattr(_mpath, '__file__', None))
        from matplotlib.path import Path
        p = Path([(0,0),(1,1),(2,0)])
        print('Path created, vertices shape', p.vertices.shape)
        # Try a simple Path operation
        codes = p.codes
        print('codes', codes)
    except Exception as e:
        print('error using _path or Path:')
        traceback.print_exc()
except Exception as e:
    print('matplotlib import fail')
    traceback.print_exc()
