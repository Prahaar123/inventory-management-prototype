# db_setup.py
import sqlite3
import hashlib
from datetime import datetime

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

conn = sqlite3.connect("inventory.db")
c = conn.cursor()

# Create tables
c.execute("""
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT,
    barcode TEXT UNIQUE,
    quantity INTEGER DEFAULT 0,
    supplier TEXT,
    purchase_price REAL,
    sale_price REAL,
    location TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user TEXT,
    action TEXT,
    item_id INTEGER,
    quantity INTEGER,
    location TEXT,
    FOREIGN KEY (item_id) REFERENCES items (id)
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    role TEXT,
    password TEXT
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user TEXT,
    item_id INTEGER,
    qty_sold INTEGER,
    FOREIGN KEY (item_id) REFERENCES items (id)
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
)
""")

conn.commit()

# Seed default admin user (if not exists)
admin_username = "admin"
admin_password = "admin123"  # change later!
c.execute("SELECT id FROM users WHERE username = ?", (admin_username,))
if not c.fetchone():
    c.execute("INSERT INTO users (username, role, password) VALUES (?, ?, ?)",
              (admin_username, "admin", hash_password(admin_password)))
    print(f">>> Created default admin user: {admin_username} / {admin_password}")

# Seed settings (low stock threshold)
c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
          ("low_stock_threshold", "5"))

# Seed a few sample items (if not already present)
sample_items = [
    ("Apple iPhone 12", "Electronics", "111111111111", 10, "Apple Supplier", 500.0, 700.0, "Store A"),
    ("Logitech Mouse M220", "Accessories", "222222222222", 25, "Logitech India", 10.0, 15.0, "Store A"),
    ("A4 Notebook 200 pages", "Stationery", "333333333333", 50, "Local Supplier", 1.0, 2.0, "Store B"),
]

for name, category, barcode, qty, supplier, purchase_price, sale_price, location in sample_items:
    c.execute("SELECT id FROM items WHERE barcode = ?", (barcode,))
    if not c.fetchone():
        c.execute("""
        INSERT INTO items (name, category, barcode, quantity, supplier, purchase_price, sale_price, location)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, category, barcode, qty, supplier, purchase_price, sale_price, location))

conn.commit()
conn.close()

print("✅ inventory.db created (or updated).")
print("Files: inventory.db (in same folder).")
