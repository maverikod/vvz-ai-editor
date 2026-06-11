# Parallelization map

Directory: `docs/plans/db_retry_worker_coordination_100_qwen`

Purpose: assign plan steps to agents while preserving dependencies.

Read blocks in order:

1. [Waves 0-1: coordination and core DB contract](PARALLELIZATION_WAVES_0_1.md)
2. [Waves 2-3: driver/RPC, client metadata, config](PARALLELIZATION_WAVES_2_3.md)
3. [Waves 4-6: schema, coordinator, watcher/indexer, compatibility](PARALLELIZATION_WAVES_4_6.md)
4. [Waves 7-8: integration, MCP verification, final report](PARALLELIZATION_WAVES_7_8.md)
5. [Compact assignment matrix](PARALLELIZATION_ASSIGNMENT_MATRIX.md)

Critical dependency chain:

```text
01 -> 02 -> 03/04 -> 05 -> 06 -> 07
08 -> 09 -> 15
11 -> 12 -> 13 -> 14/16 -> 25/32
17/18/19 depend on 01 and 04
20-27 test matching implementation blocks
29 -> 30 -> 31 -> 32 -> 33 -> 34 -> 35 -> 36
```

Main rule: do not start watcher/indexer implementation before DB retry/error contract is implemented enough to compile and pass core tests. MCP verification is sequential after merge/reload.
