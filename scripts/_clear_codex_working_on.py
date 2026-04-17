import sqlite3
c = sqlite3.connect(".reza/context.db")
c.execute("UPDATE sessions SET working_on=NULL WHERE source_tool='codex'")
c.commit()
c.close()
print("cleared")
