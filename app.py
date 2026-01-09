import streamlit as st
import pandas as pd
import re
import io
from pathlib import Path

# =================== Settings ==================
BIG_SIZE = 14
LOW_STOCK_THRESHOLD = 5
MEDIUM_STOCK_THRESHOLD = 10
PAGE_TITLE = "Makita Spare Parts Finder"

# Master stock file (same folder as app.py)
MASTER_FILE = "stocks1.xlsx"   # change name if you like

# Simple admin password (CHANGE THIS!)
ADMIN_PASSWORD = "makita123"

# Candidate column names in the spreadsheet
CANDIDATES = {
    "model": ["model", "partno", "partnumber", "itemcode", "material"],
    "material_description": ["materialdescription", "description", "desc", "itemdesc", "materialdesc"],
    "shrm": ["shrm", "showroom"],
    "home": ["home", "godown", "warehouse"],
    "stock": ["stock", "qty", "quantity", "onhand"],
    "used_spares": ["usedspares", "used spares", "used"],
    "price": ["price", "unitprice", "cost", "salesprice"],
}


# =================== Helpers ===================
def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).strip().lower())


def build_column_map(df_columns):
    norm_to_actual = {_norm(c): c for c in df_columns}
    colmap = {}
    for key, options in CANDIDATES.items():
        for opt in options:
            n = _norm(opt)
            if n in norm_to_actual:
                colmap[key] = norm_to_actual[n]
                break

    if "model" not in colmap or "material_description" not in colmap:
        raise ValueError(
            "Your sheet must have columns for Model and Description (with any of these headers):\n\n"
            f"Model: {CANDIDATES['model']}\n"
            f"Description: {CANDIDATES['material_description']}"
        )
    return colmap


def to_int(val):
    try:
        if pd.isna(val):
            return 0
        return int(float(str(val).strip()))
    except Exception:
        return 0


def to_float(val):
    try:
        if pd.isna(val):
            return 0.0
        return float(str(val).strip().replace(",", ""))
    except Exception: 
        return 0.0


def build_app_df(raw_df: pd.DataFrame, colmap: dict) -> pd.DataFrame:
    """Normalize the DataFrame for the app."""
    n = len(raw_df)

    def col_series(key, default=0):
        if key in colmap:
            return raw_df[colmap[key]]
        return pd.Series([default] * n)

    model = col_series("model", "")
    desc = col_series("material_description", "")
    shrm = col_series("shrm", 0)
    home = col_series("home", 0)

    shrm_int = shrm.apply(to_int)
    home_int = home.apply(to_int)

    if "stock" in colmap:
        stock = col_series("stock", 0).apply(to_int)
    else:
        stock = shrm_int + home_int

    if "used_spares" in colmap:
        used = col_series("used_spares", 0).apply(to_int)
    else:
        used = pd.Series([0] * n)

    price = col_series("price", 0).apply(to_float)

    df = pd.DataFrame(
        {
            "model": model.astype(str),
            "material_description": desc.astype(str),
            "shrm": shrm_int,
            "home": home_int,
            "stock": stock,
            "used_spares": used,
            "price": price,
        }
    )

    return df


def add_request_row(row: pd.Series):
    """Add one stock row to the request list in session_state."""
    if "request_rows" not in st.session_state:
        st.session_state["request_rows"] = []

    st.session_state["request_rows"].append(
        {
            "model": row["model"],
            "material_description": row["material_description"],
            "shrm": int(row["shrm"]),
            "home": int(row["home"]),
            "stock": int(row["stock"]),
            "used_spares": int(row["used_spares"]),
            "price": float(row["price"]),
            "qty": 1,
        }
    )


def load_master_to_session() -> bool:
    """Load MASTER_FILE into session_state['df'] and 'colmap'. Return True if ok."""
    path = Path(MASTER_FILE)
    if not path.exists():
        return False

    if path.suffix.lower() in (".xlsx", ".xls"):
        raw_df = pd.read_excel(path)
    elif path.suffix.lower() == ".csv":
        raw_df = pd.read_csv(path)
    else:
        raise ValueError(f"Unsupported file type: {path.suffix}")

    colmap = build_column_map(raw_df.columns)
    df = build_app_df(raw_df, colmap)

    st.session_state["df"] = df
    st.session_state["colmap"] = colmap
    st.session_state["uploaded_name"] = path.name
    return True


# =================== Streamlit App ===================
st.set_page_config(page_title=PAGE_TITLE, layout="wide")
st.title("Makita Spare Parts Finder")
# ---- Initialise session ----
if "df" not in st.session_state:
    st.session_state["df"] = None
if "request_rows" not in st.session_state:
    st.session_state["request_rows"] = []
if "uploaded_name" not in st.session_state:
    st.session_state["uploaded_name"] = None

# ---- Sidebar: admin controls ----
st.sidebar.header("Stock File (internal)")

st.sidebar.write(
    f"Current master file: **{st.session_state.get('uploaded_name') or MASTER_FILE}**"
)

admin_pwd = st.sidebar.text_input("Admin password (optional)", type="password")

is_admin = admin_pwd == ADMIN_PASSWORD

if is_admin:
    st.sidebar.success("Admin access granted.")
    new_file = st.sidebar.file_uploader(
        "Upload new master stock file",
        type=["xlsx", "xls", "csv"],
        key="admin_uploader",
    )
    if new_file is not None:
        if st.sidebar.button("Replace master stock file"):
            # overwrite MASTER_FILE
            with open(MASTER_FILE, "wb") as f:
                f.write(new_file.getbuffer())

            try:
                if load_master_to_session():
                    st.session_state["request_rows"] = []
                    st.sidebar.success(
                        f"Master stock file updated: {st.session_state['uploaded_name']} "
                        f"({len(st.session_state['df'])} rows)"
                    )
                else:
                    st.sidebar.error("Could not load the new master file.")
            except Exception as e:
                st.sidebar.error(f"Error loading master file: {e}")
