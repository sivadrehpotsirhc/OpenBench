import sqlite3

con = sqlite3.connect("data/30orless.db")

con.execute("DELETE FROM pins")
con.commit()
con.close()

print("Login screen has been reset. You can now create a new PIN.")