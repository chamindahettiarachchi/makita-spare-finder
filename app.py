import streamlit as st
import pandas as pd
import re
import io
import html
from pathlib import Path
from streamlit_searchbox import st_searchbox

# =================== Settings ===================
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
    shrm = col_series("shrm", "")
    home = col_series("home", "")
    shrm = shrm.fillna("N-A")
    home = home.fillna("N-A")

    if "stock" in colmap:
        stock = col_series("stock", 0).apply(to_int)
    else:
        stock = pd.Series([0] * n)

    if "used_spares" in colmap:
        used = col_series("used_spares", 0).apply(to_int)
    else:
        used = pd.Series([0] * n)

    price = col_series("price", 0).apply(to_float)

    df = pd.DataFrame(
        {
            "model": model.astype(str),
            "material_description": desc.astype(str),
            "shrm": shrm.astype(str).replace("nan", "N-A"),
            "home": home.astype(str).replace("nan", "N-A"),
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
            "shrm": str(row["shrm"]),
            "home": str(row["home"]),
            "stock": int(row["stock"]),
            "used_spares": int(row["used_spares"]),
            "price": float(row["price"]),
            "qty": 1,
        }
    )


def _fmt_price(val: float) -> str:
    try:
        return f"{float(val):,.2f}"
    except Exception:
        return "0.00"


