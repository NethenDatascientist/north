import io
import os
import re
import time
import pickle
import difflib
import unicodedata
from urllib.parse import quote
from datetime import datetime, timezone, timedelta
import requests
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px

# ==============================================================================
# 1. PAGE CONFIGURATION & CUSTOM STYLING
# ==============================================================================
st.set_page_config(
    page_title="ಕಾಮಗಾರಿಗಳ ಪ್ರಗತಿ ವರದಿ",
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
SNAPSHOT_FILE = "snapshot_data.pkl"

DEFAULT_SHEET_URL = st.secrets.get(
    "SPREADSHEET_URL",
    "https://docs.google.com/spreadsheets/d/1Mx-GVqqiznd_etK9pyygYd4uym0qfawCU_Rs-F5vbrk/edit?usp=sharing",
)

TARGET_SHEETS = [
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

ESTIMATE_RANGES = {
    "More than 100CR : > 10000": lambda s: s > 10000,
    "25CR - 100CR : > 2500 to <= 10000": lambda s: (s > 2500) & (s <= 10000),
    "10CR - 25CR : > 1000 to <= 2500": lambda s: (s > 1000) & (s <= 2500),
    "5CR - 10CR : > 500 to <= 1000": lambda s: (s > 500) & (s <= 1000),
    "2CR - 5CR : > 200 to <= 500": lambda s: (s > 200) & (s <= 500),
    "1CR - 5CR : > 100 to <= 500": lambda s: (s > 100) & (s <= 500),
    "0 - 2CR : >= 0 to <= 200": lambda s: (s >= 0) & (s <= 200),
    "Less than 1CR : < 100": lambda s: s < 100,
}

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
COL_BAL_REQ = "ಕಾಮಗಾರಿಯನ್ನು ಪುರ್ಣಗೊಳಿಸಲು ಬೇಕಾದ ಬಾಕಿ ಮೊತ್ತ"

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
# 3. TEXT CLEANING, KANNADA PHONETIC KEY & FUZZY UNIFICATION
# ==============================================================================
def clean_text(val) -> str:
    if pd.isna(val):
        return ""
    s = unicodedata.normalize("NFC", str(val))
    s = re.sub(r"[\u200b\u200c\u200d\ufeff\r\n\t]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def normalize_cp_cf(val) -> str:
    s = clean_text(val)
    if not s:
        return "N/A"
    s_upper = s.upper()
    s_compact = re.sub(r"[\s\-_]+", "", s_upper)
    if s_compact in {"P", "CF", "CP", "F", "S", "C", "NS", "WIP"} or re.match(
        r"^[A-Z0-9/]+$", s_compact
    ):
        return s_compact
    s_upper = re.sub(r"\bC\s*F\b", "CF", s_upper)
    s_upper = re.sub(r"\bC\s*P\b", "CP", s_upper)
    return s_upper


def normalize_sf(val) -> str:
    s = clean_text(val)
    if not s:
        return "N/A"
    s_upper = s.upper()
    s_compact = re.sub(r"[\s\-_]+", "", s_upper)
    if re.match(r"^[A-Z0-9/]+$", s_compact):
        return s_compact
    return s_upper


def levenshtein_distance(s1: str, s2: str) -> int:
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


def kannada_phonetic_key(s: str) -> str:
    s = clean_text(s)
    s = re.sub(r"[\s\-_.,()]+", "", s)
    s = re.sub(r"ಮ್$", "ಂ", s)
    s = re.sub(r"್$", "", s)
    s = re.sub(r"ೂರು$", "ುರ", s)
    s = re.sub(r"ೂರ$", "ುರ", s)
    vowel_map = str.maketrans({
        "ೀ": "ಿ",
        "ೂ": "ು",
        "ೇ": "ೆ",
        "ೋ": "ೊ",
        "ಆ": "ಅ",
        "ಈ": "ಇ",
        "ಊ": "ಉ",
        "ಏ": "ಎ",
        "ಓ": "ಒ",
        "ಖ": "ಕ",
        "ಘ": "ಗ",
        "ಛ": "ಚ",
        "ಝ": "ಜ",
        "ಠ": "ಟ",
        "ಢ": "ಡ",
        "ಥ": "ತ",
        "ಧ": "ದ",
        "ಫ": "ಪ",
        "ಭ": "ಬ",
        "ಷ": "ಶ",
    })
    s = s.translate(vowel_map)
    s = re.sub(r"ಾ$", "", s)
    return s


def unify_similar_names(series: pd.Series, preserve_slash: bool = True) -> pd.Series:
    val_counts = series.value_counts()
    canonical_map = {}
    phonetic_to_canonical = {}
    canonical_list = []

    for val, _ in val_counts.items():
        if not val or val == "N/A":
            canonical_map[val] = "N/A"
            continue

        if preserve_slash and "/" in val:
            canonical_map[val] = val
            continue

        pkey = kannada_phonetic_key(val)
        if not pkey:
            canonical_map[val] = val
            continue

        if pkey in phonetic_to_canonical:
            canonical_map[val] = phonetic_to_canonical[pkey]
            continue

        val_nospace = re.sub(r"\s+", "", val)
        matched_canon = None
        for canon in canonical_list:
            canon_nospace = re.sub(r"\s+", "", canon)
            if len(val_nospace) >= 4 and len(canon_nospace) >= 4:
                if val_nospace[0] == canon_nospace[0]:
                    dist = levenshtein_distance(val_nospace, canon_nospace)
                    if dist <= 1:
                        matched_canon = canon
                        break

        if matched_canon:
            canonical_map[val] = matched_canon
            phonetic_to_canonical[pkey] = matched_canon
        else:
            canonical_map[val] = val
            phonetic_to_canonical[pkey] = val
            canonical_list.append(val)

    return series.map(lambda x: canonical_map.get(x, x))


def match_division(raw_val) -> str | None:
    cleaned = clean_text(raw_val)
    if not cleaned:
        return None

    cleaned_core = re.sub(r"\bವಿಭಾಗ\b", "", cleaned).strip(" ,.-()/\\")
    if not cleaned_core:
        cleaned_core = cleaned

    if cleaned_core in VALID_DIVISIONS:
        return cleaned_core

    if cleaned_core in DIVISION_ALIASES:
        return DIVISION_ALIASES[cleaned_core]

    for div in VALID_DIVISIONS:
        if div in cleaned_core:
            return div
    for alias, canonical in DIVISION_ALIASES.items():
        if alias in cleaned_core:
            return canonical

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
    url_or_id = url_or_id.strip()
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", url_or_id)
    if match:
        return match.group(1)
    return url_or_id


def detect_and_map_columns(df: pd.DataFrame, sheet_name: str) -> pd.DataFrame:
    col_mapping = {}

    for col in df.columns:
        c_clean = clean_text(col)
        c_nospace = c_clean.replace(" ", "")
        c_upper = c_clean.upper()

        if re.search(r"\bS\s*/\s*F\b", c_upper) or c_upper == "S/F":
            col_mapping.setdefault(COL_SF, col)
        elif "CP/CF" in c_upper or re.search(r"CP\s*/\s*CF", c_upper):
            col_mapping.setdefault(COL_PROGRESS, col)
        elif "ಲೆಕ್ಕಶೀರ್ಷಿಕೆ" in c_nospace or "ಲೆಕ್ಕಶಿರ್ಷಿಕೆ" in c_nospace or "ಲೆಕ್ಕ" in c_nospace:
            col_mapping.setdefault(COL_HEAD, col)
        elif "ವಿಭಾಗದಹೆಸರು" in c_nospace or c_clean == "ವಿಭಾಗ":
            col_mapping.setdefault(COL_DIVISION, col)
        elif c_nospace == "ಜಿಲ್ಲೆ" or "ಜಿಲ್ಲೆಯಹೆಸರು" in c_nospace or c_nospace.startswith("ಜಿಲ್ಲೆ"):
            col_mapping.setdefault(COL_DISTRICT, col)
        elif any(t in c_nospace for t in ["ತಾಲ್ಲೂಕು", "ತಾಲೂಕು", "ತಾಲ್ಲುಕು", "ತಾಲೂಕ"]):
            col_mapping.setdefault(COL_TALUK, col)
        elif (
            "ಮತಕ್ಷ" in c_nospace
            or "ವಿಧಾನಸಭ" in c_nospace
            or "ಮತಕ್ಷೇತ್ರ" in c_nospace
            or "ಮತಕ್ಷೆತ್ರ" in c_nospace
            or (
                ("ಕ್ಷೇತ್ರ" in c_nospace or "ಕ್ಷೆತ್ರ" in c_nospace)
                and not any(x in c_nospace for x in ["ಅಚ್ಚುಕಟ್ಟು", "ಹೆಕ್ಟೇರ್", "ಎಕರೆ", "ರೈತರ"])
            )
        ):
            col_mapping.setdefault(COL_CONSTITUENCY, col)
        elif "ಮೂಲಅಂದಾಜುಮೊತ್ತ" in c_nospace:
            col_mapping.setdefault(COL_EST_AMT, col)
        elif "ಗುತ್ತಿಗೆಮೊತ್ತ" in c_nospace:
            col_mapping.setdefault(COL_TENDER_AMT, col)
        elif "ಪರಿಷ್ಕೃತಅಂದಾಜುಮೊತ್ತ" in c_nospace:
            col_mapping.setdefault(COL_REV_EST_AMT, col)
        elif (
            "ಮಾರ್ಚ-2026ವರೆಗಿನವೆಚ್ಚ" in c_nospace
            or "ಮಾರ್ಚ್-2026ವರೆಗಿನವೆಚ್ಚ" in c_nospace
            or (
                ("ಮಾರ್ಚ" in c_nospace or "ಮಾರ್ಚ್" in c_nospace)
                and "2026" in c_nospace
                and "ವೆಚ್ಚ" in c_nospace
            )
        ):
            col_mapping.setdefault(COL_EXP_MAR26, col)
        elif "2026-27" in c_nospace and "ವೆಚ್ಚ" in c_nospace:
            col_mapping.setdefault(COL_EXP_26_27, col)
        elif "ಒಟ್ಟಾರೆವೆಚ್ಚ" in c_nospace or "ಒಟ್ಟುವೆಚ್ಚ" in c_nospace:
            col_mapping.setdefault(COL_TOTAL_EXP, col)
        elif "ಬಾಕಿಬಿಲ್ಲಿನಮೊತ್ತ" in c_nospace or "ಬಾಕಿಬಿಲ್" in c_nospace:
            col_mapping.setdefault(COL_PENDING_BILL, col)
        elif (
            "ಪುರ್ಣಗೊಳಿಸಲುಬೇಕಾದಬಾಕಿಮೊತ್ತ" in c_nospace
            or "ಪೂರ್ಣಗೊಳಿಸಲುಬೇಕಾಗುವಬಾಕಿಮೊತ್ತ" in c_nospace
            or (
                ("ಪುರ್ಣಗೊಳಿಸಲು" in c_nospace or "ಪೂರ್ಣಗೊಳಿಸಲು" in c_nospace)
                and "ಬಾಕಿ" in c_nospace
            )
            or "(17-25)" in c_nospace
        ):
            col_mapping.setdefault(COL_BAL_REQ, col)

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
            if isinstance(series_data, pd.DataFrame):
                series_data = series_data.iloc[:, 0]
            std_df[target_col] = series_data
        else:
            std_df[target_col] = np.nan

    return std_df


def parse_single_sheet(raw_df: pd.DataFrame, sheet_name: str) -> pd.DataFrame:
    if raw_df.empty:
        return pd.DataFrame()

    header_row_idx = None
    for idx in range(min(15, len(raw_df))):
        row_text = " ".join([clean_text(v).replace(" ", "") for v in raw_df.iloc[idx].values])
        if "ವಿಭಾಗದಹೆಸರು" in row_text or ("ಜಿಲ್ಲೆ" in row_text and "ತಾಲ್ಲೂಕು" in row_text):
            header_row_idx = idx
            break

    if header_row_idx is not None:
        headers = [clean_text(v) for v in raw_df.iloc[header_row_idx].values]

        if header_row_idx > 0:
            prev_row = [clean_text(v) for v in raw_df.iloc[header_row_idx - 1].values]
            if sum(1 for x in prev_row if x) >= 3:
                headers = [h if h else p for h, p in zip(headers, prev_row)]

        data_start_idx = header_row_idx + 1
        if header_row_idx + 1 < len(raw_df):
            next_row = [clean_text(v) for v in raw_df.iloc[header_row_idx + 1].values]
            if not any(match_division(x) for x in next_row):
                next_joined = " ".join(next_row)
                if "CP/CF" in next_joined.upper() or "ವೆಚ್ಚ" in next_joined or "ಮತಕ್ಷ" in next_joined:
                    combined_headers = []
                    for h1, h2 in zip(headers, next_row):
                        if h2 and h2 != h1 and not h2.isdigit():
                            combined_headers.append(f"{h1} {h2}".strip())
                        else:
                            combined_headers.append(h1)
                    headers = combined_headers
                    data_start_idx = header_row_idx + 2

        df = raw_df.iloc[data_start_idx:].copy()
        df.columns = [h if h else f"Unnamed_{i}" for i, h in enumerate(headers)]
    else:
        df = raw_df.copy()

    std_df = detect_and_map_columns(df, sheet_name)

    std_df[COL_DIVISION] = std_df[COL_DIVISION].apply(match_division)
    std_df = std_df[std_df[COL_DIVISION].notna()].copy()

    if std_df.empty:
        return std_df

    std_df[COL_PROGRESS] = std_df[COL_PROGRESS].apply(normalize_cp_cf)
    std_df[COL_SF] = std_df[COL_SF].apply(normalize_sf)

    for text_col in [COL_HEAD, COL_DISTRICT, COL_TALUK, COL_CONSTITUENCY]:
        std_df[text_col] = std_df[text_col].apply(clean_text)
        std_df[text_col] = std_df[text_col].replace("", "N/A")

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


# ==============================================================================
# 4. TIMEOUT-PROOF SHEET FETCHER WITH LIVE PROGRESS BAR
# ==============================================================================
def finalize_and_save_snapshot(
    loaded_frames: list[pd.DataFrame], loaded_sheets: list[str], missing_sheets: list[str]
) -> dict:
    if loaded_frames:
        combined_df = pd.concat(loaded_frames, ignore_index=True)
        combined_df[COL_TALUK] = unify_similar_names(combined_df[COL_TALUK], preserve_slash=True)
        combined_df[COL_DISTRICT] = unify_similar_names(combined_df[COL_DISTRICT], preserve_slash=True)
        combined_df[COL_CONSTITUENCY] = unify_similar_names(
            combined_df[COL_CONSTITUENCY], preserve_slash=True
        )
    else:
        combined_df = pd.DataFrame()

    ist_now = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime(
        "%d-%m-%Y %I:%M %p IST"
    )

    snapshot_payload = {
        "df": combined_df,
        "loaded_sheets": sorted(loaded_sheets),
        "missing_sheets": missing_sheets,
        "timestamp": ist_now,
    }

    if not combined_df.empty:
        try:
            with open(SNAPSHOT_FILE, "wb") as f:
                pickle.dump(snapshot_payload, f)
        except Exception:
            pass

    return snapshot_payload


def fetch_single_sheet_with_retry(sheet_id: str, sheet_name: str) -> pd.DataFrame | None:
    """
    Downloads ONLY the requested sheet as CSV using Google's gviz endpoint.
    Completely bypasses 'doc-0g-9c-sheets.googleusercontent.com' full-xlsx export timeout!
    """
    candidates = [sheet_name]
    if sheet_name.strip() != sheet_name:
        candidates.append(sheet_name.strip())

    headers = {"User-Agent": "Mozilla/5.0"}

    for attempt in range(3):
        for cand in candidates:
            url = (
                f"https://docs.google.com/spreadsheets/d/{sheet_id}"
                f"/gviz/tq?tqx=out:csv&sheet={quote(cand)}"
            )
            try:
                resp = requests.get(url, headers=headers, timeout=(10, 25))
                if resp.status_code == 200:
                    text_data = resp.content.decode("utf-8", errors="replace")
                    if not text_data.lstrip().startswith("<!DOCTYPE html"):
                        raw_df = pd.read_csv(
                            io.StringIO(text_data),
                            header=None,
                            dtype=str,
                            on_bad_lines="skip",
                        )
                        return parse_single_sheet(raw_df, sheet_name.strip())
            except Exception:
                pass
        time.sleep(0.6 * (attempt + 1))

    return None


def download_and_build_snapshot(sheet_url: str) -> dict:
    """
    Downloads the 20 target sheets sequentially with a visible live progress bar
    so it never triggers Google's full-workbook xlsx export timeout.
    """
    sheet_id = extract_sheet_id(sheet_url)
    loaded_frames = []
    loaded_sheets = []
    missing_sheets = []

    progress_bar = st.sidebar.progress(0, text="ಗೂಗಲ್ ಶೀಟ್‌ಗೆ ಸಂಪರ್ಕಿಸಲಾಗುತ್ತಿದೆ...")
    total = len(TARGET_SHEETS)

    for idx, s_name in enumerate(TARGET_SHEETS, start=1):
        progress_bar.progress(
            idx / total,
            text=f"📥 ಲೋಡ್ ಆಗುತ್ತಿದೆ ({idx}/{total}): {s_name.strip()}",
        )
        parsed_df = fetch_single_sheet_with_retry(sheet_id, s_name)
        if parsed_df is not None:
            loaded_sheets.append(s_name.strip())
            if not parsed_df.empty:
                loaded_frames.append(parsed_df)
        else:
            missing_sheets.append(s_name.strip())

    progress_bar.empty()
    return finalize_and_save_snapshot(loaded_frames, loaded_sheets, missing_sheets)


def build_snapshot_from_uploaded_excel(file_bytes: bytes) -> dict:
    """Builds and saves the snapshot directly from an uploaded .xlsx file in 2 seconds."""
    excel_file = pd.ExcelFile(io.BytesIO(file_bytes), engine="openpyxl")
    available_map = {str(name).strip().lower(): name for name in excel_file.sheet_names}

    loaded_frames = []
    loaded_sheets = []
    missing_sheets = []

    for target in TARGET_SHEETS:
        norm_key = target.strip().lower()
        actual_name = available_map.get(norm_key)

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

    return finalize_and_save_snapshot(loaded_frames, loaded_sheets, missing_sheets)


@st.cache_data(show_spinner=False)
def load_saved_snapshot_from_disk() -> dict | None:
    if os.path.exists(SNAPSHOT_FILE):
        try:
            with open(SNAPSHOT_FILE, "rb") as f:
                data = pickle.load(f)
            if isinstance(data, dict) and "df" in data and not data["df"].empty:
                return data
        except Exception:
            pass
    return None


# ==============================================================================
# 5. MAIN APPLICATION UI
# ==============================================================================
def main():
    st.markdown(
        """
        <div class="main-header">
            <h1>📊 ಕಾಮಗಾರಿಗಳ ಪ್ರಗತಿ ವರದಿ</h1>
            <p>2026-27ನೇ ಸಾಲಿನ ಕಾಮಗಾರಿಗಳ ಕ್ರೋಢೀಕೃತ ಆರ್ಥಿಕ ಮತ್ತು ಭೌತಿಕ ಪ್ರಗತಿ ವರದಿ</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.header("⚙️ ಡೇಟಾ ನಿಯಂತ್ರಣ (Snapshot)")
        sheet_url_input = st.text_input(
            "Google Spreadsheet ಲಿಂಕ್",
            value=DEFAULT_SHEET_URL,
        )

        refresh_clicked = st.button(
            "🔄 ಹೊಸ ಡೇಟಾ ರಿಫ್ರೆಶ್ ಮಾಡಿ (Update Snapshot)",
            type="primary",
            use_container_width=True,
            help="ಗೂಗಲ್ ಶೀಟ್‌ನಿಂದ 20 ಶೀಟ್‌ಗಳನ್ನು ಒಂದೊಂದಾಗಿ ವೇಗವಾಗಿ ಲೋಡ್ ಮಾಡಿ ಹೊಸ ಸ್ನ್ಯಾಪ್‌ಶಾಟ್ ಸೇವ್ ಮಾಡುತ್ತದೆ.",
        )

        with st.expander("📤 ಪರ್ಯಾಯ: Excel (.xlsx) ಫೈಲ್ ಅಪ್‌ಲೋಡ್"):
            uploaded_xlsx = st.file_uploader(
                "ಗೂಗಲ್ ಶೀಟ್ ನಿಧಾನವಾಗಿದ್ದರೆ ನೇರವಾಗಿ .xlsx ಫೈಲ್ ಇಲ್ಲಿ ಹಾಕಿ (2 ಸೆಕೆಂಡಿನಲ್ಲಿ ಅಪ್‌ಡೇಟ್ ಆಗುತ್ತದೆ)",
                type=["xlsx"],
            )
            if uploaded_xlsx is not None:
                if st.button("✅ ಅಪ್‌ಲೋಡ್ ಮಾಡಿದ ಫೈಲ್‌ನಿಂದ ಸ್ನ್ಯಾಪ್‌ಶಾಟ್ ಸೇವ್ ಮಾಡಿ", use_container_width=True):
                    with st.spinner("ಎಕ್ಸೆಲ್ ಫೈಲ್ ಪ್ರಕ್ರಿಯೆಗೊಳಿಸಲಾಗುತ್ತಿದೆ..."):
                        snapshot = build_snapshot_from_uploaded_excel(uploaded_xlsx.read())
                        st.cache_data.clear()
                        st.success("✅ ಎಕ್ಸೆಲ್ ಫೈಲ್‌ನಿಂದ ಹೊಸ ಸ್ನ್ಯಾಪ್‌ಶಾಟ್ ಸೇವ್ ಆಗಿದೆ!")

        unit_mode = st.selectbox(
            "ಮೊತ್ತದ ಘಟಕ",
            options=["ಲಕ್ಷಗಳಲ್ಲಿ (Lakhs)", "ಕೋಟಿಗಳಲ್ಲಿ (Crores)"],
            index=0,
        )

    # 1. Load existing snapshot from disk first (instantaneous)
    snapshot = load_saved_snapshot_from_disk()

    # 2. If user clicked Refresh OR no snapshot exists on disk yet, fetch sheet-by-sheet
    if refresh_clicked or snapshot is None:
        try:
            new_snapshot = download_and_build_snapshot(sheet_url_input)
            if not new_snapshot["df"].empty:
                snapshot = new_snapshot
                st.cache_data.clear()
                if refresh_clicked:
                    st.sidebar.success("✅ ಹೊಸ ಸ್ನ್ಯಾಪ್‌ಶಾಟ್ ಯಶಸ್ವಿಯಾಗಿ ಸೇವ್ ಆಗಿದೆ!")
            elif snapshot is not None:
                st.sidebar.warning("⚠️ ಗೂಗಲ್ ಸರ್ವರ್ ನಿಧಾನವಾಗಿದೆ; ಹಿಂದಿನ ಸ್ನ್ಯಾಪ್‌ಶಾಟ್ ಡೇಟಾವನ್ನೇ ತೋರಿಸಲಾಗುತ್ತಿದೆ.")
        except Exception as e:
            if snapshot is not None:
                st.sidebar.warning(f"⚠️ ರಿಫ್ರೆಶ್ ಸಾಧ್ಯವಾಗಲಿಲ್ಲ ({e}). ಹಿಂದಿನ ಸ್ನ್ಯಾಪ್‌ಶಾಟ್ ಡೇಟಾ ಲಭ್ಯವಿದೆ.")
            else:
                st.error(f"ಡೇಟಾ ಲೋಡ್ ಮಾಡುವಲ್ಲಿ ದೋಷ: {e}")
                st.stop()

    if snapshot is None or snapshot["df"].empty:
        st.warning("ನಿಗದಿಪಡಿಸಿದ 8 ವಿಭಾಗಗಳಿಗೆ ಸಂಬಂಧಿಸಿದ ಯಾವುದೇ ಕಾಮಗಾರಿಗಳ ಮಾಹಿತಿ ಕಂಡುಬಂದಿಲ್ಲ.")
        st.stop()

    df = snapshot["df"]
    loaded_sheets = snapshot["loaded_sheets"]
    missing_sheets = snapshot["missing_sheets"]
    snap_time = snapshot.get("timestamp", "ಲಭ್ಯವಿಲ್ಲ")

    st.sidebar.caption(f"📸 **ಕೊನೆಯ ಸ್ನ್ಯಾಪ್‌ಶಾಟ್ ಸಮಯ:** {snap_time}")

    if os.path.exists(SNAPSHOT_FILE):
        with open(SNAPSHOT_FILE, "rb") as f:
            st.sidebar.download_button(
                label="💾 ಸ್ನ್ಯಾಪ್‌ಶಾಟ್ ಬ್ಯಾಕಪ್ ಡೌನ್‌ಲೋಡ್ (.pkl)",
                data=f.read(),
                file_name="snapshot_data.pkl",
                mime="application/octet-stream",
                use_container_width=True,
                help="ಈ snapshot_data.pkl ಫೈಲ್ ಅನ್ನು GitHub ನಲ್ಲಿ ಅಪ್‌ಲೋಡ್ ಮಾಡಿದರೆ ಸರ್ವರ್ ರೀಸ್ಟಾರ್ಟ್ ಆದರೂ ಡೇಟಾ ಶಾಶ್ವತವಾಗಿ ಇರುತ್ತದೆ.",
            )

    # ==========================================================================
    # 6. SIDEBAR FILTERS
    # ==========================================================================
    st.sidebar.markdown("---")
    st.sidebar.header("🔍 ಫಿಲ್ಟರ್‌ಗಳು")

    filtered_df = df.copy()

    def apply_multiselect_filter(data: pd.DataFrame, col_name: str, label: str) -> pd.DataFrame:
        options = sorted([x for x in data[col_name].dropna().unique() if x != "N/A"])
        if "N/A" in data[col_name].values:
            options.append("N/A")
        selected = st.sidebar.multiselect(label, options=options, default=[])
        if selected:
            return data[data[col_name].isin(selected)]
        return data

    filtered_df = apply_multiselect_filter(filtered_df, COL_SF, "1. S / F FILTER")
    filtered_df = apply_multiselect_filter(
        filtered_df, COL_PROGRESS, "2. PROGRESS STATUS FILTER (CP/CF)"
    )
    filtered_df = apply_multiselect_filter(filtered_df, COL_HEAD, "3. ಲೆಕ್ಕಶೀರ್ಷಿಕೆ FILTER")

    avail_divisions = [d for d in VALID_DIVISIONS if d in filtered_df[COL_DIVISION].unique()]
    sel_divisions = st.sidebar.multiselect(
        "4. ವಿಭಾಗ FILTER (ವಿಭಾಗದ ಹೆಸರು)", options=avail_divisions, default=[]
    )
    if sel_divisions:
        filtered_df = filtered_df[filtered_df[COL_DIVISION].isin(sel_divisions)]

    filtered_df = apply_multiselect_filter(filtered_df, COL_DISTRICT, "5. ಜಿಲ್ಲೆ FILTER")
    filtered_df = apply_multiselect_filter(filtered_df, COL_TALUK, "6. ತಾಲ್ಲೂಕು FILTER")
    filtered_df = apply_multiselect_filter(filtered_df, COL_CONSTITUENCY, "7. ಮತಕ್ಷೇತ್ರ FILTER")

    sel_ranges = st.sidebar.multiselect(
        "8. ಮೂಲ ಅಂದಾಜು ಮೊತ್ತ (RANGE) FILTER",
        options=list(ESTIMATE_RANGES.keys()),
        default=[],
    )
    if sel_ranges:
        range_mask = pd.Series(False, index=filtered_df.index)
        for r_label in sel_ranges:
            range_mask = range_mask | ESTIMATE_RANGES[r_label](filtered_df[COL_EST_AMT])
        filtered_df = filtered_df[range_mask]

    # ==========================================================================
    # 7. KPI METRIC CARDS
    # ==========================================================================
    is_crores = "ಕೋಟಿ" in unit_mode
    divisor = 100.0 if is_crores else 1.0
    unit_suffix = "ಕೋಟಿ (Cr)" if is_crores else "ಲಕ್ಷ (Lakhs)"

    total_works = len(filtered_df)
    sums = {col: filtered_df[col].sum() / divisor for col in FINANCIAL_COLUMNS}

    st.subheader(f"📌 ಪ್ರಮುಖ ಅಂಕಿಅಂಶಗಳು ({unit_suffix}ಗಳಲ್ಲಿ)")

    kpi_items = [
        ("ಒಟ್ಟು ಕಾಮಗಾರಿಗಳ ಸಂಖ್ಯೆ", f"{total_works:,}", "ಒಟ್ಟು ಕಾಮಗಾರಿಗಳು", True),
        ("ಒಟ್ಟು ಅಂದಾಜು ಮೊತ್ತ", f"₹ {sums[COL_EST_AMT]:,.2f}", f"ಮೂಲ ಅಂದಾಜು ಮೊತ್ತ ({unit_suffix})", False),
        ("ಗುತ್ತಿಗೆ ಮೊತ್ತ (ಜಿ.ಎಸ್.ಟಿ ಸೇರಿದಂತೆ)", f"₹ {sums[COL_TENDER_AMT]:,.2f}", f"ಗುತ್ತಿಗೆ ಮೊತ್ತ ({unit_suffix})", False),
        ("ಪರಿಷ್ಕೃತ ಅಂದಾಜು ಮೊತ್ತ (ಜಿ.ಎಸ್.ಟಿ ಸೇರಿದಂತೆ)", f"₹ {sums[COL_REV_EST_AMT]:,.2f}", f"ಪರಿಷ್ಕೃತ ಅಂದಾಜು ಮೊತ್ತ ({unit_suffix})", False),
        ("ಮಾರ್ಚ್ 2026 ವರೆಗಿನ ವೆಚ್ಚ", f"₹ {sums[COL_EXP_MAR26]:,.2f}", f"ಮಾರ್ಚ-2026 ವರೆಗಿನ ವೆಚ್ಚ ({unit_suffix})", False),
        ("2026-27ನೇ ಸಾಲಿನ ವೆಚ್ಚ", f"₹ {sums[COL_EXP_26_27]:,.2f}", f"2026-27ನೇ ಸಾಲಿನ ವೆಚ್ಚ ({unit_suffix})", False),
        ("ಒಟ್ಟಾರೆ ವೆಚ್ಚ", f"₹ {sums[COL_TOTAL_EXP]:,.2f}", f"ಒಟ್ಟಾರೆ ವೆಚ್ಚ ({unit_suffix})", False),
        ("ಬಾಕಿ ಬಿಲ್ಲಿನ ಮೊತ್ತ", f"₹ {sums[COL_PENDING_BILL]:,.2f}", f"ಬಾಕಿ ಬಿಲ್ಲಿನ ಮೊತ್ತ ({unit_suffix})", False),
        ("ಕಾಮಗಾರಿಯನ್ನು ಪುರ್ಣಗೊಳಿಸಲು ಬೇಕಾದ ಬಾಕಿ ಮೊತ್ತ", f"₹ {sums[COL_BAL_REQ]:,.2f}", f"ಕಾಮಗಾರಿಯನ್ನು ಪುರ್ಣಗೊಳಿಸಲು ಬೇಕಾದ ಬಾಕಿ ಮೊತ್ತ (17-25) ({unit_suffix})", False),
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
    # 8. TABS
    # ==========================================================================
    tab1, tab2, tab3, tab4 = st.tabs(
        [
            "📋 ವಿಭಾಗವಾರು ಸಾರಾಂಶ",
            "📈 ನಕ್ಷೆಗಳು",
            "📄 ಸಂಪೂರ್ಣ ಕಾಮಗಾರಿಗಳ ವಿವರ",
            "🗂️ ಮೂಲ ಶೀಟ್ ಸ್ಥಿತಿ",
        ]
    )

    with tab1:
        st.markdown(f"#### ವಿಭಾಗವಾರು ಗೋಷ್ಟ್ವಾರೆ ({unit_suffix}ಗಳಲ್ಲಿ)")
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
            label="📥 ಫಿಲ್ಟರ್ ಮಾಡಿದ ಡೇಟಾ ಡೌನ್‌ಲೋಡ್ ಮಾಡಿ (CSV)",
            data=csv_bytes,
            file_name="filtered_progress_report_2026_27.csv",
            mime="text/csv",
        )
        st.dataframe(filtered_df, use_container_width=True, height=500)

    with tab4:
        st.markdown("#### ಪರಿಗಣಿಸಲಾದ 20 ಶೀಟ್‌ಗಳ ಸ್ಥಿತಿ")
        sheet_counts = (
            df.groupby("SHEET_NAME")
            .size()
            .reset_index(name="ಪರಿಗಣಿಸಲಾದ ಕಾಮಗಾರಿಗಳ ಸಂಖ್ಯೆ (8 ವಿಭಾಗಗಳು)")
        )
        st.dataframe(sheet_counts, use_container_width=True, hide_index=True)
        if missing_sheets:
            st.warning(f"ಕಂಡುಬರದ ಶೀಟ್‌ಗಳು: {', '.join(missing_sheets)}")


if __name__ == "__main__":
    main()
