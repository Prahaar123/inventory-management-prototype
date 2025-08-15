# inventory_gui.py
import sqlite3
import threading
import queue
import json
import os
import socket
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # Create tables if they don't exist
    c.execute("""
    CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        category TEXT,
        barcode TEXT UNIQUE,
        quantity INTEGER,
        supplier TEXT,
        purchase_price REAL,
        sale_price REAL,
        location TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        user TEXT,
        action TEXT,
        item_id INTEGER,
        quantity INTEGER,
        location TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        user TEXT,
        type TEXT,
        customer TEXT,
        total_amount REAL,
        notes TEXT
    )
    """)

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
        unit_price REAL
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS sales (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        user TEXT,
        item_id INTEGER,
        qty_Removed INTEGER
    )
    """)

    conn.commit()
    conn.close()


# try to import camera libs
try:
    import cv2
    from pyzbar import pyzbar
    HAS_CAMERA_LIBS = True
except Exception:
    HAS_CAMERA_LIBS = False

DB_FILE = "inventory.db"
SCAN_PORT = 8000               # HTTP POST endpoint: http://<PC_IP>:8000/scan
scan_queue = queue.Queue()     # thread-safe queue for incoming scans

# -----------------------
# Lightweight HTTP server to accept POST scan data
# -----------------------
class ScanHandler(BaseHTTPRequestHandler):
    def _send_ok(self, text="OK"):
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.wfile.write(text.encode('utf-8'))

    def do_POST(self):
        if self.path != "/scan":
            self.send_response(404)
            self.end_headers()
            return
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        code = None
        # try JSON
        try:
            data = json.loads(body.decode('utf-8'))
            if isinstance(data, dict):
                code = data.get("code") or data.get("barcode") or data.get("value")
        except Exception:
            pass
        # try form-encoded
        if not code:
            try:
                qs = parse_qs(body.decode('utf-8'))
                if 'code' in qs:
                    code = qs['code'][0]
                elif 'barcode' in qs:
                    code = qs['barcode'][0]
            except Exception:
                pass
        if code:
            scan_queue.put(code.strip())
            self._send_ok("scanned")
        else:
            self._send_ok("no_code")

    # silence logging
    def log_message(self, format, *args):
        return

def start_scan_server(host="0.0.0.0", port=SCAN_PORT):
    def server_thread():
        try:
            httpd = HTTPServer((host, port), ScanHandler)
            httpd.serve_forever()
        except Exception as e:
            print("Scan server stopped/error:", e)
    t = threading.Thread(target=server_thread, daemon=True)
    t.start()
    return t

# -----------------------
# DB helpers
# -----------------------
def connect_db():
    return sqlite3.connect(DB_FILE)

def fetch_item_by_barcode(barcode):
    conn = connect_db(); c = conn.cursor()
    c.execute("SELECT id, name, category, barcode, quantity, supplier, purchase_price, sale_price, location FROM items WHERE barcode=?", (barcode,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    keys = ["id","name","category","barcode","quantity","supplier","purchase_price","sale_price","location"]
    return dict(zip(keys, row))

def add_item_db(name, category, barcode, qty, supplier, purchase_price, sale_price, location, create_barcode_image=False):
    conn = connect_db(); c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO items (name, category, barcode, quantity, supplier, purchase_price, sale_price, location)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, category, barcode, qty, supplier, purchase_price, sale_price, location))
        conn.commit()
        item_id = c.lastrowid
        # log
        c.execute("INSERT INTO logs (user, action, item_id, quantity, location) VALUES (?, ?, ?, ?, ?)",
                  ("admin", "add", item_id, qty, location or "N/A"))
        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        raise
    conn.close()
    return item_id

def update_item_qty_db(item_id, new_qty):
    conn = connect_db(); c = conn.cursor()
    c.execute("UPDATE items SET quantity=? WHERE id=?", (new_qty, item_id))
    conn.commit()
    conn.close()

def create_transaction_db(performed_by, ttype, items_list, customer=None, notes=None):
    conn = connect_db(); c = conn.cursor()
    try:
        total_amount = 0.0
        for it in items_list:
            total_amount += abs(it.get("quantity_changed", 0)) * (it.get("unit_price") or 0.0)
        c.execute("INSERT INTO transactions (user, type, customer, total_amount, notes) VALUES (?, ?, ?, ?, ?)",
                  (performed_by, ttype, customer, total_amount, notes))
        tx_id = c.lastrowid
        for it in items_list:
            c.execute("UPDATE items SET quantity=? WHERE id=?", (it["quantity_after"], it["item_id"]))
            c.execute("""INSERT INTO transaction_items
                (transaction_id, item_id, barcode, item_name, quantity_changed, quantity_before, quantity_after, unit_price)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                      (tx_id, it["item_id"], it["barcode"], it["item_name"], it["quantity_changed"],
                       it["quantity_before"], it["quantity_after"], it.get("unit_price") or 0.0))
            if ttype == "sale":
                qty_Removed = -it["quantity_changed"] if it["quantity_changed"] < 0 else it["quantity_changed"]
                c.execute("INSERT INTO sales (user, item_id, qty_Removed) VALUES (?, ?, ?)", (performed_by, it["item_id"], qty_Removed))
            c.execute("INSERT INTO logs (user, action, item_id, quantity, location) VALUES (?, ?, ?, ?, ?)",
                      (performed_by, ttype, it["item_id"], it["quantity_changed"], it.get("location","N/A")))
        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        raise
    conn.close()
    return tx_id

