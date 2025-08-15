# inventory_cli.py
import sqlite3
import hashlib
import os
import sys
from datetime import datetime

# barcode helper (local file)
from barcode_generator import generate_barcode_image, generate_unique_barcode

# Excel
try:
    from openpyxl import Workbook
    from openpyxl.styles import Font
    HAS_OPENPYXL = True
except Exception:
    HAS_OPENPYXL = False

# PDF
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
    HAS_REPORTLAB = True
except Exception:
    HAS_REPORTLAB = False

DB_FILE = "inventory.db"

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def connect_db():
    return sqlite3.connect(DB_FILE)

# ------------------------
# Inventory Core Functions
# ------------------------
def add_item():
    name = input("Item Name: ").strip()
    if not name:
        print("❌ Item name cannot be empty.")
        return

    category = input("Category: ").strip()
    barcode_input = input("Barcode (leave blank to auto-generate): ").strip()
    if not barcode_input:
        barcode_input = generate_unique_barcode()

    # quantity
    try:
        qty = int(input("Quantity: ").strip())
    except ValueError:
        print("❌ Quantity must be an integer.")
        return

    supplier = input("Supplier: ").strip()
    try:
        purchase_price = float(input("Purchase Price: ").strip())
    except ValueError:
        purchase_price = 0.0
    try:
        sale_price = float(input("Sale Price: ").strip())
    except ValueError:
        sale_price = 0.0
    location = input("Location: ").strip()

    conn = connect_db()
    c = conn.cursor()

    attempts = 0
    item_id = None
    while attempts < 5:
        try:
            c.execute("""
                INSERT INTO items (name, category, barcode, quantity, supplier, purchase_price, sale_price, location)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (name, category, barcode_input, qty, supplier, purchase_price, sale_price, location))
            conn.commit()
            item_id = c.lastrowid
            break
        except sqlite3.IntegrityError:
            attempts += 1
            barcode_input = generate_unique_barcode()
        except Exception as e:
            conn.close()
            print("❌ Error inserting item:", e)
            return

    # generate barcode image if libs available
    try:
        img_path = generate_barcode_image(barcode_input)
        print(f"🖨 Barcode image saved at: {img_path}")
    except Exception as e:
        # non-fatal; proceed even if barcode image generation fails
        print("⚠ Barcode image not created:", e)

    # log
    log_action("admin", "add", item_id, qty, location)
    conn.close()
    print(f"✅ Item '{name}' added successfully with barcode: {barcode_input}")

def update_item():
    barcode = input("Barcode of item to update: ").strip()
    conn = connect_db()
    c = conn.cursor()
    c.execute("SELECT id, name, quantity FROM items WHERE barcode=?", (barcode,))
    item = c.fetchone()
    if not item:
        print("❌ Item not found.")
        conn.close()
        return
    print(f"Current: {item[1]} - Qty: {item[2]}")
    try:
        qty = int(input("New Quantity: ").strip())
    except ValueError:
        print("❌ Quantity must be an integer.")
        conn.close()
        return
    c.execute("UPDATE items SET quantity=? WHERE id=?", (qty, item[0]))
    conn.commit()
    log_action("admin", "update", item[0], qty, "N/A")
    conn.close()
    print("✅ Item updated.")

def sell_item():
    barcode = input("Barcode of item to sell: ").strip()
    try:
        qty = int(input("Quantity to sell: ").strip())
    except ValueError:
        print("❌ Quantity must be an integer.")
        return
    conn = connect_db()
    c = conn.cursor()
    c.execute("SELECT id, name, quantity FROM items WHERE barcode=?", (barcode,))
    item = c.fetchone()
    if not item:
        print("❌ Item not found.")
        conn.close()
        return
    if qty > item[2]:
        print("❌ Not enough stock.")
        conn.close()
        return
    new_qty = item[2] - qty
    c.execute("UPDATE items SET quantity=? WHERE id=?", (new_qty, item[0]))
    c.execute("INSERT INTO sales (user, item_id, qty_sold) VALUES (?, ?, ?)", ("admin", item[0], qty))
    conn.commit()
    log_action("admin", "sell", item[0], qty, "N/A")
    check_low_stock(item[0])
    conn.close()
    print(f"✅ Sold {qty} of {item[1]}.")

def remove_item():
    barcode = input("Barcode of item to remove: ").strip()
    conn = connect_db()
    c = conn.cursor()
    c.execute("SELECT id, name FROM items WHERE barcode=?", (barcode,))
    item = c.fetchone()
    if not item:
        print("❌ Item not found.")
        conn.close()
        return
    c.execute("DELETE FROM items WHERE id=?", (item[0],))
    conn.commit()
    log_action("admin", "remove", item[0], 0, "N/A")
    conn.close()
    print(f"✅ Item '{item[1]}' removed.")

# ------------------------
# Helper Functions
# ------------------------
def log_action(user, action, item_id, quantity, location):
    conn = connect_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO logs (user, action, item_id, quantity, location)
        VALUES (?, ?, ?, ?, ?)
    """, (user, action, item_id, quantity, location))
    conn.commit()
    conn.close()

