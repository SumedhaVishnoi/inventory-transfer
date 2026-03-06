import io
import re
import pandas as pd
import uvicorn
from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

app = FastAPI(title="Inventory Transfer Planner")
try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
except Exception:
    pass
templates = Jinja2Templates(directory="templates")

_store: dict = {}

CLUSTER_TO_STATE = {
    'BOM_CLUSTER': 'MH', 'NAG_CLUSTER': 'MH',
    'DEL_CLUSTER': 'DL',
    'HYD_CLUSTER': 'TG',
    'BLR_CLUSTER': 'KA',
    'COI_CLUSTER': 'TN', 'CHN_CLUSTER': 'TN',
    'HRA_CLUSTER': 'HR',
    'PUN_CLUSTER': 'PB',
    'KOL_CLUSTER': 'WB',
    'LKO_CLUSTER': 'UP',
    'GAA_CLUSTER': 'GJ', 'SAT_CLUSTER': 'GJ', 'AMD_CLUSTER': 'GJ',
    'PAT_CLUSTER': 'BR',
    'IND_CLUSTER': 'MP',
    'JAI_CLUSTER': 'RJ',
}


def build_wh_maps(xl):
    wh_sheet = None
    for sheet in xl.sheet_names:
        try:
            peek = pd.read_excel(xl, sheet_name=sheet, header=None, nrows=2)
            row0 = [str(v).strip().lower() for v in peek.iloc[0].values]
            if any('cluster' in v for v in row0) and any('warehouse' in v for v in row0):
                wh_sheet = sheet
                break
        except Exception:
            continue
    if wh_sheet is None:
        for sheet in xl.sheet_names:
            if 'warehouse' in sheet.lower():
                wh_sheet = sheet
                break
    if wh_sheet is None:
        return {}, {}

    raw = pd.read_excel(xl, sheet_name=wh_sheet, header=None)
    state_to_wh = {}
    for _, row in raw.iterrows():
        vals = [str(v).strip() for v in row.values if str(v).strip() not in ('', 'nan')]
        if len(vals) < 2 or vals[0].lower() == 'cluster':
            continue
        state = vals[0].strip().upper()
        wh_str = re.sub(r'DEX\s*,\s*8', 'DEX8', ' '.join(vals[1:]))
        whs = [w.strip().upper() for w in re.split(r'[,\s]+', wh_str)
               if w.strip() and w.strip().upper() != 'NAN']
        seen = set()
        state_to_wh[state] = [w for w in whs if not (w in seen or seen.add(w))]

    wh_to_state = {wh: s for s, whs in state_to_wh.items() for wh in whs}
    return wh_to_state, state_to_wh


def load_inventory(xl):
    candidates = []
    for sheet in xl.sheet_names:
        try:
            peek = pd.read_excel(xl, sheet_name=sheet, header=None, nrows=5)
            for _, row in peek.iterrows():
                if any(str(v).strip().lower() == 'asin' for v in row.values):
                    candidates.append((sheet, xl.parse(sheet).shape[0]))
                    break
        except Exception:
            continue

    if not candidates:
        raise ValueError(f"No sheet with 'asin' column found. Sheets: {xl.sheet_names}")

    candidates.sort(key=lambda x: -x[1])
    main_sheet = candidates[0][0]

    raw = pd.read_excel(xl, sheet_name=main_sheet, header=None)
    header_idx = None
    for i, row in raw.iterrows():
        if any(str(v).strip().lower() == 'asin' for v in row.values):
            header_idx = i
            break
    if header_idx is None:
        raise ValueError("Could not locate header row.")

    df = pd.read_excel(xl, sheet_name=main_sheet, header=header_idx)
    df.columns = [str(c).strip().lower() for c in df.columns]

    missing = {'sku type', 'total_units_cw', 'total_units_l30d'} - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {', '.join(missing)}")

    df['sku type'] = df['sku type'].astype(str).str.strip()
    df = df[df['sku type'].str.upper() == 'NON-OTC'].copy()
    if df.empty:
        raise ValueError("No NON-OTC rows found.")

    for col in ['total_units_cw', 'total_units_l30d']:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    fc_col = next((c for c in df.columns if 'fc stock' in c or 'fc_stock' in c), None)
    if fc_col:
        df[fc_col] = pd.to_numeric(df[fc_col], errors='coerce').fillna(0)
    else:
        df['total fc stock available'] = 0
        fc_col = 'total fc stock available'

    all_cols = list(df.columns)
    wh_cols = [c for c in all_cols[all_cols.index(fc_col) + 1:] if not c.startswith('_')]
    for col in wh_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    df['_required'] = (df['total_units_l30d'] - df['total_units_cw']).clip(lower=0)
    return df, wh_cols, fc_col