def render_spare_cards(spare_df: pd.DataFrame) -> None:
    for _, row in spare_df.iterrows():
        model = html.escape(str(row["model"]))
        desc = html.escape(str(row["material_description"]))
        shrm = html.escape(str(row["shrm"]))
        home = html.escape(str(row["home"]))
        st.markdown(
            f"""
<div class="spare-card">
  <div class="spare-main"><strong>{model}</strong> - {desc}</div>
  <div class="spare-meta">
    <span>Showroom: {shrm}</span>
    <span>Home: {home}</span>
    <span>Stock: {int(row["stock"])}</span>
    <span>Used: {int(row["used_spares"])}</span>
    <span>Price: {_fmt_price(row["price"])}</span>
  </div>
</div>
            """,
            unsafe_allow_html=True,
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
st.markdown(
    "<h1 style='color:#006400; margin-bottom:0;'>Makita Spare Parts Finder</h1>",
    unsafe_allow_html=True,
)
st.markdown(
    """
<style>
  @media (max-width: 768px) {
    .block-container { padding-left: 1rem; padding-right: 1rem; }
    .block-container h1 { font-size: 1.6rem; }
    div[data-testid="column"] { width: 100% !important; flex: 1 1 100% !important; }
    button, .stButton > button { width: 100%; }
    .stDataFrame, .stTable { font-size: 0.85rem; }
  }
  .spare-card {
    border: 1px solid #d0d0d0;
    border-radius: 8px;
    padding: 10px 12px;
    margin: 8px 0;
    background: #ffffff;
  }
  .spare-main { font-size: 0.95rem; margin-bottom: 6px; }
  .spare-meta span {
    display: inline-block;
    margin-right: 12px;
    font-size: 0.85rem;
    color: #333333;
  }
  @media (max-width: 768px) {
    .spare-meta span { display: block; margin-right: 0; }
  }
  </style>
    """,
    unsafe_allow_html=True,
)
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

mobile_view = st.sidebar.toggle("Mobile-friendly lists", value=True)

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

    st.markdown("Search Model or Description (this filters the table below):")
    all_suggestions = (
        df["model"].astype(str).fillna("")
        + " - "
        + df["material_description"].astype(str).fillna("")
    ).tolist()
    col_search1, col_search2 = st.columns([3, 1])

    with col_search1:
        def search_spares(searchterm: str):
            if not searchterm:
                return []
            term = searchterm.strip().lower()
            return [s for s in all_suggestions if term in s.lower()][:20]

        search_value = st_searchbox(
            search_spares,
            placeholder="Start typing to filter by model or description",
            default_use_searchterm=True,
            key="spare_searchbox",
        )
        search_value = str(search_value or "").strip()

    with col_search2:
        add_button = st.button("Add to List", use_container_width=True)

    available_row = None
    if search_value:
        q = search_value
        if " - " in q:
            q_model, q_desc = q.split(" - ", 1)
            mask = (
                df["model"].str.contains(re.escape(q_model), case=False, na=False)
                & df["material_description"].str.contains(
                    re.escape(q_desc), case=False, na=False
                )
            )
        else:
            mask = (
                df["model"].str.contains(re.escape(q), case=False, na=False)
                | df["material_description"].str.contains(re.escape(q), case=False, na=False)
            )
        spare_filtered = df[mask].copy()
        if len(spare_filtered) == 1:
            available_row = spare_filtered.iloc[0]

        spare_view = spare_filtered[
            ["model", "material_description", "shrm", "home", "stock", "used_spares", "price"]
        ]
        st.caption(f"Matches: {len(spare_view)}")
        if mobile_view:
            render_spare_cards(spare_view)
        else:
            st.dataframe(spare_view, use_container_width=True)
    else:
        st.info("Start typing to see matching spare parts.")

    if add_button and search_value:
        q = search_value
        if " - " in q:
            q_model, q_desc = q.split(" - ", 1)
            hits = df[
                df["model"].str.contains(re.escape(q_model), case=False, na=False)
                & df["material_description"].str.contains(
                    re.escape(q_desc), case=False, na=False
                )
            ]
            q_display = f"{q_model} - {q_desc}"
        else:
            hits = df[
                df["model"].str.match(fr"^{re.escape(q)}", case=False, na=False)
                | df["material_description"].str.contains(re.escape(q), case=False, na=False)
            ]
            q_display = q

        if hits.empty:
            st.error(f"Part not found: {q_display}")
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

    if available_row is not None:
        available_qty = int(available_row["stock"]) - int(available_row["used_spares"])
        st.markdown(
            f"<div style='margin-top:12px; color:#0066cc; font-weight:600;'>"
            f"Available Quantity: {available_qty}"
            f"</div>",
            unsafe_allow_html=True,
        )


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

        if mobile_view:
            updated_rows = []
            for idx, row in req_df.iterrows():
                model = html.escape(str(row["model"]))
                desc = html.escape(str(row["material_description"]))
                shrm = html.escape(str(row["shrm"]))
                home = html.escape(str(row["home"]))
                st.markdown(
                    f"""
<div class="spare-card">
  <div class="spare-main"><strong>{model}</strong> - {desc}</div>
  <div class="spare-meta">
    <span>Showroom: {shrm}</span>
    <span>Home: {home}</span>
    <span>Stock: {int(row["stock"])}</span>
    <span>Used: {int(row["used_spares"])}</span>
    <span>Price: {_fmt_price(row["price"])}</span>
  </div>
</div>
                    """,
                    unsafe_allow_html=True,
                )

                qty = st.number_input(
                    "Qty",
                    min_value=0,
                    step=1,
                    value=int(row["qty"]),
                    key=f"qty_{idx}",
                )
                line_total = float(row["price"]) * int(qty)
                st.markdown(f"Line Total: **{_fmt_price(line_total)}**")

                updated = row.drop(labels=["line_total"]).to_dict()
                updated["qty"] = int(qty)
                updated_rows.append(updated)

            st.session_state["request_rows"] = updated_rows
            total_items = len(updated_rows)
            total_qty = sum(r["qty"] for r in updated_rows)
            total_amount = sum(float(r["price"]) * int(r["qty"]) for r in updated_rows)
        else:
            st.write("You can edit the Qty column. Line Total and totals update automatically.")
            edited_df = st.data_editor(
                req_df,
                hide_index=True,
                num_rows="dynamic",
                column_config={
                    "model": st.column_config.TextColumn("Model", disabled=True),
                    "material_description": st.column_config.TextColumn("Description", disabled=True),
                "shrm": st.column_config.TextColumn("Showroom", disabled=True),
                "home": st.column_config.TextColumn("Home", disabled=True),
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

            new_rows = edited_df.drop(columns=["line_total"]).to_dict("records")
            if new_rows != req_rows:
                st.session_state["request_rows"] = new_rows
                if hasattr(st, "rerun"):
                    st.rerun()
                else:
                    st.experimental_rerun()

            total_items = len(edited_df)
            total_qty = int(edited_df["qty"].sum())
            total_amount = float(edited_df["line_total"].sum())

        col_t1, col_t2, col_t3 = st.columns(3)
        col_t1.metric("Items", total_items)
        col_t2.metric("Total Qty", total_qty)
        col_t3.metric("Total Amount", f"{total_amount:,.2f}")

        st.markdown("---")

        buffer = io.BytesIO()
        if mobile_view:
            out_df = pd.DataFrame(updated_rows)
            out_df["line_total"] = out_df["price"] * out_df["qty"]
        else:
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
            if hasattr(st, "rerun"):
                st.rerun()
            else:
                st.experimental_rerun()
