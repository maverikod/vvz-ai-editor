from pathlib import Path

ROOT = Path(__file__).resolve().parent
files = [ROOT / 'architecture_addendum.md'] + sorted(ROOT.glob('step_*.md'))
required = ['Goal', 'Required', 'Verification']
ambiguous_terms = ['prefer existing', 'if needed', 'where practical', 'acceptable', 'fallback', 'or equivalent', 'may use', 'if available']
for path in files:
    text = path.read_text(encoding='utf-8')
    lines = text.splitlines()
    missing = [word for word in required if word not in text]
    amb = [term for term in ambiguous_terms if term in text.lower()]
    print(f'{path.name}|lines={len(lines)}|missing={missing}|ambiguous_terms={amb}')