def compute_plan(asin_df, wh_cols, fc_col, wh_to_state, state_to_wh):
    wh_stock = {
        col.upper(): int(asin_df[col].iloc[0])
        for col in wh_cols if asin_df[col].iloc[0] > 0
    }
    cluster_req, state_req = {}, {}
    for _, row in asin_df.iterrows():
        c = row['cust_cluster']
        r = int(row['_required'])
        cluster_req[c] = r
        s = CLUSTER_TO_STATE.get(c)
        if s:
            state_req[s] = state_req.get(s, 0) + r

    results = []
    for _, row in asin_df.iterrows():
        cluster    = row['cust_cluster']
        required   = cluster_req[cluster]
        dest_state = CLUSTER_TO_STATE.get(cluster)
        fc_stock   = int(float(row.get(fc_col, 0)))

        dest_wh = '—'
        if dest_state:
            options = state_to_wh.get(dest_state, [])
            seen = set()
            options = [w for w in options if not (w in seen or seen.add(w))]
            cands = [(wh, int(asin_df[wh.lower()].iloc[0]))
                     for wh in options if wh.lower() in wh_cols]
            cands.sort(key=lambda x: x[1])
            dest_wh = cands[0][0] if cands else (options[0] if options else '—')

        remaining = required
        allocs = []
        for wh in sorted(wh_stock, key=lambda w: -wh_stock[w]):
            if remaining <= 0:
                break
            stock = wh_stock[wh]
            if stock <= 0:
                continue
            wh_state = wh_to_state.get(wh)
            if dest_state and wh_state == dest_state:
                continue
            if state_req.get(wh_state, 0) > 0:
                continue
            take = min(stock, remaining)
            if take > 0:
                allocs.append({'source': wh, 'destination': dest_wh, 'units': take})
                remaining -= take
                wh_stock[wh] -= take

        allocated = required - remaining
        if required == 0:
            status = 'No Transfer Required'
        elif allocated >= required:
            status = 'Transfer Planned'
        else:
            status = 'Insufficient Stock'

        results.append({
            'cluster':        cluster,
            'dest_state':     dest_state or '—',
            'dest_warehouse': dest_wh,
            'required_stock': required,
            'fc_stock':       fc_stock,
            'allocated':      allocated,
            'shortfall':      max(required - allocated, 0),
            'transfer_plan':  ' | '.join(f"{a['source']}→{a['destination']}:{a['units']}" for a in allocs) if allocs else '—',
            'allocations':    allocs,
            'status':         status,
        })
    return results


def build_lanes(xl):
    """Read active lanes from uploaded file if available."""
    for sheet in xl.sheet_names:
        try:
            peek = pd.read_excel(xl, sheet_name=sheet, header=0, nrows=2)
            cols = [str(c).strip().lower() for c in peek.columns]
            if len(cols) >= 2 and 'lanes' in cols[0]:
                df = pd.read_excel(xl, sheet_name=sheet, header=0)
                c0, c1 = df.columns[0], df.columns[1]
                return set(zip(df[c0].astype(str).str.strip().str.upper(),
                               df[c1].astype(str).str.strip().str.upper()))
        except Exception:
            continue
    return set()


