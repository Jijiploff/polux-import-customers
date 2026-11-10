"""Reemplaza == True/== False por == True/== False en el código backend.

Motivo: SQL Server no acepta `IS 1` para columnas BIT; SQLAlchemy genera
`= 1` cuando se usa `==` en lugar de `.is_()`.

Uso:
    docker compose exec backend python -m scripts.fix_is_true
"""
from pathlib import Path
import re

ROOT = Path("/app")
PATTERNS = [
    (re.compile(r"\.is_\(True\)"), "== True"),
    (re.compile(r"\.is_\(False\)"), "== False"),
]

EXCLUDE_FRAGMENTS = ("/.venv/", "site-packages", "__pycache__")

changed: list[str] = []
for py in ROOT.rglob("*.py"):
    s = str(py)
    if any(frag in s for frag in EXCLUDE_FRAGMENTS):
        continue
    original = py.read_text(encoding="utf-8")
    new = original
    for pat, repl in PATTERNS:
        new = pat.sub(repl, new)
    if new != original:
        py.write_text(new, encoding="utf-8")
        changed.append(str(py.relative_to(ROOT)))

if changed:
    print(f"Archivos modificados: {len(changed)}")
    for c in sorted(changed):
        print(f"  ✓ {c}")
else:
    print("Nada que modificar.")