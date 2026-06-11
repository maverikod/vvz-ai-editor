# Atomic step: chunk type

Parent step: 06-indexing-chunker-integration

Source: `chunk_metadata_adapter/semantic_chunk.py` and `chunk_metadata_adapter/data_types.py`.

Goal: use the existing `SemanticChunk.type` contract for Markdown documentation chunks.

Decision: Markdown documentation chunks must use `ChunkType.DOC_BLOCK` / `"DocBlock"`.

Allowed `ChunkType` values verified in `chunk_metadata_adapter`: `DocBlock`, `CodeBlock`, `Message`, `Draft`, `Task`, `Subtask`, `TZ`, `Comment`, `Log`, `Metric`.

Do not introduce `documentation_markdown` or any other new chunk type unless `chunk_metadata_adapter.ChunkType` is extended first and all `chunk_type` consumers are checked.

Implementation note: `type="DocBlock"` is the canonical Markdown docs chunk type. If `language="Markdown"` is used, separately verify `is_code_chunk` behavior because `LanguageEnum.is_programming_language()` currently treats Markdown as a technical/programming language.

Output: markdown-chunk-type-decision.md