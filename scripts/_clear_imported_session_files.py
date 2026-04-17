import sqlite3
c = sqlite3.connect(".reza/context.db")
c.execute("UPDATE sessions SET files_modified=NULL WHERE source_tool IN ('cursor','codex')")
c.commit()
c.close()
print("cleared files_modified on imported sessions")
