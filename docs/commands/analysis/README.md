# Analysis Commands Block

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

Commands for code analysis: complexity, duplicates, comprehensive analysis, semantic search.

## Commands → File Mapping

| MCP Command Name        | Class                         | Source File                          |
|-------------------------|-------------------------------|--------------------------------------|
| analyze_complexity       | AnalyzeComplexityMCPCommand   | `commands/analyze_complexity_mcp.py` |
| find_duplicates          | FindDuplicatesMCPCommand      | `commands/find_duplicates_mcp.py`    |
| comprehensive_analysis   | ComprehensiveAnalysisMCPCommand| `commands/comprehensive_analysis_mcp.py`|
| semantic_search          | SemanticSearchMCPCommand     | `commands/semantic_search_mcp.py`   |

All inherit from `BaseMCPCommand`. Registration: `code_analysis/hooks.py`. Core: complexity_analyzer, duplicate_detector, comprehensive_analyzer, vector/semantic search.

## Detailed Command Descriptions

See [COMMANDS.md](COMMANDS.md) in this directory for per-command schema, parameters, and behavior.
