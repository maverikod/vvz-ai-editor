# MCP command parameters: strict validation

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Rule

- **Required vs optional** only define whether a parameter may be absent. They do not relax validation when the parameter is present.
- **If a parameter is present**, it MUST be validated strictly against the command schema:
  - Type must match (`string`, `integer`, `number`, `boolean`, `array`, `object`).
  - If the schema defines `enum`, the value must be one of the allowed values.
  - If the schema has `additionalProperties: false`, any parameter not listed in `properties` must be rejected.

## Implementation

1. **Schema**: Each command exposes `get_schema()` with `properties`, `required`, and `additionalProperties: false` (recommended). Every property must have a `type`; use `enum` where applicable.

2. **Validation**: At the start of `execute()`, commands MUST call:
   ```python
   BaseMCPCommand.validate_params_against_schema(
       params,  # full incoming dict: named args + kwargs
       self.get_schema(),
       command_name=self.name,
   )
   ```
   Build `params` from the arguments passed to `execute()` (e.g. merge `kwargs` with any named parameters that might be passed through).

3. **Helper**: `BaseMCPCommand.validate_params_against_schema(params, schema, command_name)` raises `ValidationError` (field, message, details) when:
   - A key is present that is not in `properties` and `additionalProperties` is false.
   - A value's type does not match the property's `type`.
   - A value is not in the property's `enum` (if defined).

## Checklist for command authors

- [ ] `get_schema()` has `additionalProperties: false` and every property has `type`.
- [ ] At the beginning of `execute()`, all incoming parameters are passed to `validate_params_against_schema()`.
- [ ] No “lenient” acceptance of wrong types (e.g. string where integer is expected).
