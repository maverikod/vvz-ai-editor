# Step 05: code_analysis/commands/json_load_file_command.py

## Goal
- Make JSON loading the only supported read entry point for JSON structure.
- Prevent JSON files from being handled as plain text.

## Current responsibility
- Loads JSON files into the JSON tree workflow.

## Required changes
- Enforce `.json` suffix validation inside the command.
- Return a wrong-handler error for non-JSON files.
- Keep parsing errors explicit and structured.
- Make diagnostics reusable by the universal file router.
- Do not modify files or project indexes during load.

## MCP validation
- Load valid `.json` succeeds.
- Load malformed `.json` returns parse diagnostics.
- Load `.yaml` fails with wrong-handler error.
- Load `.txt` fails with wrong-handler error.
- Follow-up read through JSON workflow confirms parsed structure.