# -----------------------
# Utility: local IP
# -----------------------
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

# -----------------------
# Camera scan helper
# -----------------------
def scan_barcode_from_camera(cancel_key='q', camera_index=0, window_title="Scan Barcode - press 'q' to cancel"):
    """
    Opens the webcam, scans for barcodes using pyzbar, and returns the first barcode string found.
    Returns None if cancelled or no camera libs available.
    """
    if not HAS_CAMERA_LIBS:
        return None

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        return None

    barcode_data = None
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        barcodes = pyzbar.decode(frame)
        for barcode in barcodes:
            try:
                barcode_data = barcode.data.decode('utf-8')
            except Exception:
                barcode_data = None
            if barcode_data:
                # draw rectangle and break
                (x, y, w, h) = barcode.rect
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                cv2.putText(frame, barcode_data, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,0), 2)
                break
        cv2.imshow(window_title, frame)
        if barcode_data:
            # small delay to show the green rectangle
            cv2.waitKey(500)
            break
        if cv2.waitKey(1) & 0xFF == ord(cancel_key):
            barcode_data = None
            break

    cap.release()
    cv2.destroyAllWindows()
    return barcode_data

# -----------------------
# GUI
# -----------------------
class InventoryGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Inventory Manager — Scanner-ready")
        self.current_popup = None   # keep track of active popup ("add" or "Remove")
        # active_entry and active_lookup used by HTTP scan-injection
        self.active_entry = None
        self.active_lookup = None

        self.setup_main()

        # start HTTP scan server (receives scans from phone / other tools) - optional
        try:
            start_scan_server()
        except Exception as e:
            print("Could not start scan server:", e)

        # start polling for scans from network (POST -> scan_queue)
        self.root.after(150, self.poll_scan_queue)

    def poll_scan_queue(self):
        try:
            while True:
                code = scan_queue.get_nowait()
                try:
                    ent = getattr(self, "active_entry", None)
                    lookup_fn = getattr(self, "active_lookup", None)
                    if ent and lookup_fn:
                        ent.delete(0, tk.END)
                        ent.insert(0, code)
                        lookup_fn()
                    else:
                        item = fetch_item_by_barcode(code)
                        if item:
                            messagebox.showinfo("Scan received", f"Scanned: {item['name']} (Qty: {item['quantity']})")
                        else:
                            messagebox.showinfo("Scan received", f"Barcode {code} (not found)")
                except Exception as e:
                    print("Error handling scan:", e)
        except queue.Empty:
            pass
        self.root.after(150, self.poll_scan_queue)

    def setup_main(self):
        frame = ttk.Frame(self.root, padding=12)
        frame.grid(sticky="nsew")
        self.root.columnconfigure(0, weight=1); self.root.rowconfigure(0, weight=1)

        title = ttk.Label(frame, text="Inventory Manager", font=("Segoe UI", 16, "bold"))
        title.grid(row=0, column=0, columnspan=3, pady=(0,10), sticky="w")

        ip = get_local_ip()
        info = ttk.Label(frame, text=f"Scan endpoint (HTTP POST): http://{ip}:{SCAN_PORT}/scan  — hardware scanner works by focusing barcode field.")
        info.grid(row=1, column=0, columnspan=3, sticky="w", pady=(0,8))

        btn_inv = ttk.Button(frame, text="Open Inventory", command=self.open_inventory_window, width=20)
        btn_inv.grid(row=2, column=0, padx=6, pady=6)
        btn_logs = ttk.Button(frame, text="Check Logs", command=self.open_logs_window, width=20)
        btn_logs.grid(row=2, column=1, padx=6, pady=6)
        btn_add = ttk.Button(frame, text="Add Item (scan)", command=self.open_add_item_window, width=20)
        btn_add.grid(row=3, column=0, padx=6, pady=6)
        btn_Remove = ttk.Button(frame, text="Remove Item (scan)", command=self.open_Remove_item_window, width=20)
        btn_Remove.grid(row=3, column=1, padx=6, pady=6)
        btn_export = ttk.Button(frame, text="Export Transactions CSV", command=self.export_transactions_csv, width=20)
        btn_export.grid(row=4, column=0, padx=6, pady=6)
        btn_exit = ttk.Button(frame, text="Exit", command=self.root.quit, width=20)
        btn_exit.grid(row=4, column=1, padx=6, pady=6)

    # -----------------------
    # Inventory window
    # -----------------------
    def open_inventory_window(self):
        w = tk.Toplevel(self.root)
        w.title("Inventory")
        w.geometry("900x400")
        tree = ttk.Treeview(w, columns=("id","name","barcode","qty","price","location"), show="headings")
        for col, text in [("id","ID"),("name","Name"),("barcode","Barcode"),("qty","Qty"),("price","Price"),("location","Location")]:
            tree.heading(col, text=text); tree.column(col, width=120)
        tree.pack(fill="both", expand=True)
        def refresh():
            for r in tree.get_children(): tree.delete(r)
            conn = connect_db(); c = conn.cursor()
            c.execute("SELECT id, name, barcode, quantity, sale_price, location FROM items ORDER BY id")
            for row in c.fetchall():
                tree.insert("", "end", values=(row[0], row[1], row[2], row[3], row[4], row[5]))
            conn.close()
        btns = ttk.Frame(w); btns.pack(fill="x", pady=6)
        ttk.Button(btns, text="Refresh", command=refresh).pack(side="left", padx=6)
        ttk.Button(btns, text="Close", command=w.destroy).pack(side="right", padx=6)
        refresh()

        # -----------------------
    # Logs window
    # -----------------------
    def open_logs_window(self):
        w = tk.Toplevel(self.root)
        w.title("Logs")
        w.geometry("800x400")
        tree = ttk.Treeview(w, columns=("time","user","action","item","qty"), show="headings")
        for col, text in [("time","Time"),("user","User"),("action","Action"),("item","ItemID"),("qty","Qty")]:
            tree.heading(col, text=text); tree.column(col, width=140)
        tree.pack(fill="both", expand=True)

        def refresh_logs():
            for r in tree.get_children():
                tree.delete(r)
            conn = connect_db(); c = conn.cursor()
            c.execute("SELECT timestamp, user, action, item_id, quantity FROM logs ORDER BY timestamp DESC LIMIT 200")
            rows = c.fetchall()
            conn.close()
            for r in rows:
                tree.insert("", "end", values=(r[0], r[1], r[2], r[3], r[4]))
            return rows

        rows = refresh_logs()

        def export_logs_pdf():
            if not rows:
                messagebox.showinfo("No logs", "No logs to export.")
                return
            filename = f"logs_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            styles = getSampleStyleSheet()
            doc = SimpleDocTemplate(filename, pagesize=A4)
            elements = []
            elements.append(Paragraph("Inventory Logs", styles['Title']))
            elements.append(Spacer(1, 12))
            for row in rows:
                log_line = f"Time: {row[0]}, User: {row[1]}, Action: {row[2]}, ItemID: {row[3]}, Qty: {row[4]}"
                elements.append(Paragraph(log_line, styles['Normal']))
                elements.append(Spacer(1, 6))
            doc.build(elements)
            messagebox.showinfo("Exported", f"Logs exported to {os.path.abspath(filename)}")

        btns = ttk.Frame(w)
        btns.pack(fill="x", pady=6)
        ttk.Button(btns, text="Refresh", command=lambda: refresh_logs()).pack(side="left", padx=6)
        ttk.Button(btns, text="Export as PDF", command=export_logs_pdf).pack(side="left", padx=6)
        ttk.Button(btns, text="Close", command=w.destroy).pack(side="right", padx=6)



    # -----------------------
    # Add item popup (scan first)
    # -----------------------
    def open_add_item_window(self):
        self.current_popup = "add"
        w = tk.Toplevel(self.root)
        w.title("Add Item (scan barcode)")
        w.geometry("520x360")

        lbl = ttk.Label(w, text="Scan barcode (or type) then click Lookup", font=("Segoe UI", 11))
        lbl.pack(pady=6)

        frm = ttk.Frame(w)
        frm.pack(fill="x", padx=8, pady=6)

        ttk.Label(frm, text="Barcode:").grid(row=0, column=0, sticky="e")

        # use instance var so poller and camera func can update it
        self.add_barcode_var = tk.StringVar()
        ent_barcode = ttk.Entry(frm, textvariable=self.add_barcode_var, width=30)
        ent_barcode.grid(row=0, column=1, padx=6, pady=6)
        ent_barcode.focus_set()

        # Lookup function will be defined below; bind Enter to it (will use the inner do_lookup)
        # we set active_entry and active_lookup so network scanner can inject
        self.active_entry = ent_barcode

        # Lookup button (do_lookup defined after fields)
        # We'll set active_lookup to the actual lookup function later
        ttk.Button(frm, text="Lookup", command=lambda: None).grid(row=0, column=2, padx=6)

        # Camera scan button
        ttk.Button(frm, text="Scan Barcode (Camera)", command=lambda: self._start_camera_scan_for("add", ent_barcode)).grid(row=0, column=3, padx=6)

        # Define form variables here so they are accessible in nested funcs
        self.name_var = tk.StringVar()
        self.cat_var = tk.StringVar()
        self.qty_var = tk.IntVar(value=1)
        self.supplier_var = tk.StringVar()
        self.pp_var = tk.DoubleVar(value=0.0)
        self.sp_var = tk.DoubleVar(value=0.0)
        self.loc_var = tk.StringVar()

        f2 = ttk.Frame(w)
        f2.pack(fill="both", expand=True, padx=8, pady=6)

        ttk.Label(f2, text="Name:").grid(row=0, column=0, sticky="e")
        ttk.Entry(f2, textvariable=self.name_var, width=40).grid(row=0, column=1, padx=6, pady=4)
        ttk.Label(f2, text="Category:").grid(row=1, column=0, sticky="e")
        ttk.Entry(f2, textvariable=self.cat_var, width=40).grid(row=1, column=1, padx=6, pady=4)
        ttk.Label(f2, text="Quantity:").grid(row=2, column=0, sticky="e")
        ttk.Entry(f2, textvariable=self.qty_var, width=20).grid(row=2, column=1, padx=6, pady=4, sticky="w")
        ttk.Label(f2, text="Supplier:").grid(row=3, column=0, sticky="e")
        ttk.Entry(f2, textvariable=self.supplier_var, width=40).grid(row=3, column=1, padx=6, pady=4)
        ttk.Label(f2, text="Purchase Price:").grid(row=4, column=0, sticky="e")
        ttk.Entry(f2, textvariable=self.pp_var, width=20).grid(row=4, column=1, padx=6, pady=4, sticky="w")
        ttk.Label(f2, text="Sale Price:").grid(row=5, column=0, sticky="e")
        ttk.Entry(f2, textvariable=self.sp_var, width=20).grid(row=5, column=1, padx=6, pady=4, sticky="w")
        ttk.Label(f2, text="Location:").grid(row=6, column=0, sticky="e")
        ttk.Entry(f2, textvariable=self.loc_var, width=40).grid(row=6, column=1, padx=6, pady=4)

        info_lbl = ttk.Label(w, text="", foreground="blue")
        info_lbl.pack(pady=4)

        # Define the lookup function
        def do_lookup():
            code = self.add_barcode_var.get().strip()
            if not code:
                messagebox.showwarning("No barcode", "Please scan or enter a barcode.")
                return
            item = fetch_item_by_barcode(code)
            if item:
                # fill form with existing values
                self.name_var.set(item["name"])
                self.cat_var.set(item.get("category", ""))
                self.qty_var.set(item["quantity"])
                self.supplier_var.set(item.get("supplier", ""))
                self.pp_var.set(item.get("purchase_price", 0.0))
                self.sp_var.set(item.get("sale_price", 0.0))
                self.loc_var.set(item.get("location", ""))
                info_lbl.config(text=f"Item exists (ID {item['id']}). Save will update quantity.")
            else:
                info_lbl.config(text="New item. Fill details and Save.")

        # now set active_lookup to this do_lookup
        self.active_lookup = do_lookup
        # rebind Lookup button to actual function
        # find the lookup button in frame children and reconfigure: simpler to just create a new one
        # (we will create a small local button row below)
        # Save button handler
        def on_save():
            barcode = self.add_barcode_var.get().strip()
            if not barcode:
                messagebox.showwarning("Barcode missing", "Please scan or enter a barcode.")
                return

            name = self.name_var.get().strip()
            category = self.cat_var.get().strip()
            try:
                qty = int(self.qty_var.get())
            except Exception:
                messagebox.showerror("Invalid", "Quantity must be integer.")
                return
            supplier = self.supplier_var.get().strip()
            try:
                purchase_price = float(self.pp_var.get())
            except Exception:
                purchase_price = 0.0
            try:
                sale_price = float(self.sp_var.get())
            except Exception:
                sale_price = 0.0
            location = self.loc_var.get().strip()

            existing = fetch_item_by_barcode(barcode)
            try:
                if existing:
                    new_qty = existing["quantity"] + qty
                    update_item_qty_db(existing["id"], new_qty)
                    messagebox.showinfo("Updated", f"Updated {existing['name']} quantity to {new_qty}")
                else:
                    add_item_db(name, category, barcode, qty, supplier, purchase_price, sale_price, location, create_barcode_image=False)
                    messagebox.showinfo("Added", f"Added new item: {name}")
                w.destroy()
            except Exception as e:
                messagebox.showerror("DB error", str(e))

        btns = ttk.Frame(w)
        btns.pack(pady=6)
        ttk.Button(btns, text="Lookup", command=do_lookup).pack(side="left", padx=6)
        ttk.Button(btns, text="Save", command=on_save).pack(side="left", padx=6)
        ttk.Button(btns, text="Cancel", command=w.destroy).pack(side="right", padx=6)

        w.protocol("WM_DELETE_WINDOW", lambda: (setattr(self, "current_popup", None), w.destroy()))

    # -----------------------
    # Remove item popup (scan workflow)
    # -----------------------
    def open_Remove_item_window(self):
        self.current_popup = "Remove"
        w = tk.Toplevel(self.root)
        w.title("Remove Item (scan)")
        w.geometry("480x260")

        ttk.Label(w, text="Scan barcode to Remove (or type and press Lookup)").pack(pady=6)

        frm = ttk.Frame(w)
        frm.pack(fill="x", padx=8, pady=4)

        ttk.Label(frm, text="Barcode:").grid(row=0, column=0, sticky="e")

        # use instance var
        self.Remove_barcode_var = tk.StringVar()
        ent_barcode = ttk.Entry(frm, textvariable=self.Remove_barcode_var, width=30)
        ent_barcode.grid(row=0, column=1, padx=6)
        ent_barcode.focus_set()
        # set active_entry to allow scan injection from network scans
        self.active_entry = ent_barcode

        ttk.Button(frm, text="Lookup", command=lambda: None).grid(row=0, column=2, padx=6)
        # camera scan button
        ttk.Button(frm, text="Scan Barcode (Camera)", command=lambda: self._start_camera_scan_for("Remove", ent_barcode)).grid(row=0, column=3, padx=6)

        # Variables for item details
        self.Remove_name_var = tk.StringVar()
        self.Remove_cur_qty_var = tk.IntVar()
        self.Remove_price_var = tk.DoubleVar()
        self.Remove_id_var = tk.IntVar()

        # Show item details
        details_frame = ttk.Frame(w)
        details_frame.pack(fill="x", padx=8, pady=6)

        ttk.Label(details_frame, text="Name:").grid(row=0, column=0, sticky="e")
        ttk.Label(details_frame, textvariable=self.Remove_name_var).grid(row=0, column=1, sticky="w")

        ttk.Label(details_frame, text="Current Quantity:").grid(row=1, column=0, sticky="e")
        ttk.Label(details_frame, textvariable=self.Remove_cur_qty_var).grid(row=1, column=1, sticky="w")

        ttk.Label(details_frame, text="Sale Price:").grid(row=2, column=0, sticky="e")
        ttk.Label(details_frame, textvariable=self.Remove_price_var).grid(row=2, column=1, sticky="w")

        ttk.Label(details_frame, text="Quantity to Remove:").grid(row=3, column=0, sticky="e")
        qty_to_Remove_var = tk.IntVar(value=1)
        qty_entry = ttk.Entry(details_frame, textvariable=qty_to_Remove_var, width=10)
        qty_entry.grid(row=3, column=1, sticky="w")

        info_lbl = ttk.Label(w, text="", foreground="blue")
        info_lbl.pack(pady=4)

        # define lookup and Remove functions
        def do_lookup_Remove():
            code = self.Remove_barcode_var.get().strip()
            if not code:
                messagebox.showwarning("No barcode", "Please scan or enter a barcode.")
                return
            item = fetch_item_by_barcode(code)
            if not item:
                messagebox.showerror("Not found", "Item not found in DB.")
                return
            self.Remove_name_var.set(item["name"])
            self.Remove_cur_qty_var.set(item["quantity"])
            self.Remove_price_var.set(item.get("sale_price", 0.0))
            self.Remove_id_var.set(item["id"])
            info_lbl.config(text="Item found. Enter quantity to Remove and click Remove.")

        def on_Remove():
            item_id = self.Remove_id_var.get()
            if item_id == 0:
                messagebox.showerror("No item", "Please lookup an item first.")
                return

        # attach lookup & Remove handlers to buttons (replace placeholder Lookup button)
        # find & replace the Lookup button: simpler to add a small row of buttons below
        btns2 = ttk.Frame(w)
        btns2.pack(pady=6)
        ttk.Button(btns2, text="Lookup", command=do_lookup_Remove).pack(side="left", padx=6)
        def perform_Remove():
            try:
                Remove_qty = int(qty_to_Remove_var.get())
            except Exception:
                messagebox.showerror("Invalid quantity", "Quantity must be an integer.")
                return
            current_qty = self.Remove_cur_qty_var.get()
            if Remove_qty <= 0:
                messagebox.showerror("Invalid quantity", "Quantity to Remove must be positive.")
                return
            if Remove_qty > current_qty:
                messagebox.showerror("Insufficient quantity", "Not enough stock to Remove.")
                return
            item_id = self.Remove_id_var.get()
            try:
                new_qty = current_qty - Remove_qty
                update_item_qty_db(item_id, new_qty)
                # create transaction record
                it = {
                    "item_id": item_id,
                    "barcode": self.Remove_barcode_var.get().strip(),
                    "item_name": self.Remove_name_var.get(),
                    "quantity_changed": -Remove_qty,
                    "quantity_before": current_qty,
                    "quantity_after": new_qty,
                    "unit_price": self.Remove_price_var.get()
                }
                create_transaction_db("admin", "sale", [it], customer=None, notes="Removed via GUI")
                messagebox.showinfo("Removed", f"Removed {Remove_qty} units of {self.Remove_name_var.get()}. New quantity: {new_qty}")
                w.destroy()
            except Exception as e:
                messagebox.showerror("DB error", str(e))

        ttk.Button(btns2, text="Remove", command=perform_Remove).pack(side="left", padx=6)
        ttk.Button(btns2, text="Cancel", command=w.destroy).pack(side="right", padx=6)

        # set active lookup so network scans inject properly
        self.active_lookup = do_lookup_Remove

        w.protocol("WM_DELETE_WINDOW", lambda: (setattr(self, "current_popup", None), w.destroy()))

    # -----------------------
    # Export transactions CSV (simple wrapper)
    # -----------------------
    def export_transactions_csv(self):
        import csv
        filename = f"transactions_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        conn = connect_db(); c = conn.cursor()
        c.execute("SELECT id, timestamp, user, type, customer, total_amount FROM transactions ORDER BY timestamp DESC")
        txs = c.fetchall()
        if not txs:
            messagebox.showinfo("No transactions", "There are no transactions to export.")
            conn.close(); return
        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["transaction_id","timestamp","user","type","customer","total_amount","item_barcode","item_name","qty_changed","qty_before","qty_after","unit_price"])
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
        messagebox.showinfo("Exported", f"Transactions exported to {os.path.abspath(filename)}")

    # -----------------------
    # Helper: start camera scan for add/Remove (runs scan in background thread)
    # -----------------------
    def _start_camera_scan_for(self, mode, entry_widget):
        """
        mode: "add" or "Remove"
        entry_widget: the Entry widget to fill in (thread-safe update via root.after)
        """
        if not HAS_CAMERA_LIBS:
            messagebox.showerror("Camera libs missing", "Camera scanning requires 'opencv-python' and 'pyzbar'.\nInstall with:\n\npip install opencv-python pyzbar")
            return

        def do_scan():
            code = scan_barcode_from_camera()
            if code:
                # update UI from main thread
                def ui_update():
                    entry_widget.delete(0, tk.END)
                    entry_widget.insert(0, code)
                    # trigger lookup automatically depending on mode
                    if mode == "add":
                        try:
                            if hasattr(self, "active_lookup") and self.active_lookup:
                                self.active_lookup()
                        except Exception:
                            pass
                    elif mode == "Remove":
                        try:
                            if hasattr(self, "active_lookup") and self.active_lookup:
                                self.active_lookup()
                        except Exception:
                            pass
                self.root.after(0, ui_update)
            else:
                # cancelled or failed
                self.root.after(0, lambda: messagebox.showinfo("Scan", "No barcode detected or scan cancelled."))
        threading.Thread(target=do_scan, daemon=True).start()

# -----------------------
# Run
# -----------------------
def main():
    init_db()  # ✅ create tables if missing
    root = tk.Tk()
    app = InventoryGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
