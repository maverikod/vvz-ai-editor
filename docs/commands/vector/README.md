# Vector Commands Block

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

Commands for vector index and vectorization: rebuild FAISS index, revectorize.

## Commands → File Mapping

| MCP Command Name | Class                | Source File                            |
|------------------|----------------------|----------------------------------------|
| rebuild_faiss    | RebuildFaissCommand  | `commands/vector_commands/rebuild_faiss.py`|
| revectorize      | RevectorizeCommand   | `commands/vector_commands/revectorize.py`  |

Package: `commands/vector_commands/` (`__init__.py` exports both). Registration: `code_analysis/hooks.py`.

## Detailed Command Descriptions

See [COMMANDS.md](COMMANDS.md) in this directory for per-command schema, parameters, and behavior.
