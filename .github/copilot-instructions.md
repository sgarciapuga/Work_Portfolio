## Cost-efficiency rules (always follow)
- Prefer smallest sufficient model and minimal reasoning by default.
- Do not use long-context, autopilot, or background agents unless explicitly requested.
- Never run full-repo analysis when a file-scoped or function-scoped search is enough.
- Reuse prior outputs in this session; revise incrementally instead of regenerating.
- Keep prompts and edits narrowly scoped to the requested task.
- For code changes: inspect only relevant files first, then make surgical edits.
- Ask before any expensive action (broad refactor, multi-agent run, full test suite, or long-context pass).
- Prefer targeted tests/lint checks over full-suite runs.
- Stop after delivering the requested result; avoid extra exploratory work.