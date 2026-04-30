# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Auto_Claude_CLI is a single-file Python orchestrator that drives Claude CLI to autonomously build complete software projects from a natural-language idea. It implements a multi-stage AI agent pipeline with **local progress tracking** for multi-day project resume support.

## Running

```bash
# Prerequisite: Claude CLI installed globally
npm install -g @anthropic-ai/claude-code

# Start a new project (default: resume mode)
python run.py "your project idea here"

# Resume a previous project (no need to re-type idea)
python run.py

# Force start from scratch
python run.py "your project idea here" --force

# Custom rate-limit retry interval (seconds)
python run.py "idea" --retry-wait 300
```

Must run inside a sandbox/empty directory. Uses `--dangerously-skip-permissions`.

## Architecture

The entire application is `run.py` (~530 lines, zero external Python dependencies, Python 3.9+ stdlib only). It is a linear pipeline where each stage constructs a role-based prompt and invokes `execute_claude_agent()`.

### Progress & Resume System

- **PROGRESS.md** — checkbox-format file in the working directory tracking every stage and module sub-step
- **Default mode is resume**: if PROGRESS.md exists, skips all `done` stages and continues from the first pending step
- **Stage 3 module-level granularity**: each module's Build/Integrate/Verify tracked independently
- `ProgressManager` class handles read/write/expand; `expand_stage3()` is idempotent (preserves done status on re-run)

### API Health Check

- `check_api_health()` reads `~/.claude/settings.json` for `ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN`
- Sends a minimal POST to `{base_url}/v1/messages` before each Claude CLI call
- On 429 (rate limit): blocks with countdown timer, retries indefinitely until quota resets
- On other errors: warns but proceeds (non-blocking)
- No settings file found: skips check silently

### Pipeline Stages (sequential)

1. **Requirement Research** — Product Researcher, outputs `research.md`
2. **Brainstorming** — UX Researcher, outputs `BRAIN.md` (personas/scenarios)
3. **Product Definition** — PM, outputs `PRD.md` + `DATA_FLOW.md`
4. **System Architecture** — Architect, outputs `architecture.json` + `requirements.txt`
5. **Dependency Analysis** — Topologically sorts modules from `architecture.json` via `graphlib.TopologicalSorter`
6. **Development Loop** — Per module in build order: build code + tests, integrate into `main.py`, verify via CLI
7. **Refactoring** — Code review + cleanup + re-run tests
8. **Final Acceptance** — End-to-end system test

### Key Functions

- `execute_claude_agent(prompt, ...)` — Core driver; includes pre-flight health check, retries on failure
- `check_api_health()` — Reads settings.json, verifies API, blocks on 429
- `ProgressManager` — Tracks stages in PROGRESS.md, supports load/create/set_active/set_done/expand_stage3
- `stage_dependency_analysis()` — Builds DAG from `architecture.json` module dependencies
- `countdown(seconds)` — Live countdown timer for rate-limit waits

## Conventions

- `DEFAULT_LANGUAGE = "Python"` — default target language for generated projects
- `RETRY_WAIT_DEFAULT = 600` — 10-minute default wait between rate-limit retries
- Windows: `subprocess.run` uses `shell=True` on `os.name == 'nt'`
- Bilingual docs: update both `README.md` and `README_CN.md` when changing documentation
- No tests for the orchestrator itself; it generates tests for output projects at `tests/test_<module_name>.py`

## PROGRESS.md Format

```markdown
- **Idea**: user's idea here
- **Started**: 2026-05-01 10:30:00
- **Updated**: 2026-05-01 14:20:00

## Pipeline

- [x] -1 Requirement Research @ 2026-05-01 10:35:00
- [~] 3.1|payment_module Build: payment_module
- [ ] 3.2|payment_module Integrate: payment_module
- [ ] 5 Final Acceptance
```

Status: `[x]` done, `[~]` active, `[ ]` pending, `[!]` failed. Module stages use `step|module_name` IDs.

## architecture.json Contract

Must contain a `modules` dict where each module has a `dependencies` array, plus an `entry_point` field. Example in `example/shopping_system/architecture.json`.
