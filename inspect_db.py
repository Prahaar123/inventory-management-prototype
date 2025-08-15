# inspect_db.py
import sqlite3

conn = sqlite3.connect("inventory.db")
c = conn.cursor()

tables = ["items", "users", "logs", "sales", "settings"]
for t in tables:
    try:
        c.execute(f"SELECT COUNT(*) FROM {t}")
        cnt = c.fetchone()[0]
    except Exception as e:
        cnt = f"error: {e}"
    print(f"{t}: {cnt} rows")

print("\nSample items:")
c.execute("SELECT id, name, barcode, quantity, location FROM items LIMIT 10")
for row in c.fetchall():
    print(row)

print("\nSettings:")
c.execute("SELECT key, value FROM settings")
for r in c.fetchall():
    print(r)

conn.close()