def generate_excel(df, wh_cols, fc_col, wh_to_state, state_to_wh, active_lanes=None):
    """Process all ASINs and return Excel in manager's exact format."""
    if active_lanes is None:
        active_lanes = set()

    all_asins = sorted(df['asin'].dropna().unique().tolist())
    rows = []

    for asin in all_asins:
        asin_df  = df[df['asin'].astype(str).str.strip().str.upper() == asin.upper()].copy()
        fnsku    = str(asin_df['fnsku'].iloc[0]) if 'fnsku' in asin_df.columns else ''
        results  = compute_plan(asin_df, wh_cols, fc_col, wh_to_state, state_to_wh)

        for r in results:
            cluster_short = r['cluster'].replace('_CLUSTER', '')
            for alloc in r['allocations']:
                src   = alloc['source']
                dst   = alloc['destination']
                units = alloc['units']
                lane  = 'Active lane' if (src.upper(), dst.upper()) in active_lanes else 'No active lane'
                rows.append({
                    'ASIN ID':                                   asin,
                    'FNSKU':                                     fnsku,
                    'Demand Cluster':                            cluster_short,
                    'Current FC':                                src,
                    'Unit in Current FC':                        units,
                    'Destination FC':                            dst,
                    'Units to be Transfered in Destination FC':  units,
                    'Lane Dest.':                                lane,
                })

    out_df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=[
        'ASIN ID', 'FNSKU', 'Demand Cluster', 'Current FC',
        'Unit in Current FC', 'Destination FC',
        'Units to be Transfered in Destination FC', 'Lane Dest.'
    ])

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        out_df.to_excel(writer, index=False, sheet_name='Transfer Plan')
        ws = writer.sheets['Transfer Plan']
        for col in ws.columns:
            max_len = max((len(str(cell.value)) for cell in col if cell.value), default=10)
            ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 60)
    buf.seek(0)
    return buf


# ── Routes ────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    if not file.filename.lower().endswith((".xlsx", ".xls")):
        return JSONResponse(status_code=400,
            content={"error": "Please upload an Excel file (.xlsx or .xls)."})
    contents = await file.read()
    try:
        xl = pd.ExcelFile(io.BytesIO(contents))
        wh_to_state, state_to_wh = build_wh_maps(xl)
        df, wh_cols, fc_col = load_inventory(xl)
        active_lanes = build_lanes(xl)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": f"Error reading file: {str(e)}"})

    _store.clear()
    _store.update({
        "df": df, "wh_cols": wh_cols, "fc_col": fc_col,
        "wh_to_state": wh_to_state, "state_to_wh": state_to_wh,
        "active_lanes": active_lanes,
    })
    asins = sorted(df["asin"].dropna().unique().tolist())
    return JSONResponse(content={
        "success": True, "total_rows": len(df),
        "unique_asins": len(asins), "asins": asins,
    })


@app.get("/search")
async def search_asin(asin: str):
    if "df" not in _store:
        return JSONResponse(status_code=400, content={"error": "Upload a file first."})

    asin    = asin.strip()
    df      = _store["df"]
    asin_df = df[df["asin"].astype(str).str.strip().str.upper() == asin.upper()].copy()
    if asin_df.empty:
        return JSONResponse(status_code=404, content={"error": f"ASIN '{asin}' not found."})

    wh_stock = {
        col.upper(): int(asin_df[col].iloc[0])
        for col in _store["wh_cols"] if asin_df[col].iloc[0] > 0
    }
    results  = compute_plan(asin_df, _store["wh_cols"], _store["fc_col"],
                            _store["wh_to_state"], _store["state_to_wh"])
    sku_name = str(asin_df["sku"].iloc[0]) if "sku" in asin_df.columns else ""

    return JSONResponse(content={
        "results": results,
        "summary": {
            "asin": asin, "sku": sku_name,
            "total_clusters": len(asin_df),
            "total_supply":   sum(wh_stock.values()),
            "total_demand":   int(asin_df["_required"].sum()),
            "wh_stock":       wh_stock,
        },
    })


@app.get("/download")
async def download_excel():
    if "df" not in _store:
        return JSONResponse(status_code=400, content={"error": "Upload a file first."})
    try:
        buf = generate_excel(
            _store["df"], _store["wh_cols"], _store["fc_col"],
            _store["wh_to_state"], _store["state_to_wh"],
            _store.get("active_lanes", set())
        )
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=transfer_plan.xlsx"}
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