def check_low_stock(item_id):
    conn = connect_db()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key='low_stock_threshold'")
    row = c.fetchone()
    threshold = int(row[0]) if row else 5
    c.execute("SELECT name, quantity FROM items WHERE id=?", (item_id,))
    item = c.fetchone()
    if item and item[1] is not None and item[1] <= threshold:
        print(f"⚠ LOW STOCK ALERT: {item[0]} has only {item[1]} left!")
    conn.close()

def view_inventory():
    conn = connect_db()
    c = conn.cursor()
    c.execute("SELECT id, name, barcode, quantity, sale_price, location FROM items ORDER BY id")
    items = c.fetchall()
    conn.close()
    print("\n--- INVENTORY ---")
    if not items:
        print("No items found.")
        return
    for i in items:
        print(f"ID:{i[0]} | {i[1]} | Barcode:{i[2]} | Qty:{i[3]} | Price:{i[4]} | Loc:{i[5]}")

def view_logs():
    conn = connect_db()
    c = conn.cursor()
    c.execute("SELECT timestamp, user, action, item_id, quantity FROM logs ORDER BY timestamp DESC LIMIT 20")
    logs = c.fetchall()
    conn.close()
    print("\n--- LAST LOGS ---")
    if not logs:
        print("No logs.")
        return
    for l in logs:
        print(l)

def get_all_items():
    conn = connect_db()
    c = conn.cursor()
    c.execute("SELECT barcode, name, category, quantity, sale_price, location FROM items ORDER BY id")
    rows = c.fetchall()
    conn.close()
    return rows

