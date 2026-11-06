# Engineering skill installation notes

Project instructions are in `/AGENTS.md`, the constitution is in `.specify/memory/constitution.md`, and the Anti-Slop core is included at `/antislop.md`.

Install selected Matt Pocock engineering skills with `npx skills@latest add mattpocock/skills -a codex`. Select TDD, diagnosing-bugs, codebase-design, and code-review.

The Anti-Slop core is already vendored. Install its modular skills with `npx skills@latest add miqdadbadjuber/anti-slop --all -a codex`.

Install Spec Kit with `uv tool install specify-cli`; verify using `specify version`. Follow existing-project adoption guidance before generating or migrating files.

This is a Streamlit application. Install the full UI/UX Pro Max skill and its searchable data with `npx ui-ux-pro-max-cli init --ai codex`. The CLI is the supported installation path.

Review installer diffs before accepting updates. Do not force-overwrite customized agent files or commit machine-specific global settings.