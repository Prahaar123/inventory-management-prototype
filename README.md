# Inventory Management Prototype

A lightweight inventory management prototype built in Python.  
This project demonstrates a simple inventory system with CLI and GUI components, barcode generation, and a SQLite database backend.

![Python](<img width="659" height="261" alt="Screenshot 2025-08-15 223654" src="https://github.com/user-attachments/assets/ac5ab486-65ce-4bb4-82b2-1d11f639587a" />)
![License](https://img.shields.io/badge/license-MIT-green)

---

## 🚀 Features
- Add, update, and remove inventory items
- View items in both **Command Line Interface (CLI)** and **Graphical User Interface (GUI)**
- Generate barcodes for each item
- SQLite database for easy storage
- Modular code for future expansion

---

## 📂 Project Structure
InventoryDemo/
├── barcode_generator.py # Generates barcodes
├── db_setup.py # Creates and sets up the SQLite database
├── inspect_db.py # Tools for inspecting the DB
├── inventory_cli.py # Command-line interface
├── inventory_gui.py # GUI for managing inventory
├── migrate_phase3.py # Migration script for DB updates
├── barcodes/ # Generated barcodes
├── requirements.txt # Python dependencies
└── README.md # This file

---

## ⚙️ Installation
1. **Clone the repository**

git clone https://github.com/Prahaar123/inventory-management-prototype.git
cd inventory-management-prototype

2. **Create a virtual environment**
python -m venv venv

3. **Activate the virtual environment**
- **Windows**
venv\Scripts\activate
- **Mac/Linux**
source venv/bin/activate

4. **Install dependencies**
pip install -r requirements.txt

---

## ▶️ Usage

### **Run CLI version**
python inventory_cli.py

### **Run GUI version**
python inventory_gui.py

---

## 📸 Screenshots
<img width="659" height="261" alt="Screenshot 2025-08-15 223654" src="https://github.com/user-attachments/assets/45f785e0-ebdd-4e70-a266-f023c56d8331" />
<img width="553" height="410" alt="Screenshot 2025-08-15 223750" src="https://github.com/user-attachments/assets/d3eba5e1-69b6-4b81-aa49-a8bf70c2edfb" />
<img width="518" height="310" alt="Screenshot 2025-08-15 224041" src="https://github.com/user-attachments/assets/b623550f-2051-4f64-93c5-2cc62dd8466c" />
<img width="929" height="457" alt="Screenshot 2025-08-15 223926" src="https://github.com/user-attachments/assets/841e657d-aa45-4507-8083-8b601bb9264c" />

---
## 💻 Download Executable (Windows)
You can directly download and run the Windows version of this project without installing Python:

[📥 Download InventoryDemo.exe](https://github.com/Prahaar123/releases/download/v1.0-prototype/InventoryDemo.exe)

---

## 📜 License
This project is licensed under the MIT License.

---




