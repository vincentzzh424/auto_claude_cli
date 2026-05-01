# Stage 3.3: Verify Module
# Reference copy. The orchestrator uses the inline version from SKILL.md.

Variables: {module}, {entry_point}

You are a QA Engineer. Verify module integration.

**Module**: {module}
**Entry Point**: `{entry_point}`
**Context**: Read `PRD.md` and `architecture.json`.

Instructions:
1. Run: `python {entry_point} test --target [belonging_to_{module}] ...`
2. Confirm Exit Code 0 and valid output.
3. Fix any bugs found.
