# AGENTS.md

Project-specific instructions for Codex and other coding agents:

- Keep code modular, typed, and easy to reason about.
- Do not hardcode financial assumptions; place configurable assumptions in explicit settings or deterministic scoring inputs.
- Keep financial calculations deterministic and testable.
- Separate raw external API clients from normalized domain models.
- Never expose, log, commit, or hardcode API keys or bearer tokens.
- Prefer small, focused PRs with clear summaries.
- Add or update tests when changing scoring logic.
- This project is a research and stock-screening tool, not an automated trading system.
