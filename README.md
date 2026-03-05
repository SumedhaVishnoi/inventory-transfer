# InventoryFlow — Inventory Transfer Planner

> **Live App:** [https://invento-wpkh.onrender.com](https://invento-wpkh.onrender.com)  
> Hosted for free on Render · No login required · Works from any browser

---

## What This Tool Does

InventoryFlow helps plan **inventory transfers across clusters** for NON-OTC SKUs.

Given an Excel file with ASIN-level inventory data, it:
- Lets you search any **ASIN**
- Shows how much stock each **cluster needs**
- Identifies which **warehouses have surplus** stock (above their own cluster's need)
- Plans transfers: **Source Warehouse → Destination Warehouse : Units**
- Enforces the safety rule: **never take from a warehouse whose home cluster has any requirement**

---

## How to Use (Online)

1. Open the live link: **https://invento-wpkh.onrender.com**
2. Upload your `.xlsx` Excel file
3. Type or select an **ASIN** from the autocomplete
4. Click **Search**
5. View the transfer plan table

> ⚠️ The app may take **~30 seconds** to load on first visit (free tier sleeps after inactivity). Just wait and refresh once.

---

## Excel File Requirements

Your Excel file must have **two sheets**:

### Sheet 1 — Inventory Data (any sheet name is fine)
Must contain these columns (header row auto-detected):

| Column | Description |
|--------|-------------|
| `asin` | Amazon ASIN |
| `SKU` | Product SKU name |
| `SKU Type` | Must be `NON-OTC` to be processed |
| `cust_cluster` | Cluster name (e.g. `DEL_CLUSTER`) |
| `total_units_cw` | Current warehouse stock |
| `total_units_l30d` | Last 30 days demand |
| `Total FC Stock Available` | FC stock on hand |
| Warehouse columns | One column per warehouse (e.g. `BLR5`, `DED4`) |

### Sheet 2 — Warehouse Cluster Mapping (any sheet name with "warehouse" in it)
Maps state codes to warehouse names:

| Column | Example |
|--------|---------|
| Cluster | `KA` |
| warehouse name | `BLR4, BLR5, BLR7, BLR8, FBLF...` |

---

## Business Logic

```
Required = max(total_units_l30d − total_units_cw, 0)
```

For each cluster needing stock:

1. **Skip** warehouses in the same state as the requesting cluster
2. **Skip** warehouses whose home state has ANY requirement for this ASIN
3. **Take** from remaining free warehouses (highest stock first)
4. **Deduct** from shared pool — no double counting across clusters
5. **Destination** = warehouse in the cluster's home state with lowest current stock

| Status | Meaning |
|--------|---------|
| ✅ Transfer Planned | Full requirement can be met from surplus |
| ⚠️ Insufficient Stock | Partial transfer possible — not enough surplus |
| — No Transfer Required | Cluster already has enough stock |

---

## Project Structure

```
inventory-transfer/
├── main.py                  # FastAPI backend — all logic
├── requirements.txt         # Python dependencies
├── render.yaml              # Render deployment config
├── .python-version          # Pins Python 3.11.8
├── templates/
│   └── index.html           # Frontend (HTML + CSS + JS, all inline)
└── README.md
```

---



---

## Running Locally

```powershell
# 1. Clone the repo
git clone https://github.com/SumedhaVishnoi/inventory-transfer
cd inventory-transfer

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start the server
python main.py

# 4. Open browser
# http://127.0.0.1:8000
```

---

## Deploying Updates

Any push to `main` branch auto-deploys on Render:

```powershell
git add .
git commit -m "your update message"
git push
```

Render picks it up automatically in ~2 minutes.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11 · FastAPI · Uvicorn |
| Data | Pandas · OpenPyXL |
| Frontend | HTML · CSS · Vanilla JS (no frameworks) |
| Hosting | Render (free tier) |

---

## Notes

- Uploaded files are **not stored** — users re-upload each session
- Only **NON-OTC** rows are processed
- Sheet names don't need to match exactly — auto-detected by content
