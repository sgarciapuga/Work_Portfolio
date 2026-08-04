import sqlite3

db_path = "../portfolio-data/treasury.db"
conn = sqlite3.connect(db_path)

conn.execute("DROP TABLE IF EXISTS fx_rates")
conn.commit()
conn.close()

print("FX table dropped.")

