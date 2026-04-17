"""Dev smoke helper for session list output."""
import json
import subprocess
import sys

out = subprocess.check_output(
    ["reza", "session", "list", "--json", "--limit", "5"],
    text=True,
    encoding="utf-8",
    shell=False,
)
for s in json.loads(out):
    summary = (s.get("working_on") or s.get("first_user_message") or "").replace("\n", " ")
    print(f"{s.get('source_tool') or '-':<7} {s['id']:<24} turns={s['turn_count']:>3} tok={s['token_total']:>5}  | {summary[:70]}")
