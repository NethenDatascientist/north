import io
import re
import difflib
import requests
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px

# ==============================================================================
# 1. PAGE CONFIGURATION & CUSTOM STYLING
# ==============================================================================
st.set_page_config(
    page_title="ಕಾಮಗಾರಿಗಳ ಪ್ರಗತಿ ವರದಿ | Works Progress Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .main-header {
        background: linear-gradient(90deg, #0f172a 0%, #1e3a8a 100%);
        color: white;
        padding: 1.2rem 1.8rem;
        border-radius: 12px;
        margin-bottom: 1.2rem;
        box-shadow: 0 4px 12px rgba(0,0,0,0.12);
    }
    .main-header h1 {
        margin: 0;
        font-size: 1.75rem;
        font-weight: 700;
        color: #ffffff;
    }
    .main-header p {
        margin: 0.3rem 0 0 0;
        font-size: 0.95rem;
        color: #cbd5e1;
    }
    .kpi-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-left: 5px solid #2563eb;
        border-radius: 10px;
        padding: 1rem 1.2rem;
        box-shadow: 0 2px 6px rgba(0,0,0,0.04);
        margin-bottom: 0.8rem;
        height: 100%;
    }
    .kpi-card.count-card {
        border-left-color: #059669;
        background: #f0fdf4;
    }
    .kpi-title {
        font-size: 0.88rem;
        font-weight: 600;
        color: #475569;
        margin-bottom: 0.4rem;
        line-height: 1.35;
    }
    .kpi-value {
        font-size: 1.45rem;
        font-weight: 800;
        color: #0f172a;
    }
    .kpi-sub {
        font-size: 0.78rem;
        color: #64748b;
        margin-top: 0.2rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ==============================================================================
# 2. CONSTANTS & TARGET CONFIGURATION
# ==============================================================================
# Replace the placeholder below with your full Google Spreadsheet sharing URL
# or set SPREADSHEET_URL in Streamlit Cloud Secrets.
DEFAULT_SHEET_URL = st.secrets.get(
    "SPREADSHEET_URL",
    "PASTE_YOUR_GOOGLE_SPREADSHEET_URL_HERE",
)

TARGET_SHEETS_RAW = [
    "4702 NT_N",
    "4702_MOT_N",
    "4702 _APB_N",
    "4702_LIS_N",
    "PV_N",
    "KHARLAND_N",
    "4711 FC_N",
    "PMKSY N",
    "KMERC_N",
    "N SDMF ",
    "N Atalbhuja",
    "NABARD APB_N",
    "NABARDMOT_N",
    "NABARD LIS_N",
    "SCPBW_N",
    "SCP _CD_N",
    "SCP_ LIS_N",
    "TSP _BW_N",
    "TSP _CD_N",
    "TSP _LIS_N",
]

VALID_DIVISIONS = [
    "ಕಲಬುರಗಿ",
    "ಕೊಪ್ಪಳ",
    "ಧಾರವಾಡ",
    "ಬಳ್ಳಾರಿ",
    "ಬೀದರ",
    "ಬೆಳಗಾವಿ",
    "ವಿಜಯಪುರ",
    "ಹಳಿಯಾಳ",
]

# Common spelling aliases mapped directly to the 8 canonical division names
DIVISION_ALIASES = {
    "ಕಲಬುರ್ಗಿ": "ಕಲಬುರಗಿ",
    "ಕಲ್ಬುರ್ಗಿ": "ಕಲಬುರಗಿ",
    "ಗುಲ್ಬರ್ಗಾ": "ಕಲಬುರಗಿ",
    "ಬೀದರ್": "ಬೀದರ",
    "ಬಿದರ": "ಬೀದರ",
    "ಬಿದರ್": "ಬೀದರ",
    "ಬೆಳಗಾವ": "ಬೆಳಗಾವಿ",
    "ವಿಜಯಪೂರ": "ವಿಜಯಪುರ",
    "ಬಿಜಾಪುರ": "ವಿಜಯಪುರ",
    "ಧಾರವಾಡಾ": "ಧಾರವಾಡ",
    "ಹಳಿಯಾಳ್": "ಹಳಿಯಾಳ",
    "ಕೊಪ್ಪಳ್": "ಕೊಪ್ಪಳ",
    "ಬಳ್ಳಾರೀ": "ಬಳ್ಳಾರಿ",
}

# Range definitions (values in Lakhs: 1 Cr = 100 Lakhs)
ESTIMATE_RANGES = {
    "More than 100CR (> 10000 Lakhs)": lambda s: s > 10000,
    "25CR - 100CR (> 2500 to <= 10000 Lakhs)": lambda s: (s > 2500) & (s <= 10000),
    "10CR - 25CR (> 1000 to <= 2500 Lakhs)": lambda s: (s > 1000) & (s <= 2500),
    "5CR - 10CR (> 500 to <= 1000 Lakhs)": lambda s: (s > 500) & (s <= 1000),
    "2CR - 5CR (> 200 to <= 500 Lakhs)": lambda s: (s > 200) & (s <= 500),
    "1CR - 5CR (> 100 to <= 500 Lakhs)": lambda s: (s > 100) & (s <= 500),
    "0 - 2CR (>= 0 to <= 200 Lakhs)": lambda s: (s >= 0) & (s <= 200),
    "Less than 1CR (< 100 Lakhs)": lambda s: s < 100,
}

# Canonical Column Names used across the app
COL_SF = "S/F"
COL_PROGRESS = "PROGRESS STATUS (CP/CF)"
COL_HEAD = "ಲೆಕ್ಕ ಶೀರ್ಷಿಕೆ"
COL_DIVISION = "ವಿಭಾಗದ ಹೆಸರು"
COL_DISTRICT = "ಜಿಲ್ಲೆ"
COL_TALUK = "ತಾಲ್ಲೂಕು"
COL_CONSTITUENCY = "ಮತಕ್ಷೇತ್ರ"

COL_EST_AMT = "ಮೂಲ ಅಂದಾಜು ಮೊತ್ತ"
COL_TENDER_AMT = "ಗುತ್ತಿಗೆ ಮೊತ್ತ (ಜಿ.ಎಸ್.ಟಿ ಸೇರಿದಂತೆ)"
COL_REV_EST_AMT = "ಪರಿಷ್ಕೃತ ಅಂದಾಜು ಮೊತ್ತ (ಜಿ.ಎಸ್.ಟಿ ಸೇರಿದಂತೆ)"
COL_EXP_MAR26 = "ಮಾರ್ಚ್ 2026 ವರೆಗಿನ ವೆಚ್ಚ"
COL_EXP_26_27 = "2026-27ನೇ ಸಾಲಿನ ವೆಚ್ಚ"
COL_TOTAL_EXP = "ಒಟ್ಟಾರೆ ವೆಚ್ಚ"
COL_PENDING_BILL = "ಬಾಕಿ ಬಿಲ್ಲಿನ ಮೊತ್ತ"
COL_BAL_REQ = "ಕಾಮಗಾರಿಯನ್ನು ಪೂರ್ಣಗೊಳಿಸಲು ಬೇಕಾಗುವ ಬಾಕಿ ಮೊತ್ತ"

FINANCIAL_COLUMNS = [
    COL_EST_AMT,
    COL_TENDER_AMT,
    COL_REV_EST_AMT,
    COL_EXP_MAR26,
    COL_EXP_26_27,
    COL_TOTAL_EXP,
    COL_PENDING_BILL,
    COL_BAL_REQ,
]

# ==============================================================================
# 3. HELPER FUNCTIONS FOR FUZZY MATCHING & COLUMN NORMALIZATION
# ==============================================================================
def clean_text(val) -> str:
    """Removes zero-width characters, newlines, and extra spaces."""
    if pd.isna(val):
        return ""
    s = str(val)
    s = re.sub(r"[\u200b\u200c\u200d\ufeff\r\n\t]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def levenshtein_distance(s1: str, s2: str) -> int:
    """Calculates character-level Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


def match_division(raw_val) -> str | None:
    """
    Matches a raw cell value under 'ವಿಭಾಗದ ಹೆಸರು' to one of the 8 canonical
    divisions, tolerating leading/trailing spaces and 1-2 character typos.
    Returns None if the value does not belong to the 8 target divisions.
    """
    cleaned = clean_text(raw_val)
    if not cleaned:
        return None

    # Remove generic suffixes like 'ವಿಭಾಗ' or punctuation if present
    cleaned_core = re.sub(r"\bವಿಭಾಗ\b", "", cleaned).strip(" ,.-()/\\")
    if not cleaned_core:
        cleaned_core = cleaned

    # 1. Direct match
    if cleaned_core in VALID_DIVISIONS:
        return cleaned_core

    # 2. Known alias match
    if cleaned_core in DIVISION_ALIASES:
        return DIVISION_ALIASES[cleaned_core]

    # 3. Substring containment (e.g., 'ಧಾರವಾಡ ವಿಭಾಗ' or 'ಕಲಬುರಗಿ (ನೀ)')
    for div in VALID_DIVISIONS:
        if div in cleaned_core:
            return div
    for alias, canonical in DIVISION_ALIASES.items():
        if alias in cleaned_core:
            return canonical

    # 4. Fuzzy / 1-letter typo tolerance (Levenshtein distance <= 2 or similarity >= 0.78)
    best_match = None
    best_dist = 999
    best_ratio = 0.0

    candidates = {d: d for d in VALID_DIVISIONS}
    candidates.update(DIVISION_ALIASES)

    for token in [cleaned_core] + cleaned_core.split():
        if len(token) < 3:
            continue
        for cand_str, canonical in candidates.items():
            dist = levenshtein_distance(token, cand_str)
            ratio = difflib.SequenceMatcher(None, token, cand_str).ratio()
            if (dist <= 2 or ratio >= 0.78) and (
                dist < best_dist or (dist == best_dist and ratio > best_ratio)
            ):
                best_dist = dist
                best_ratio = ratio
                best_match = canonical

    return best_match


def extract_sheet_id(url_or_id: str) -> str:
    """Extracts the spreadsheet ID from a Google Sheets URL."""
    url_or_id = url_or_id.strip()
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", url_or_id)
    if match:
        return match.group(1)
    return url_or_id


def normalize_sheet_key(name: str) -> str:
    """Normalizes sheet names for matching (strips quotes, ranges like !A1:AB, and spaces)."""
    s = re.sub(r"!.*$", "", str(name))
    s = s.strip("'\" ")
    s = re.sub(r"\s+", " ", s)
    return s.lower()


def detect_and_map_columns(df: pd.DataFrame, sheet_name: str) -> pd.DataFrame:
    """
    Identifies the required columns in a sheet even if headers contain extra spaces,
    newlines, or extended text (like CP/CF inside a longer column header).
    """
    col_mapping = {}

    for col in df.columns:
        c_clean = clean_text(col)
        c_nospace = c_clean.replace(" ", "")
        c_upper = c_clean.upper()

        # 1. S/F Filter Column
        if re.search(r"\bS\s*/\s*F\b", c_upper) or c_upper == "S/F":
            col_mapping.setdefault(COL_SF, col)

        # 2. Progress Status (CP/CF pattern)
        elif "CP/CF" in c_upper or re.search(r"CP\s*/\s*CF", c_upper):
            col_mapping.setdefault(COL_PROGRESS, col)

        # 3. ಲೆಕ್ಕ ಶೀರ್ಷಿಕೆ
        elif "ಲೆಕ್ಕಶೀರ್ಷಿಕೆ" in c_nospace or "ಲೆಕ್ಕ ಶೀರ್ಷಿಕೆ" in c_clean:
            col_mapping.setdefault(COL_HEAD, col)

        # 4. ವಿಭಾಗದ ಹೆಸರು
        elif "ವಿಭಾಗದಹೆಸರು" in c_nospace or c_clean == "ವಿಭಾಗ":
            col_mapping.setdefault(COL_DIVISION, col)

        # 5. ಜಿಲ್ಲೆ
        elif c_nospace == "ಜಿಲ್ಲೆ" or "ಜಿಲ್ಲೆಯಹೆಸರು" in c_nospace:
            col_mapping.setdefault(COL_DISTRICT, col)

        # 6. ತಾಲ್ಲೂಕು
        elif c_nospace in ["ತಾಲ್ಲೂಕು", "ತಾಲೂಕು"]:
            col_mapping.setdefault(COL_TALUK, col)

        # 7. ಮತಕ್ಷೇತ್ರ
        elif "ಮತಕ್ಷೇತ್ರ" in c_nospace:
            col_mapping.setdefault(COL_CONSTITUENCY, col)

        # 8. Financial Columns
        elif "ಮೂಲಅಂದಾಜುಮೊತ್ತ" in c_nospace:
            col_mapping.setdefault(COL_EST_AMT, col)
        elif "ಗುತ್ತಿಗೆಮೊತ್ತ" in c_nospace:
            col_mapping.setdefault(COL_TENDER_AMT, col)
        elif "ಪರಿಷ್ಕೃತಅಂದಾಜುಮೊತ್ತ" in c_nospace:
            col_mapping.setdefault(COL_REV_EST_AMT, col)
        elif ("ಮಾರ್ಚ್" in c_nospace and "2026" in c_nospace and "ವೆಚ್ಚ" in c_nospace) or (
            "ಮಾರ್ಚ್2026ವರೆಗಿನವೆಚ್ಚ" in c_nospace
        ):
            col_mapping.setdefault(COL_EXP_MAR26, col)
        elif "2026-27" in c_nospace and "ವೆಚ್ಚ" in c_nospace:
            col_mapping.setdefault(COL_EXP_26_27, col)
        elif "ಒಟ್ಟಾರೆವೆಚ್ಚ" in c_nospace or "ಒಟ್ಟುವೆಚ್ಚ" in c_nospace:
            col_mapping.setdefault(COL_TOTAL_EXP, col)
        elif "ಬಾಕಿಬಿಲ್ಲಿನಮೊತ್ತ" in c_nospace or "ಬಾಕಿಬಿಲ್" in c_nospace:
            col_mapping.setdefault(COL_PENDING_BILL, col)
        elif "ಪೂರ್ಣಗೊಳಿಸಲುಬೇಕಾಗುವಬಾಕಿಮೊತ್ತ" in c_nospace or (
            "ಪೂರ್ಣಗೊಳಿಸಲು" in c_nospace and "ಬಾಕಿ" in c_nospace
        ):
            col_mapping.setdefault(COL_BAL_REQ, col)

    # Build a clean standardized dataframe
    std_df = pd.DataFrame(index=df.index)
    std_df["SHEET_NAME"] = sheet_name.strip()

    all_target_cols = [
        COL_SF,
        COL_PROGRESS,
        COL_HEAD,
        COL_DIVISION,
        COL_DISTRICT,
        COL_TALUK,
        COL_CONSTITUENCY,
    ] + FINANCIAL_COLUMNS

    for target_col in all_target_cols:
        if target_col in col_mapping:
            src_col = col_mapping[target_col]
            series_data = df[src_col]
            # Handle duplicate column names in raw sheet if any
            if isinstance(series_data, pd.DataFrame):
                series_data = series_data.iloc[:, 0]
            std_df[target_col] = series_data
        else:
            std_df[target_col] = np.nan

    return std_df


def parse_single_sheet(raw_df: pd.DataFrame, sheet_name: str) -> pd.DataFrame:
    """
    Finds the header row dynamically (scanning first 15 rows for 'ವಿಭಾಗದ ಹೆಸರು' or 'ಜಿಲ್ಲೆ'),
    maps columns, filters rows by the 8 valid divisions (with fuzzy matching),
    and converts financial columns to numeric values.
    """
    if raw_df.empty:
        return pd.DataFrame()

    header_row_idx = None
    for idx in range(min(15, len(raw_df))):
        row_Text = " ".join([clean_text(v).replace(" ", "") for v in raw_df.iloc[idx].values])
        if "ವಿಭಾಗದಹೆಸರು" in row_Text or ("ಜಿಲ್ಲೆ" in row_Text and "ತಾಲ್ಲೂಕು" in row_Text):
            header_row_idx = idx
            break

    if header_row_idx is not None:
        # Combine multi-row headers if the row directly below also has sub-headers (like CP/CF or amounts)
        headers = [clean_text(v) for v in raw_df.iloc[header_row_idx].values]
        if header_row_idx + 1 < len(raw_df):
            next_row = [clean_text(v) for v in raw_df.iloc[header_row_idx + 1].values]
            next_joined = " ".join(next_row)
            # If the next row looks like a sub-header row (contains CP/CF or ವೆಚ್ಚ but no valid division data)
            if ("CP/CF" in next_joined.upper() or "ವೆಚ್ಚ" in next_joined) and not any(
                match_division(x) for x in next_row
            ):
                combined_headers = []
                for h1, h2 in zip(headers, next_row):
                    if h2 and h2 != h1 and not h2.isdigit():
                        combined_headers.append(f"{h1} {h2}".strip())
                    else:
                        combined_headers.append(h1)
                headers = combined_headers
                header_row_idx += 1

        df = raw_df.iloc[header_row_idx + 1 :].copy()
        df.columns = [
            h if h else f"Unnamed_{i}" for i, h in enumerate(headers)
        ]
    else:
        df = raw_df.copy()

    std_df = detect_and_map_columns(df, sheet_name)

    # Apply fuzzy matching on 'ವಿಭಾಗದ ಹೆಸರು' and filter to ONLY the 8 valid divisions
    std_df[COL_DIVISION] = std_df[COL_DIVISION].apply(match_division)
    std_df = std_df[std_df[COL_DIVISION].notna()].copy()

    if std_df.empty:
        return std_df

    # Clean text filter columns
    for text_col in [COL_SF, COL_PROGRESS, COL_HEAD, COL_DISTRICT, COL_TALUK, COL_CONSTITUENCY]:
        std_df[text_col] = std_df[text_col].apply(clean_text)
        std_df[text_col] = std_df[text_col].replace("", "N/A")

    # Clean & convert numeric financial columns
    for fin_col in FINANCIAL_COLUMNS:
        cleaned_num = (
            std_df[fin_col]
            .astype(str)
            .str.replace(",", "", regex=False)
            .str.replace("₹", "", regex=False)
            .str.strip()
        )
        std_df[fin_col] = pd.to_numeric(cleaned_num, errors="coerce").fillna(0.0)

    return std_df


@st.cache_data(ttl=600, show_spinner=False)
def load_workbook_data(sheet_url: str) -> tuple[pd.DataFrame, list[str], list[str]]:
    """
    Downloads the Google Spreadsheet as an Excel stream in a single request
    and processes all 20 target sheets.
    """
    sheet_id = extract_sheet_id(sheet_url)
    export_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"

    response = requests.get(export_url, timeout=60)
    response.raise_for_status()

    excel_file = pd.ExcelFile(io.BytesIO(response.content), engine="openpyxl")
    available_map = {normalize_sheet_key(name): name for name in excel_file.sheet_names}

    loaded_frames = []
    loaded_sheets = []
    missing_sheets = []

    for target in TARGET_SHEETS_RAW:
        norm_key = normalize_sheet_key(target)
        actual_name = available_map.get(norm_key)

        # Fallback: ignore underscores/spaces differences when matching sheet names
        if actual_name is None:
            compact_target = re.sub(r"[\s_]+", "", norm_key)
            for avail_norm, avail_orig in available_map.items():
                if re.sub(r"[\s_]+", "", avail_norm) == compact_target:
                    actual_name = avail_orig
                    break

        if actual_name is not None:
            raw_sheet_df = pd.read_excel(excel_file, sheet_name=actual_name, header=None)
            parsed_df = parse_single_sheet(raw_sheet_df, actual_name)
            if not parsed_df.empty:
                loaded_frames.append(parsed_df)
            loaded_sheets.append(actual_name)
        else:
            missing_sheets.append(target)

    if loaded_frames:
        combined_df = pd.concat(loaded_frames, ignore_index=True)
    else:
        combined_df = pd.DataFrame()

    return combined_df, loaded_sheets, missing_sheets


# ==============================================================================
# 4. MAIN APPLICATION UI
# ==============================================================================
def main():
    st.markdown(
        """
        <div class="main-header">
            <h1>📊 ಕಾಮಗಾರಿಗಳ ಪ್ರಗತಿ ವರದಿ (Works Progress Dashboard)</h1>
            <p>Consolidated Multi-Sheet Analytics & Financial Progress Tracker (2026-27)</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.header("⚙️ Data Source & Controls")
        sheet_url_input = st.text_input(
            "Google Spreadsheet URL",
            value=DEFAULT_SHEET_URL,
            help="Paste your Google Sheet link (shared as 'Anyone with the link can view').",
        )
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("🔄 Refresh Data", use_container_width=True):
                st.cache_data.clear()
        with col_btn2:
            unit_mode = st.selectbox(
                "Display Unit",
                options=["Lakhs (ಲಕ್ಷಗಳಲ್ಲಿ)", "Crores (ಕೋಟಿಗಳಲ್ಲಿ)"],
                index=0,
            )

    if not sheet_url_input or "PASTE_YOUR_GOOGLE_SPREADSHEET_URL_HERE" in sheet_url_input:
        st.info(
            "👈 Please enter your Google Spreadsheet URL in the sidebar (or set `DEFAULT_SHEET_URL` in `app.py`) to load the dashboard."
        )
        st.stop()

    with st.spinner("Loading and consolidating 20 sheets from Google Drive..."):
        try:
            df, loaded_sheets, missing_sheets = load_workbook_data(sheet_url_input)
        except Exception as e:
            st.error(
                f"Unable to fetch spreadsheet. Ensure the sheet is shared with 'Anyone with the link' or upload the file. Details: {e}"
            )
            st.stop()

    if df.empty:
        st.warning("No matching rows found for the 8 specified divisions across the target sheets.")
        st.stop()

    # ==========================================================================
    # 5. SIDEBAR FILTERS (CASCADING & MULTI-SELECT)
    # ==========================================================================
    st.sidebar.markdown("---")
    st.sidebar.header("🔍 ಫಿಲ್ಟರ್‌ಗಳು (Filters)")

    filtered_df = df.copy()

    def apply_multiselect_filter(data: pd.DataFrame, col_name: str, label: str) -> pd.DataFrame:
        options = sorted([x for x in data[col_name].dropna().unique() if x != "N/A"])
        if "N/A" in data[col_name].values:
            options.append("N/A")
        selected = st.sidebar.multiselect(label, options=options, default=[])
        if selected:
            return data[data[col_name].isin(selected)]
        return data

    # 1. S / F FILTER
    filtered_df = apply_multiselect_filter(filtered_df, COL_SF, "1. S / F FILTER")

    # 2. PROGRESS STATUS FILTER (CP/CF)
    filtered_df = apply_multiselect_filter(
        filtered_df, COL_PROGRESS, "2. PROGRESS STATUS FILTER (CP/CF)"
    )

    # 3. ಲೆಕ್ಕಶೀರ್ಷಿಕೆ FILTER
    filtered_df = apply_multiselect_filter(
        filtered_df, COL_HEAD, "3. ಲೆಕ್ಕಶೀರ್ಷಿಕೆ FILTER (ಲೆಕ್ಕ ಶೀರ್ಷಿಕೆ)"
    )

    # 4. ವಿಭಾಗ FILTER (Ordered by the 8 canonical divisions)
    avail_divisions = [d for d in VALID_DIVISIONS if d in filtered_df[COL_DIVISION].unique()]
    sel_divisions = st.sidebar.multiselect(
        "4. ವಿಭಾಗ FILTER (ವಿಭಾಗದ ಹೆಸರು)", options=avail_divisions, default=[]
    )
    if sel_divisions:
        filtered_df = filtered_df[filtered_df[COL_DIVISION].isin(sel_divisions)]

    # 5. ಜಿಲ್ಲೆ FILTER
    filtered_df = apply_multiselect_filter(filtered_df, COL_DISTRICT, "5. ಜಿಲ್ಲೆ FILTER")

    # 6. ತಾಲ್ಲೂಕು FILTER
    filtered_df = apply_multiselect_filter(filtered_df, COL_TALUK, "6. ತಾಲ್ಲೂಕು FILTER")

    # 7. ಮತಕ್ಷೇತ್ರ FILTER
    filtered_df = apply_multiselect_filter(filtered_df, COL_CONSTITUENCY, "7. ಮತಕ್ಷೇತ್ರ FILTER")

    # 8. ಮೂಲ ಅಂದಾಜು ಮೊತ್ತ (RANGE) FILTER (Supports multiple overlapping selections)
    sel_ranges = st.sidebar.multiselect(
        "8. ಮೂಲ ಅಂದಾಜು ಮೊತ್ತ (RANGE) FILTER",
        options=list(ESTIMATE_RANGES.keys()),
        default=[],
        help="Values in sheet are in Lakhs (100 Lakhs = 1 Crore). You can select multiple ranges.",
    )
    if sel_ranges:
        range_mask = pd.Series(False, index=filtered_df.index)
        for r_label in sel_ranges:
            range_mask = range_mask | ESTIMATE_RANGES[r_label](filtered_df[COL_EST_AMT])
        filtered_df = filtered_df[range_mask]

    # ==========================================================================
    # 6. KPI METRIC CARDS (9 REQUIRED VALUES)
    # ==========================================================================
    is_crores = unit_mode.startswith("Crores")
    divisor = 100.0 if is_crores else 1.0
    unit_suffix = "Cr (ಕೋಟಿ)" if is_crores else "Lakhs (ಲಕ್ಷ)"

    total_works = len(filtered_df)
    sums = {col: filtered_df[col].sum() / divisor for col in FINANCIAL_COLUMNS}

    st.subheader(f"📌 ಪ್ರಮುಖ ಅಂಕಿಅಂಶಗಳು (Summary Metrics — in {unit_suffix})")

    kpi_items = [
        ("ಒಟ್ಟು ಕಾಮಗಾರಿಗಳ ಸಂಖ್ಯೆ", f"{total_works:,}", "Total Number of Works", True),
        (
            "ಒಟ್ಟು ಅಂದಾಜು ಮೊತ್ತ",
            f"₹ {sums[COL_EST_AMT]:,.2f}",
            f"ಮೂಲ ಅಂದಾಜು ಮೊತ್ತ ({unit_suffix})",
            False,
        ),
        (
            "ಗುತ್ತಿಗೆ ಮೊತ್ತ (ಜಿ.ಎಸ್.ಟಿ ಸೇರಿದಂತೆ)",
            f"₹ {sums[COL_TENDER_AMT]:,.2f}",
            f"Tender Amount incl. GST ({unit_suffix})",
            False,
        ),
        (
            "ಪರಿಷ್ಕೃತ ಅಂದಾಜು ಮೊತ್ತ (ಜಿ.ಎಸ್.ಟಿ ಸೇರಿದಂತೆ)",
            f"₹ {sums[COL_REV_EST_AMT]:,.2f}",
            f"ಪರಿಷ್ಕೃತ ಅಂದಾಜು ಮೊತ್ತ ({unit_suffix})",
            False,
        ),
        (
            "ಮಾರ್ಚ್ 2026 ವರೆಗಿನ ವೆಚ್ಚ",
            f"₹ {sums[COL_EXP_MAR26]:,.2f}",
            f"Expenditure up to March 2026 ({unit_suffix})",
            False,
        ),
        (
            "2026-27ನೇ ಸಾಲಿನ ವೆಚ್ಚ",
            f"₹ {sums[COL_EXP_26_27]:,.2f}",
            f"2026-27 Expenditure ({unit_suffix})",
            False,
        ),
        (
            "ಒಟ್ಟಾರೆ ವೆಚ್ಚ",
            f"₹ {sums[COL_TOTAL_EXP]:,.2f}",
            f"Total Expenditure ({unit_suffix})",
            False,
        ),
        (
            "ಬಾಕಿ ಬಿಲ್ಲಿನ ಮೊತ್ತ",
            f"₹ {sums[COL_PENDING_BILL]:,.2f}",
            f"Pending Bill Amount ({unit_suffix})",
            False,
        ),
        (
            "ಕಾಮಗಾರಿಯನ್ನು ಪೂರ್ಣಗೊಳಿಸಲು ಬೇಕಾಗುವ ಬಾಕಿ ಮೊತ್ತ",
            f"₹ {sums[COL_BAL_REQ]:,.2f}",
            f"Balance Required to Complete ({unit_suffix})",
            False,
        ),
    ]

    for row_start in range(0, 9, 3):
        cols = st.columns(3)
        for idx, col_ui in enumerate(cols):
            title, val_str, sub_str, is_count = kpi_items[row_start + idx]
            card_cls = "kpi-card count-card" if is_count else "kpi-card"
            with col_ui:
                st.markdown(
                    f"""
                    <div class="{card_cls}">
                        <div class="kpi-title">{title}</div>
                        <div class="kpi-value">{val_str}</div>
                        <div class="kpi-sub">{sub_str}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    st.markdown("---")

    # ==========================================================================
    # 7. TABS: DIVISION ABSTRACT, VISUAL CHARTS & DETAILED DATA
    # ==========================================================================
    tab1, tab2, tab3, tab4 = st.tabs(
        [
            "📋 ವಿಭಾಗವಾರು ಸಾರಾಂಶ (Division Abstract)",
            "📈 ನಕ್ಷೆಗಳು (Visual Analytics)",
            "📄 ಸಂಪೂರ್ಣ ಕಾಮಗಾರಿಗಳ ವಿವರ (Detailed Works)",
            "🗂️ ಮೂಲ ಶೀಟ್ ಸ್ಥಿತಿ (Sheet Status)",
        ]
    )

    with tab1:
        st.markdown(f"#### ವಿಭಾಗವಾರು ಗೋಷ್ಟ್ವಾರೆ (Values in {unit_suffix})")
        div_group = (
            filtered_df.groupby(COL_DIVISION, as_index=False)
            .agg(
                ಒಟ್ಟು_ಕಾಮಗಾರಿಗಳ_ಸಂಖ್ಯೆ=(COL_DIVISION, "count"),
                **{col: (col, lambda s: round(s.sum() / divisor, 2)) for col in FINANCIAL_COLUMNS},
            )
            .rename(
                columns={
                    "ಒಟ್ಟು_ಕಾಮಗಾರಿಗಳ_ಸಂಖ್ಯೆ": "ಒಟ್ಟು ಕಾಮಗಾರಿಗಳ ಸಂಖ್ಯೆ",
                    COL_EST_AMT: "ಒಟ್ಟು ಅಂದಾಜು ಮೊತ್ತ",
                }
            )
        )

        # Add Grand Total row
        if not div_group.empty:
            total_row = {"ವಿಭಾಗದ ಹೆಸರು": "ಒಟ್ಟು (Grand Total)"}
            for c in div_group.columns[1:]:
                total_row[c] = div_group[c].sum()
            div_summary_df = pd.concat(
                [div_group, pd.DataFrame([total_row])], ignore_index=True
            )
            st.dataframe(div_summary_df, use_container_width=True, hide_index=True)

    with tab2:
        c1, c2 = st.columns(2)
        with c1:
            fig_bar = px.bar(
                div_group,
                x=COL_DIVISION,
                y=["ಒಟ್ಟು ಅಂದಾಜು ಮೊತ್ತ", COL_TOTAL_EXP, COL_BAL_REQ],
                barmode="group",
                title=f"ವಿಭಾಗವಾರು ಅಂದಾಜು ಮೊತ್ತ vs ಒಟ್ಟಾರೆ ವೆಚ್ಚ ({unit_suffix})",
                labels={"value": unit_suffix, "variable": "ವಿವರ"},
            )
            st.plotly_chart(fig_bar, use_container_width=True)

        with c2:
            status_counts = (
                filtered_df.groupby(COL_PROGRESS, as_index=False)
                .size()
                .rename(columns={"size": "ಕಾಮಗಾರಿಗಳ ಸಂಖ್ಯೆ"})
            )
            fig_pie = px.pie(
                status_counts,
                names=COL_PROGRESS,
                values="ಕಾಮಗಾರಿಗಳ ಸಂಖ್ಯೆ",
                hole=0.4,
                title="ಪ್ರಗತಿ ಹಂತ (CP/CF) ವಾರು ಕಾಮಗಾರಿಗಳ ಹಂಚಿಕೆ",
            )
            st.plotly_chart(fig_pie, use_container_width=True)

    with tab3:
        st.markdown(f"#### ಫಿಲ್ಟರ್ ಮಾಡಲಾದ ಕಾಮಗಾರಿಗಳ ಪಟ್ಟಿ ({len(filtered_df):,} ಕಾಮಗಾರಿಗಳು)")
        csv_bytes = filtered_df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            label="📥 Download Filtered Data (CSV)",
            data=csv_bytes,
            file_name="filtered_progress_report_2026_27.csv",
            mime="text/csv",
        )
        st.dataframe(filtered_df, use_container_width=True, height=500)

    with tab4:
        st.markdown("#### ಪರಿಗಣಿಸಲಾದ ಶೀಟ್‌ಗಳ ಸ್ಥಿತಿ (20 Target Sheets)")
        sheet_counts = (
            df.groupby("SHEET_NAME")
            .size()
            .reset_index(name="Valid Rows (8 Target Divisions)")
        )
        st.dataframe(sheet_counts, use_container_width=True, hide_index=True)
        if missing_sheets:
            st.warning(f"Sheets not found in workbook: {', '.join(missing_sheets)}")


if __name__ == "__main__":
    main()
