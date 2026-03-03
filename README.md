# InventoryFlow — Transfer Planner
## Automated Inventory Transfer Planning Web App

---

## Project Structure

```
inventory_transfer/
├── main.py                  # FastAPI backend — all API logic
├── requirements.txt         # Python dependencies
├── templates/
│   └── index.html           # Jinja2 HTML template (frontend)
└── static/
    └── styles.css           # Corporate green & white CSS
```

---

## Prerequisites

- **Python 3.10 or later** (check: `python --version`)
- **pip** package manager

---

## Installation (Step-by-Step)

### Step 1 — Clone / Download the project folder

Place the `inventory_transfer/` folder anywhere on your machine.

### Step 2 — Open a terminal and navigate into the project

```bash
cd inventory_transfer
```

### Step 3 — (Recommended) Create a virtual environment

```bash
# Create
python -m venv venv

# Activate — macOS / Linux
source venv/bin/activate

# Activate — Windows (Command Prompt)
venv\Scripts\activate.bat

# Activate — Windows (PowerShell)
venv\Scripts\Activate.ps1
```

### Step 4 — Install dependencies

```bash
pip install -r requirements.txt
```

---

## Running the App

### Start the development server

```bash
python main.py
```

Or equivalently:

```bash
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

### Open in browser

```
http://localhost:8000
```

---

## How to Use

1. **Upload** your `.xlsx` or `.xls` Excel file using the upload area (drag-and-drop or click to browse).
2. Click **Process File**.
3. The system reads **Sheet1** only, filters rows where `SKU Type = "non-otc"`, and runs the transfer allocation logic.
4. Review the **Summary Cards** and the **Results Table**.
5. Use the **search** and **status filter** to drill down into specific ASINs or SKUs.
6. Click **↩ Start Over** to upload a new file.

---

## Excel File Requirements

| Column               | Required |
|----------------------|----------|
| `asin`               | ✓        |
| `SKU`                | ✓        |
| `SKU Type`           | ✓ (filter: `non-otc`) |
| `cust_cluster`       | ✓        |
| `total_units_cw`     | ✓        |
| `total_units_l30d`   | ✓        |
| `total fc stock available` | ✓  |
| Columns R → BS       | Warehouse stock values |

- Only **Sheet1** is read.
- Column headers must be in **row 1**.
- Warehouse columns are read by **position** (columns R through BS, i.e. column indices 17–70).

---

## Business Logic Summary

```
Required_Stock = max(total_units_l30d - total_units_cw, 0)

If Required_Stock == 0      → "No Transfer Required"
If Required_Stock > 0       → Sort warehouses (R:BS) by stock descending
                              Allocate greedily until requirement met
                              Fully met  → "Transfer Planned"
                              Not met    → "Insufficient Stock"
```

---

## Stopping the Server

Press `Ctrl + C` in the terminal.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` inside your venv |
| Port 8000 already in use | Change port: `uvicorn main:app --port 8080` |
| "Could not read Sheet1" | Ensure the Excel file has a tab named exactly `Sheet1` |
| Missing column error | Check that your file has the required column headers in row 1 |
| No results shown | Confirm at least one row has `SKU Type = non-otc` (case-insensitive) |
