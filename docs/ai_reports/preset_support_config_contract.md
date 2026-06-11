# chunk_set_overrides — Config Contract

Key path: `code_analysis.vectorization.chunk_set_overrides`

Type: object (dict[str, str]) | Optional | Default: {} (use built-in presets)

Controls which SVO chunker preset is used per document source type.

## Keys

| source_type key | Default preset   | Description                         |
|-----------------|------------------|-------------------------------------|
| `docstring`     | `docstring`      | Python docstrings (module/class/fn) |
| `docs_markdown` | `technical_text` | Markdown documentation files        |

## Valid preset values

Defined in `svo_client.client.CHUNK_SET_PRESETS`:

`plain_text`, `technical_text`, `docstring`, `scientific_text`, `fiction`, `chat`, `log`

## Example config.json fragment

```json
{
  "code_analysis": {
    "vectorization": {
      "chunk_set_overrides": {
        "docstring": "docstring",
        "docs_markdown": "technical_text"
      }
    }
  }
}
```

## Behaviour on invalid value

Invalid preset names are logged as WARNING and the default for that source_type is used. The worker does not crash.