# ------------------------
# Phase 3: Transactions (multi-item)
# ------------------------
def create_transaction():
    """
    Interactive flow to create a multi-item transaction.
    Types: sale (reduces stock), purchase/restock (increases stock), adjustment, damage, return.
    """
    ttype = input("Transaction Type (sale/purchase/restock/adjustment/damage/return): ").strip().lower()
    if ttype not in ("sale", "purchase", "restock", "adjustment", "damage", "return"):
        print("❌ Invalid type.")
        return

    performed_by = input("Performed by (username) [default: admin]: ").strip() or "admin"
    customer = input("Customer name (optional): ").strip()
    notes = input("Notes (optional): ").strip()

    items_list = []
    while True:
        barcode = input("Scan/Enter barcode (or type 'done' to finish): ").strip()
        if barcode.lower() == "done":
            break
        conn = connect_db(); c = conn.cursor()
        c.execute("SELECT id, name, quantity, sale_price, purchase_price FROM items WHERE barcode=?", (barcode,))
        row = c.fetchone()
        conn.close()
        if not row:
            print("❌ Item not found for barcode:", barcode)
            continue
        item_id, name, current_qty, sale_price, purchase_price = row
        print(f"Found: {name} | Current qty: {current_qty}")
        try:
            q = int(input("Quantity (positive integer): ").strip())
        except ValueError:
            print("❌ Invalid quantity.")
            continue

        # determine quantity change sign:
        if ttype in ("sale", "damage", "return") and ttype != "purchase" and ttype != "restock":
            # For 'sale' and 'damage', we'll reduce stock (negative change)
            pass

        # For clarity, define change so that positive always means stock increase.
        if ttype in ("purchase", "restock"):
            change = q  # add to stock
        elif ttype == "sale":
            change = -q  # reduce stock
        elif ttype == "damage":
            change = -q
        elif ttype == "return":
            change = q
        elif ttype == "adjustment":
            # ask whether it's +/- adjustment
            adj = input("Adjustment + or - ? (enter '+' or '-'): ").strip()
            if adj == "+":
                change = q
            elif adj == "-":
                change = -q
            else:
                print("❌ Invalid adjustment sign.")
                continue
        else:
            change = -q

        quantity_before = current_qty
        quantity_after = current_qty + change

        if quantity_after < 0:
            print("❌ Not enough stock. Current:", current_qty)
            continue

        unit_price = sale_price if (sale_price is not None) else (purchase_price if purchase_price is not None else 0.0)
        items_list.append({
            "item_id": item_id,
            "barcode": barcode,
            "item_name": name,
            "quantity_changed": change,
            "quantity_before": quantity_before,
            "quantity_after": quantity_after,
            "unit_price": unit_price
        })
        print(f"Added to transaction: {name} | change: {change} | after: {quantity_after}")

    if not items_list:
        print("No items in transaction. Aborting.")
        return

    # compute total (for sale type we sum qty_sold * sale_price). For purchases we can sum cost if purchase_price present.
    total_amount = 0.0
    for it in items_list:
        if ttype == "sale":
            qty_sold = -it["quantity_changed"] if it["quantity_changed"] < 0 else it["quantity_changed"]
            total_amount += qty_sold * (it["unit_price"] or 0.0)
        elif ttype in ("purchase", "restock"):
            total_amount += it["quantity_changed"] * (it["unit_price"] or 0.0)
        else:
            # adjustments/damage/return: optional zero or keep computed absolute value
            total_amount += abs(it["quantity_changed"]) * (it["unit_price"] or 0.0)

    print("\n--- Transaction Summary ---")
    print(f"Type: {ttype} | Items: {len(items_list)} | Total approx: {total_amount:.2f}")
    for it in items_list:
        print(f"{it['item_name']} | change: {it['quantity_changed']} | before: {it['quantity_before']} | after: {it['quantity_after']}")

    confirm = input("Confirm transaction? (y/n): ").strip().lower()
    if confirm != "y":
        print("Transaction cancelled.")
        return

    # Persist transaction atomically
    conn = connect_db(); c = conn.cursor()
    try:
        c.execute("INSERT INTO transactions (user, type, customer, total_amount, notes) VALUES (?, ?, ?, ?, ?)",
                  (performed_by, ttype, customer, total_amount, notes))
        transaction_id = c.lastrowid

        for it in items_list:
            # update item stock
            c.execute("UPDATE items SET quantity=? WHERE id=?", (it["quantity_after"], it["item_id"]))
            # insert into transaction_items
            c.execute("""
                INSERT INTO transaction_items
                (transaction_id, item_id, barcode, item_name, quantity_changed, quantity_before, quantity_after, unit_price)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (transaction_id, it["item_id"], it["barcode"], it["item_name"],
                  it["quantity_changed"], it["quantity_before"], it["quantity_after"], it["unit_price"]))

            # for compatibility, if this was a sale, insert into sales table (one row per item)
            if ttype == "sale":
                qty_sold = -it["quantity_changed"] if it["quantity_changed"] < 0 else it["quantity_changed"]
                c.execute("INSERT INTO sales (user, item_id, qty_sold) VALUES (?, ?, ?)",
                          (performed_by, it["item_id"], qty_sold))

            # log action
            action_label = ttype
            c.execute("INSERT INTO logs (user, action, item_id, quantity, location) VALUES (?, ?, ?, ?, ?)",
                      (performed_by, action_label, it["item_id"], it["quantity_changed"], "N/A"))

        conn.commit()
        print(f"✅ Transaction saved. ID: {transaction_id}")
    except Exception as e:
        conn.rollback()
        print("❌ Failed to save transaction:", e)
    finally:
        conn.close()

def view_transactions(limit=50):
    conn = connect_db(); c = conn.cursor()
    c.execute("SELECT id, timestamp, user, type, customer, total_amount FROM transactions ORDER BY timestamp DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    print("\n--- TRANSACTIONS (recent) ---")
    if not rows:
        print("No transactions found.")
        return
    for r in rows:
        print(f"ID:{r[0]} | {r[1]} | {r[2]} | {r[3]} | Customer:{r[4]} | Total:{(r[5] or 0):.2f}")

def view_transaction_details():
    tid = input("Enter transaction ID to view details: ").strip()
    try:
        tid = int(tid)
    except ValueError:
        print("❌ Invalid ID.")
        return
    conn = connect_db(); c = conn.cursor()
    c.execute("SELECT id, timestamp, user, type, customer, total_amount, notes FROM transactions WHERE id=?", (tid,))
    tx = c.fetchone()
    if not tx:
        print("❌ Transaction not found.")
        conn.close()
        return
    print(f"\nTransaction {tx[0]} | {tx[1]} | {tx[2]} | {tx[3]} | customer: {tx[4]} | total: {(tx[5] or 0):.2f}")
    if tx[6]:
        print("Notes:", tx[6])
    c.execute("SELECT barcode, item_name, quantity_changed, quantity_before, quantity_after, unit_price FROM transaction_items WHERE transaction_id=?", (tid,))
    items = c.fetchall()
    conn.close()
    print("\nItems:")
    for it in items:
        print(f"{it[1]} | barcode:{it[0]} | change:{it[2]} | before:{it[3]} | after:{it[4]} | unit_price:{it[5]}")

def export_transactions_csv(filename=None):
    import csv
    rows = []
    conn = connect_db(); c = conn.cursor()
    c.execute("SELECT id, timestamp, user, type, customer, total_amount FROM transactions ORDER BY timestamp DESC")
    txs = c.fetchall()
    if not txs:
        print("No transactions to export.")
        conn.close(); return
    if not filename:
        filename = f"transactions_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["transaction_id", "timestamp", "user", "type", "customer", "total_amount", "item_barcode", "item_name", "qty_changed", "qty_before", "qty_after", "unit_price"])
        for tx in txs:
            tx_id = tx[0]
            c.execute("SELECT barcode, item_name, quantity_changed, quantity_before, quantity_after, unit_price FROM transaction_items WHERE transaction_id=?", (tx_id,))
            items = c.fetchall()
            if items:
                for it in items:
                    writer.writerow([tx[0], tx[1], tx[2], tx[3], tx[4], tx[5], it[0], it[1], it[2], it[3], it[4], it[5]])
            else:
                writer.writerow([tx[0], tx[1], tx[2], tx[3], tx[4], tx[5], "", "", "", "", "", ""])
    conn.close()
    print(f"✅ Transactions exported to {filename}")

# ------------------------
# Export Functions
# ------------------------
def export_inventory_to_excel():
    if not HAS_OPENPYXL:
        print("❌ openpyxl is not installed. Run: pip install openpyxl")
        return

    rows = get_all_items()
    if not rows:
        print("❌ No items to export.")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"inventory_export_{timestamp}.xlsx"

    wb = Workbook()
    ws = wb.active
    ws.title = "Inventory"

    headers = ["Barcode", "Name", "Category", "Quantity", "Sale Price", "Location"]
    ws.append(headers)
    for col in range(1, len(headers) + 1):
        ws.cell(row=1, column=col).font = Font(bold=True)

    for r in rows:
        ws.append([
            r[0] or "",
            r[1] or "",
            r[2] or "",
            r[3] if r[3] is not None else 0,
            float(r[4]) if r[4] is not None else 0.0,
            r[5] or ""
        ])

    wb.save(filename)
    print(f"✅ Excel exported: {os.path.abspath(filename)}")

def export_inventory_to_pdf():
    if not HAS_REPORTLAB:
        print("❌ reportlab is not installed. Run: pip install reportlab")
        return

    rows = get_all_items()
    if not rows:
        print("❌ No items to export.")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"inventory_report_{timestamp}.pdf"

    data = [["Barcode", "Name", "Category", "Quantity", "Sale Price", "Location"]]
    for r in rows:
        data.append([
            r[0] or "",
            r[1] or "",
            r[2] or "",
            str(r[3] if r[3] is not None else 0),
            f"{(r[4] if r[4] is not None else 0):.2f}",
            r[5] or ""
        ])

    doc = SimpleDocTemplate(filename, pagesize=letter)
    table = Table(data, repeatRows=1)
    style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ])
    table.setStyle(style)
    elements = [table]
    doc.build(elements)
    print(f"✅ PDF exported: {os.path.abspath(filename)}")

# ------------------------
# CLI Menu & Arg handling
# ------------------------
def menu():
    while True:
        print("\n=== Inventory CLI ===")
        print("1. View Inventory")
        print("2. Add Item")
        print("3. Update Item Quantity")
        print("4. Sell Item")
        print("5. Remove Item")
        print("6. View Logs")
        print("7. Export Inventory to Excel (.xlsx)")
        print("8. Export Inventory to PDF (.pdf)")
        print("9. Create Transaction (sale/purchase/adjustment/damage/return)")
        print("10. View Transactions (recent)")
        print("11. View Transaction Details")
        print("12. Export Transactions to CSV")
        print("0. Exit")
        choice = input("Select: ").strip()
        if choice == "1":
            view_inventory()
        elif choice == "2":
            add_item()
        elif choice == "3":
            update_item()
        elif choice == "4":
            sell_item()
        elif choice == "5":
            remove_item()
        elif choice == "6":
            view_logs()
        elif choice == "7":
            export_inventory_to_excel()
        elif choice == "8":
            export_inventory_to_pdf()
        elif choice == "9":
            create_transaction()    
        elif choice == "10":
            view_transactions()     
        elif choice == "11":
            view_transaction_details()
        elif choice == "12":
            export_transactions_csv()
        elif choice == "0":
            break
        else:
            print("❌ Invalid choice.")

def run_cli_or_args():
    # Usage: python inventory_cli.py export_excel
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd in ("export_excel", "export-excel", "xlsx"):
            export_inventory_to_excel(); return
        if cmd in ("export_pdf", "export-pdf", "pdf"):
            export_inventory_to_pdf(); return
        if cmd in ("view", "list"):
            view_inventory(); return
        print("Unknown argument. Running interactive menu.")
    menu()

if __name__ == "__main__":
    run_cli_or_args()
