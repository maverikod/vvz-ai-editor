import ast, json, os

COMMANDS_DIR = os.path.join(os.path.dirname(__file__), '..', 'ai_editor', 'commands')

def get_schema_params(tree):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == 'get_schema':
            for child in ast.walk(node):
                if isinstance(child, ast.Return) and child.value and isinstance(child.value, ast.Dict):
                    return extract_schema_dict(child.value)
            break
    return {}

def extract_schema_dict(d):
    result = {'properties': {}, 'required': []}
    for k, v in zip(d.keys, d.values):
        key = ast.literal_eval(k) if isinstance(k, ast.Constant) else None
        if key == 'properties' and isinstance(v, ast.Dict):
            for pk, pv in zip(v.keys, v.values):
                prop_name = ast.literal_eval(pk) if isinstance(pk, ast.Constant) else str(pk)
                prop_type = '?'
                if isinstance(pv, ast.Dict):
                    for tk, tv in zip(pv.keys, pv.values):
                        if isinstance(tk, ast.Constant) and tk.value == 'type':
                            prop_type = ast.literal_eval(tv) if isinstance(tv, ast.Constant) else '?'
                result['properties'][prop_name] = prop_type
        elif key == 'required' and isinstance(v, (ast.List, ast.Tuple)):
            result['required'] = [ast.literal_eval(el) for el in v.elts if isinstance(el, ast.Constant)]
    return result

def get_execute_accesses(tree):
    accessed = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == 'execute':
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    func = child.func
                    if isinstance(func, ast.Attribute) and func.attr == 'get':
                        if isinstance(func.value, ast.Name) and func.value.id == 'params':
                            if child.args and isinstance(child.args[0], ast.Constant):
                                accessed.add(child.args[0].value)
                if isinstance(child, ast.Subscript):
                    if isinstance(child.value, ast.Name) and child.value.id == 'params':
                        sl = child.slice
                        if isinstance(sl, ast.Constant):
                            accessed.add(sl.value)
            break
    return accessed

def get_metadata_info(tree):
    result = {'params_listed': [], 'fields': {}}
    PLACEHOLDERS = {'TODO', '...', ''}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == 'metadata':
            for child in ast.walk(node):
                if isinstance(child, ast.Return) and child.value and isinstance(child.value, ast.Dict):
                    val = child.value
                    for k, v in zip(val.keys, val.values):
                        key = ast.literal_eval(k) if isinstance(k, ast.Constant) else None
                        if key == 'parameters' and isinstance(v, ast.Dict):
                            result['params_listed'] = [
                                ast.literal_eval(pk) if isinstance(pk, ast.Constant) else str(pk)
                                for pk in v.keys
                            ]
                        elif key in ('return_value', 'error_cases', 'best_practices', 'usage_examples'):
                            empty = False
                            try:
                                lit = ast.literal_eval(v)
                                empty = lit in PLACEHOLDERS or lit == [] or lit == {}
                            except Exception:
                                pass
                            result['fields'][key] = {'present': True, 'empty': empty}
                    break
            break
    for field in ('return_value', 'error_cases', 'best_practices', 'usage_examples'):
        if field not in result['fields']:
            result['fields'][field] = {'present': False, 'empty': None}
    return result

def audit_file(filepath):
    with open(filepath) as f:
        src = f.read()
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return {'error': str(e)}
    schema = get_schema_params(tree)
    execute_access = get_execute_accesses(tree)
    meta = get_metadata_info(tree)
    schema_props = schema.get('properties', {})
    required = set(schema.get('required', []))
    params_table = []
    for name, typ in schema_props.items():
        params_table.append({'param': name, 'type': typ, 'required': name in required, 'accessed': name in execute_access})
    meta_params = set(meta['params_listed'])
    schema_params_set = set(schema_props.keys())
    return {
        'params': params_table,
        'meta_params_listed': meta['params_listed'],
        'missing_from_meta': sorted(schema_params_set - meta_params),
        'extra_in_meta': sorted(meta_params - schema_params_set),
        'fields': meta['fields']
    }

results = {}
for fname in sorted(os.listdir(COMMANDS_DIR)):
    if fname.endswith('_command.py') and not fname.startswith('base_'):
        fpath = os.path.join(COMMANDS_DIR, fname)
        results[f'commands/{fname}'] = audit_file(fpath)

print(json.dumps(results, indent=2))
