import json
import subprocess
import sys

sid = sys.argv[1] if len(sys.argv) > 1 else "codex-019d7445b1ad"
out = subprocess.check_output(
    ["reza", "session", "graph", sid], text=True, encoding="utf-8"
)
d = json.loads(out)
sc = d["scope"]
s = d["session"]
print(f"session: {s['id']}  ({s['llm_name']}, {s['turn_count']} turns)")
print(f"files touched: {len(sc['files'])}")
for f in sc["files"][:15]:
    print(f"  - {f}")
print(f"nodes in those files: {len(sc.get('nodes', []))}")
print(f"edges between those nodes: {len(sc['edges'])}")
