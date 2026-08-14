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

## Repeatable process for data projects
- Follow docs-internal/REPEATABLE_DATA_PROJECT_PLAYBOOK.md for phase-by-phase delivery.
- Use prompt patterns from docs-internal/COPILOT_LOW_TOKEN_PROMPTS.md.
- Prefer template reuse over free-form planning when task is repetitive.

<!-- mermaid-ai-skills:start -->
## Mermaid Diagrams

When the user asks to create, edit, or visualize a diagram, follow the
instructions in `.github/instructions/mermaid.instructions.md`.
<!-- mermaid-ai-skills:end -->