else:
    if admin_pwd:
        st.sidebar.error("Wrong admin password.")

st.sidebar.caption("Normal users can ignore the password field.")

# ---- Load master file if needed ----
if st.session_state["df"] is None:
    loaded_ok = load_master_to_session()
else:
    loaded_ok = True

if not loaded_ok or st.session_state["df"] is None:
    st.info(
        "No master stock file found.\n\n"
        f"Admin must upload **{MASTER_FILE}** in the sidebar (correct password needed)."
    )
    st.stop()

df = st.session_state["df"]

# =========================================================
# Tabs: Spare List  |  Request List
# =========================================================
tab1, tab2 = st.tabs(["Spare List", "Request List"])


# =========================================================
# TAB 1: Spare List
# =========================================================
with tab1:
    st.subheader("Spare List (from master file)")

    col_search1, col_search2 = st.columns([3, 1])

    with col_search1:
        spare_search = st.text_input(
            "Search Model or Description (this filters the table below):",
            "",
            key="spare_search",
        )

    with col_search2:
        st.write("")
        add_button = st.button("Add from Search")

    st.caption("Stock level info:")
    st.markdown(
        f"""
- Stock = 0 -> **critical**  
- Stock < {LOW_STOCK_THRESHOLD} -> **low**  
- Stock < {MEDIUM_STOCK_THRESHOLD} -> **medium**  
- Stock >= {MEDIUM_STOCK_THRESHOLD} -> **ok**
        """
    )

    if spare_search.strip():
        q = spare_search.strip().lower()
        mask = (
            df["model"].str.contains(re.escape(q), case=False, na=False)
            | df["material_description"].str.contains(re.escape(q), case=False, na=False)
        )
        spare_filtered = df[mask].copy()
    else:
        spare_filtered = df.copy()

    spare_view = spare_filtered[
        ["model", "material_description", "shrm", "home", "stock", "used_spares", "price"]
    ]
    st.dataframe(spare_view, use_container_width=True)

    if add_button and spare_search.strip():
        q = spare_search.strip()
        hits = df[
            df["model"].str.match(fr"^{re.escape(q)}", case=False, na=False)
            | df["material_description"].str.contains(re.escape(q), case=False, na=False)
        ]

        if hits.empty:
            st.error(f"Part not found: {q}")
        elif len(hits) == 1:
            add_request_row(hits.iloc[0])
            st.success(f"Added: {hits.iloc[0]['model']}")
        else:
            st.warning(f"Found {len(hits)} matches. Please choose one:")

            matches_display = hits[
                ["model", "material_description", "shrm", "home", "stock", "used_spares", "price"]
            ].reset_index(drop=True)
            st.dataframe(matches_display, use_container_width=True)

            idx = st.number_input(
                "Select row number to add (starting from 0):",
                min_value=0,
                max_value=len(matches_display) - 1,
                step=1,
                value=0,
                key="match_index",
            )
            if st.button("Confirm Add Selected Match"):
                add_request_row(hits.iloc[int(idx)])
                st.success(f"Added: {hits.iloc[int(idx)]['model']}")


# =========================================================
# TAB 2: Request List
# =========================================================
with tab2:
    st.subheader("Request List")

    req_rows = st.session_state.get("request_rows", [])
    if not req_rows:
        st.info("No items in the request list yet. Add from the Spare List tab.")
    else:
        req_df = pd.DataFrame(req_rows)

        req_df["qty"] = req_df["qty"].fillna(1).astype(int)
        req_df.loc[req_df["qty"] < 0, "qty"] = 0

        req_df["line_total"] = req_df["price"] * req_df["qty"]

        st.write("You can edit the Qty column. Line Total and totals update automatically.")
        edited_df = st.data_editor(
            req_df,
            hide_index=True,
            num_rows="dynamic",
            column_config={
                "model": st.column_config.TextColumn("Model", disabled=True),
                "material_description": st.column_config.TextColumn("Description", disabled=True),
                "shrm": st.column_config.NumberColumn("Showroom", disabled=True),
                "home": st.column_config.NumberColumn("Home", disabled=True),
                "stock": st.column_config.NumberColumn("Stock", disabled=True),
                "used_spares": st.column_config.NumberColumn("Used Spares", disabled=True),
                "price": st.column_config.NumberColumn("Price", format="%.2f", disabled=True),
                "qty": st.column_config.NumberColumn("Qty", min_value=0, step=1),
                "line_total": st.column_config.NumberColumn("Line Total", format="%.2f", disabled=True),
            },
            key="request_editor",
            use_container_width=True,
        )

        edited_df["qty"] = edited_df["qty"].fillna(0).astype(int)
        edited_df["line_total"] = edited_df["price"] * edited_df["qty"]

        st.session_state["request_rows"] = edited_df.drop(columns=["line_total"]).to_dict("records")

        total_items = len(edited_df)
        total_qty = int(edited_df["qty"].sum())
        total_amount = float(edited_df["line_total"].sum())

        col_t1, col_t2, col_t3 = st.columns(3)
        col_t1.metric("Items", total_items)
        col_t2.metric("Total Qty", total_qty)
        col_t3.metric("Total Amount", f"{total_amount:,.2f}")

        st.markdown("---")

        buffer = io.BytesIO()
        out_df = edited_df.copy()
        with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
            out_df.to_excel(writer, index=False, sheet_name="Requests")
        buffer.seek(0)

        st.download_button(
            label="Download Request List (Excel)",
            data=buffer,
            file_name="requests.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        if st.button("Clear Request List"):
            st.session_state["request_rows"] = []
            st.experimental_rerun()
