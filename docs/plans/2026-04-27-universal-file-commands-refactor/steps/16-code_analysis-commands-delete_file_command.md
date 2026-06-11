# Step 16: code_analysis/commands/delete_file_command.py

- Align delete_file with the universal delete flow.
- Resolve handler and validate delete mode before trash move, DB update, or index cleanup.
- Keep existing full-file delete behavior only when mode=file is explicit in the universal command.
- For legacy delete_file, preserve compatibility but add registry diagnostics and wrong-handler protections.
- Reject .venv, venv, site-packages, and installed package paths before any side effect.
- Acceptance: delete_file still works for allowed project files, while universal delete prevents accidental node/range/full-file ambiguity.
