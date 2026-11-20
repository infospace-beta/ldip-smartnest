"""Fail release checks when tracked application source contains merge markers."""
from pathlib import Path
import re
import subprocess

root = Path(__file__).resolve().parents[1]
extensions = {'.py', '.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs', '.json', '.yaml', '.yml'}
marker = re.compile(r'^(?:<{7}(?: |$)|={7}$|>{7}(?: |$))')
paths = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0')
failures = []
for name in paths:
    source = root / name
    if not source.is_file() or source.suffix not in extensions:
        continue
    for number, line in enumerate(source.read_text(encoding='utf-8-sig').splitlines(), 1):
        if marker.match(line):
            failures.append(f'{name}:{number}')
if failures:
    print('Unresolved merge markers in source:\n' + '\n'.join(failures))
    raise SystemExit(1)
print('No unresolved merge markers in tracked application source.')
