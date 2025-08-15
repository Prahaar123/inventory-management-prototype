# migrate_phase3.py
import sqlite3

DB_FILE = "inventory.db"

conn = sqlite3.connect(DB_FILE)
c = conn.cursor()

# Transactions master table
c.execute("""
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user TEXT,
    type TEXT,            -- 'sale', 'purchase', 'restock', 'adjustment', 'damage', 'return'
    customer TEXT,
    total_amount REAL,
    notes TEXT
)
""")

# Transaction items (one row per item in a transaction)
c.execute("""
CREATE TABLE IF NOT EXISTS transaction_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id INTEGER,
    item_id INTEGER,
    barcode TEXT,
    item_name TEXT,
    quantity_changed INTEGER,
    quantity_before INTEGER,
    quantity_after INTEGER,
    unit_price REAL,
    FOREIGN KEY(transaction_id) REFERENCES transactions(id),
    FOREIGN KEY(item_id) REFERENCES items(id)
)
""")

conn.commit()
conn.close()
print("✅ Migration complete: transactions and transaction_items tables created.")
