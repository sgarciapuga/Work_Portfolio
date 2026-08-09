**Environment Hardening & Native Crash Recovery**

Short-term goal: ensure Quarto/Jupyter run in an isolated conda env and use conda-built Matplotlib/runtime to avoid DLL mixups.

Steps to follow:

- 1. Install conda-forge Matplotlib and runtime into the target env (example below).
- 2. Use the provided wrapper `scripts/render_in_env_quarto.ps1` to run Quarto with `env_quarto`.
- 3. If native crashes persist, capture a native dump (requires admin): use WinDbg or ProcDump to collect a minidump when Python crashes and share it for analysis.
- 4. For immediate reliability, set `MPLBACKEND='Agg'` in the environment or port individual plots to Plotly.

Conda install example:
```powershell
conda activate env_quarto
conda install -y -c conda-forge matplotlib vs2015_runtime libpng freetype zlib
```

Admin-only native debugging (optional):
- Use ProcDump: `procdump -ma -e python.exe python_crash.dmp`
- Or use WinDbg to run `python.exe` and capture the exception stack.

CI recommendation:
- Add a job that creates a fresh environment (conda), installs `quarto` + deps and runs `quarto render --execute` to catch regressions.
