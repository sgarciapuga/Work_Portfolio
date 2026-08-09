import pefile, sys, os
from pathlib import Path
pyd = Path(r"C:\Users\44784\miniconda3\envs\env_quarto\Lib\site-packages\matplotlib\_path.cp311-win_amd64.pyd")
print('inspecting', pyd)
if not pyd.exists():
    print('pyd not found')
    sys.exit(1)
p = pefile.PE(str(pyd))
print('DLL imports:')
imports = set()
if hasattr(p, 'DIRECTORY_ENTRY_IMPORT'):
    for entry in p.DIRECTORY_ENTRY_IMPORT:
        imports.add(entry.dll.decode())
for d in sorted(imports):
    print('-', d)

# Print PATH and search for common libs
path = os.environ.get('PATH','')
print('\nPATH entries (first 8):')
for i,part in enumerate(path.split(os.pathsep)):
    if i<8:
        print(i, part)

candidates = ['libpng','freetype','zlib','libhdf5','openjpeg','libjpeg','msvcp','ucrt']
print('\nChecking PATH for candidate DLLs:')
found = False
for part in path.split(os.pathsep):
    try:
        files = list(Path(part).glob('*.dll'))
    except Exception:
        continue
    for f in files:
        name = f.name.lower()
        for cand in candidates:
            if cand in name:
                print('found', name, 'in', part)
                found = True
if not found:
    print('No candidate libs found in PATH entries scanned')
