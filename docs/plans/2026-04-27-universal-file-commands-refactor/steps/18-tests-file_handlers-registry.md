# Step 18: tests/file_handlers/test_registry.py

- Add tests for extension-to-handler routing.
- Verify .md, .txt, .rst, .adoc route to text.
- Verify .json routes to json.
- Verify .yaml and .yml route to yaml.
- Verify .py, .pyi, .pyw route to python.
- Verify unknown extensions fail closed.
- Verify unsupported extensions fail before backup, write, DB update, indexing, or parse calls.
- Acceptance: tests prove routing is config-driven and not duplicated in command bodies.
