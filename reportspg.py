from datetime import date, datetime, timedelta
from io import BytesIO
import hashlib
import hmac
import json
import os
import re
import tempfile
import geopandas as gpd
import pandas as pd
import pydeck as pdk
import requests
from shapely.geometry import Point
import streamlit as st
from functools import lru_cache
from streamlit_js_eval import get_geolocation

try:
    from schedule_entry import (
        SCHEDULE_DETAIL_FILE,
        get_scheduled_personnel_for_team,
        get_scheduled_vehicles,
        render_schedule_entry,
    )
except ImportError:
    from schedule_entry import SCHEDULE_DETAIL_FILE, get_scheduled_vehicles, render_schedule_entry

    def get_scheduled_personnel_for_team(team_name, target_date=None, selected_kecamatan=""):
        return {
            "found": False,
            "supervisi": [],
            "spg_1": [],
            "spg_2": [],
            "spg_all": [],
            "vehicles": [],
            "records": [],
        }

from team_brand_sync import (
    match_brands_by_team_name,
    resolve_team_allowed_brands,
)

# ====================================================
# KONFIGURASI HALAMAN STREAMLIT
# ====================================================
st.set_page_config(
    page_title="Laporan Dirsell SPG",
    page_icon="📍",
    layout="centered",
    initial_sidebar_state="collapsed",
)

if str(st.query_params.get("page", "")).strip().lower() != "admin":
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"],
        [data-testid="stSidebarNav"],
        [data-testid="collapsedControl"] {
            display: none !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def get_team_theme(team_name: str) -> dict:
    """Mengembalikan konfigurasi palet warna dinamis berdasarkan nama team."""
    name = str(team_name or "").casefold()
    if "matcha" in name:
        return {
            "banner_bg": "linear-gradient(135deg, #090D0B 0%, #132A1E 100%)",
            "banner_border": "#22C55E",
            "badge_bg": "rgba(34, 197, 94, 0.18)",
            "badge_color": "#4ADE80",
            "btn_bg": "linear-gradient(135deg, #16A34A 0%, #052E16 100%)",
            "btn_shadow": "0 4px 12px rgba(22, 163, 74, 0.30)",
            "addr_bg": "#ECFDF5",
            "addr_border": "#86EFAC",
            "addr_accent": "#16A34A",
            "addr_text": "#064E3B",
            "accent_hex": "#22C55E",
        }
    if "super" in name:
        return {
            "banner_bg": "linear-gradient(135deg, #7F1D1D 0%, #450A0A 100%)",
            "banner_border": "#F59E0B",
            "badge_bg": "rgba(245, 158, 11, 0.20)",
            "badge_color": "#FCD34D",
            "btn_bg": "linear-gradient(135deg, #DC2626 0%, #B45309 100%)",
            "btn_shadow": "0 4px 12px rgba(220, 38, 38, 0.30)",
            "addr_bg": "#FFFBEB",
            "addr_border": "#FDE68A",
            "addr_accent": "#D97706",
            "addr_text": "#78350F",
            "accent_hex": "#F59E0B",
        }
    if "aksara" in name or "akasar" in name:
        return {
            "banner_bg": "linear-gradient(135deg, #0F1115 0%, #27200E 100%)",
            "banner_border": "#EAB308",
            "badge_bg": "rgba(234, 179, 8, 0.20)",
            "badge_color": "#FACC15",
            "btn_bg": "linear-gradient(135deg, #18181B 0%, #CA8A04 100%)",
            "btn_shadow": "0 4px 12px rgba(202, 138, 4, 0.28)",
            "addr_bg": "#FEFCE8",
            "addr_border": "#FEF08A",
            "addr_accent": "#CA8A04",
            "addr_text": "#713F12",
            "accent_hex": "#EAB308",
        }
    if "apel" in name:
        return {
            "banner_bg": "linear-gradient(135deg, #9A3412 0%, #7F1D1D 100%)",
            "banner_border": "#EF4444",
            "badge_bg": "rgba(239, 68, 68, 0.20)",
            "badge_color": "#FCA5A5",
            "btn_bg": "linear-gradient(135deg, #EA580C 0%, #DC2626 100%)",
            "btn_shadow": "0 4px 12px rgba(234, 88, 12, 0.30)",
            "addr_bg": "#FFF7ED",
            "addr_border": "#FDBA74",
            "addr_accent": "#EA580C",
            "addr_text": "#7C2D12",
            "accent_hex": "#EF4444",
        }
    return {
        "banner_bg": "linear-gradient(135deg, #0F172A 0%, #1E293B 100%)",
        "banner_border": "#DC2626",
        "badge_bg": "rgba(56, 189, 248, 0.15)",
        "badge_color": "#38BDF8",
        "btn_bg": "linear-gradient(135deg, #DC2626 0%, #B91C1C 100%)",
        "btn_shadow": "0 4px 12px rgba(220, 38, 38, 0.25)",
        "addr_bg": "#EFF6FF",
        "addr_border": "#BFDBFE",
        "addr_accent": "#2563EB",
        "addr_text": "#1E3A8A",
        "accent_hex": "#DC2626",
    }


# ====================================================
# CUSTOM CSS UNTUK UI MODERN & MOBILE-FRIENDLY
# ====================================================
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', sans-serif;
    }

    /* Background Utama */
    .stApp {
        background-color: #F8FAFC;
        color: #1E293B;
    }

    /* Header Login */
    .login-header {
        background: linear-gradient(135deg, #DC2626 0%, #991B1B 100%);
        padding: 32px 24px;
        border-radius: 20px;
        color: white;
        text-align: center;
        box-shadow: 0 12px 28px -6px rgba(220, 38, 38, 0.35);
        margin-bottom: 24px;
        position: relative;
        overflow: hidden;
    }
    .login-header h1 {
        margin: 0;
        font-size: 1.65rem;
        font-weight: 800;
        letter-spacing: -0.02em;
    }
    .login-header p {
        margin: 6px 0 0 0;
        font-size: 0.9rem;
        color: #FEE2E2;
        font-weight: 500;
    }

    /* Styling Container / Card */
    .ui-card {
        background-color: #FFFFFF;
        padding: 22px;
        border-radius: 16px;
        border: 1px solid #E2E8F0;
        box-shadow: 0 4px 12px -2px rgba(15, 23, 42, 0.04);
        margin-bottom: 16px;
    }

    /* Form Styling */
    [data-testid="stForm"] {
        background-color: #FFFFFF;
        padding: 24px 20px;
        border-radius: 18px;
        border: 1px solid #E2E8F0;
        box-shadow: 0 8px 20px -4px rgba(15, 23, 42, 0.05);
    }

    /* Tombol Utama & Submit */
    [data-testid="stFormSubmitButton"] > button,
    div.stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #DC2626 0%, #B91C1C 100%) !important;
        color: #FFFFFF !important;
        font-weight: 700 !important;
        font-size: 0.95rem !important;
        padding: 0.65rem 1.2rem !important;
        border-radius: 12px !important;
        border: none !important;
        box-shadow: 0 4px 12px rgba(220, 38, 38, 0.25) !important;
        transition: all 0.2s ease !important;
    }
    [data-testid="stFormSubmitButton"] > button:hover,
    div.stButton > button[kind="primary"]:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 16px rgba(220, 38, 38, 0.35) !important;
    }

    /* Tombol Sekunder */
    div.stButton > button[kind="secondary"] {
        background-color: #FFFFFF !important;
        color: #334155 !important;
        font-weight: 600 !important;
        border: 1px solid #CBD5E1 !important;
        border-radius: 12px !important;
        padding: 0.6rem 1rem !important;
        transition: all 0.2s ease !important;
    }
    div.stButton > button[kind="secondary"]:hover {
        border-color: #94A3B8 !important;
        background-color: #F1F5F9 !important;
    }

    /* Input Fields */
    .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] > div {
        border-radius: 10px !important;
        border-color: #CBD5E1 !important;
    }

    /* User Banner setelah Login */
    .user-banner {
        background: linear-gradient(135deg, #0F172A 0%, #1E293B 100%);
        color: #F8FAFC;
        padding: 18px 20px;
        border-radius: 16px;
        margin-bottom: 16px;
        box-shadow: 0 8px 20px -4px rgba(15, 23, 42, 0.2);
        border-left: 5px solid #DC2626;
    }
    .user-banner-title {
        font-size: 1.1rem;
        font-weight: 700;
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 6px;
    }
    .badge-mode {
        background-color: rgba(56, 189, 248, 0.15);
        color: #38BDF8;
        padding: 3px 10px;
        border-radius: 999px;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .user-banner-sub {
        font-size: 0.85rem;
        color: #CBD5E1;
    }

    /* KPI Dashboard Card */
    .dashboard-card {
        background-color: #FFFFFF;
        border: 1px solid #E2E8F0;
        padding: 18px;
        border-radius: 16px;
        box-shadow: 0 4px 10px -2px rgba(15, 23, 42, 0.04);
        margin-bottom: 12px;
        min-height: 138px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        transition: transform 0.2s ease;
    }
    .dashboard-card:hover {
        transform: translateY(-2px);
        border-color: #CBD5E1;
    }
    .card-value {
        font-size: 1.75rem;
        font-weight: 800;
        color: #0F172A;
        line-height: 1.15;
    }
    .card-value-green {
        font-size: 1.75rem;
        font-weight: 800;
        color: #16A34A;
        line-height: 1.15;
    }
    .card-subtext {
        font-size: 0.8rem;
        color: #64748B;
        margin-top: 4px;
    }
    .card-label {
        font-size: 0.88rem;
        color: #475569;
        font-weight: 600;
        margin-top: 8px;
    }

    /* Progress Bar */
    .progress-bar-container {
        width: 100%;
        background-color: #E2E8F0;
        border-radius: 999px;
        height: 8px;
        margin: 10px 0 4px 0;
        overflow: hidden;
    }
    .progress-bar-fill {
        height: 100%;
        background: linear-gradient(90deg, #16A34A 0%, #22C55E 100%);
        border-radius: 999px;
    }

    /* Box Alamat Warkop */
    .address-box {
        background-color: #EFF6FF;
        border: 1px solid #BFDBFE;
        border-left: 4px solid #2563EB;
        padding: 12px 16px;
        border-radius: 12px;
        font-size: 0.88rem;
        color: #1E3A8A;
        margin-top: 8px;
        margin-bottom: 16px;
    }

    /* Section Title Pill */
    .section-title {
        font-size: 1.05rem;
        font-weight: 700;
        color: #0F172A;
        margin: 18px 0 10px 0;
        display: flex;
        align-items: center;
        gap: 8px;
    }

    .footer-note {
        text-align: center;
        font-size: 0.78rem;
        color: #94A3B8;
        margin-top: 24px;
        padding-bottom: 16px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def apply_team_theme_css(team_name: str):
    """Menerapkan gaya CSS tema warna dinamis pada halaman User (SPG & Supervisi)."""
    t = get_team_theme(team_name)
    st.markdown(
        f"""
        <style>
        .user-banner {{
            background: {t["banner_bg"]} !important;
            border-left: 5px solid {t["banner_border"]} !important;
        }}
        .badge-mode {{
            background-color: {t["badge_bg"]} !important;
            color: {t["badge_color"]} !important;
        }}
        [data-testid="stFormSubmitButton"] > button,
        div.stButton > button[kind="primary"] {{
            background: {t["btn_bg"]} !important;
            box-shadow: {t["btn_shadow"]} !important;
        }}
        .address-box {{
            background-color: {t["addr_bg"]} !important;
            border: 1px solid {t["addr_border"]} !important;
            border-left: 4px solid {t["addr_accent"]} !important;
            color: {t["addr_text"]} !important;
        }}
        .section-title {{
            border-left: 4px solid {t["accent_hex"]};
            padding-left: 10px;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# ====================================================
# DEFINISI FILE DATABASE LOKAL & KONFIGURASI GOOGLE SHEET
# ====================================================
WEB_APP_URL = "https://script.google.com/macros/s/AKfycbzk6tqiNonaArNjJt7X0IIhja_D7elgGLkNPE90xmDtvdHwNeq4VhZJQfUU2OE_jiA/exec"

DB_FILE = "rekap_laporan_spg.csv"
DB_SUPERVISI_KONTAK_FILE = "rekap_kontak_supervisi.csv"
MASTER_BRAND_FILE = "master_brand_rokok.json"
MASTER_TARGET_FILE = "master_target_brand.json"
MASTER_HARGA_FILE = "master_harga_konsumen.json"
STOK_SUPERVISI_FILE = "stok_rokok_supervisi.json"
MASTER_AKSES_FILE = "master_akses_user.json"

DEFAULT_SUPERVISI_PIN = "1122"
DEFAULT_SPG_PIN = "2233"


def _file_mtime(path: str) -> float:
    return os.path.getmtime(path) if os.path.exists(path) else 0.0


@st.cache_data(show_spinner=False)
def _cached_read_csv(path: str, mtime: float) -> pd.DataFrame:
    return pd.read_csv(path)


@st.cache_data(show_spinner=False)
def _cached_read_excel(path: str, mtime: float) -> pd.DataFrame:
    df = pd.read_excel(path)
    df.columns = [str(c).strip() for c in df.columns]
    return df


@st.cache_data(show_spinner=False)
def _cached_read_json(path: str, mtime: float):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw_text = f.read().strip()
        if not raw_text:
            return None
        return json.loads(raw_text)
    except (OSError, json.JSONDecodeError):
        return None


@st.cache_data(show_spinner=False)
def _cached_read_json_no_mtime(path: str, _mtime: float = 0.0) -> dict | list | None:
    """Membaca file JSON secara aman dengan proteksi file kosong/rusak dan pelacakan mtime."""
    return _cached_read_json(path, _mtime)


def _read_json_safe(path: str) -> dict | list | None:
    return _cached_read_json_no_mtime(path, _file_mtime(path))


def _hash_pin(pin_plain: str) -> str:
    return hashlib.sha256(str(pin_plain or "").strip().encode("utf-8")).hexdigest()


def load_master_akses() -> dict:
    """Memuat pengaturan PIN/akses per peran & per nama personil."""
    data = _read_json_safe(MASTER_AKSES_FILE)
    base = {
        "supervisi_default_pin": DEFAULT_SUPERVISI_PIN,
        "spg_default_pin": DEFAULT_SPG_PIN,
        "require_spg_pin": False,
        "supervisi_pins": {},
        "spg_pins": {},
    }
    if isinstance(data, dict):
        base["supervisi_default_pin"] = str(data.get("supervisi_default_pin") or DEFAULT_SUPERVISI_PIN).strip()
        base["spg_default_pin"] = str(data.get("spg_default_pin") or DEFAULT_SPG_PIN).strip()
        base["require_spg_pin"] = bool(data.get("require_spg_pin", False))
        if isinstance(data.get("supervisi_pins"), dict):
            base["supervisi_pins"] = {
                str(k).strip(): str(v).strip()
                for k, v in data["supervisi_pins"].items()
                if str(k).strip() and str(v).strip()
            }
        if isinstance(data.get("spg_pins"), dict):
            base["spg_pins"] = {
                str(k).strip(): str(v).strip()
                for k, v in data["spg_pins"].items()
                if str(k).strip() and str(v).strip()
            }
    return base


def save_master_akses(akses_cfg: dict) -> bool:
    payload = {
        "supervisi_default_pin": str(akses_cfg.get("supervisi_default_pin") or DEFAULT_SUPERVISI_PIN).strip(),
        "spg_default_pin": str(akses_cfg.get("spg_default_pin") or DEFAULT_SPG_PIN).strip(),
        "require_spg_pin": bool(akses_cfg.get("require_spg_pin", False)),
        "supervisi_pins": {
            str(k).strip(): str(v).strip()
            for k, v in (akses_cfg.get("supervisi_pins") or {}).items()
            if str(k).strip() and str(v).strip()
        },
        "spg_pins": {
            str(k).strip(): str(v).strip()
            for k, v in (akses_cfg.get("spg_pins") or {}).items()
            if str(k).strip() and str(v).strip()
        },
    }
    with open(MASTER_AKSES_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    st.cache_data.clear()
    return True


def verify_user_pin(role: str, person_name: str, entered_pin: str, akses_cfg: dict | None = None) -> bool:
    cfg = akses_cfg if isinstance(akses_cfg, dict) else load_master_akses()
    pin_in = str(entered_pin or "").strip()
    if not pin_in:
        return False

    role_norm = str(role or "").strip().casefold()
    p_key = str(person_name or "").strip().casefold()

    if role_norm == "supervisi":
        expected = cfg.get("supervisi_default_pin", DEFAULT_SUPERVISI_PIN)
        for k, v in cfg.get("supervisi_pins", {}).items():
            if str(k).strip().casefold() == p_key and str(v).strip():
                expected = str(v).strip()
                break
        return hmac.compare_digest(_hash_pin(pin_in), _hash_pin(expected))

    if role_norm == "spg":
        expected = cfg.get("spg_default_pin", DEFAULT_SPG_PIN)
        for k, v in cfg.get("spg_pins", {}).items():
            if str(k).strip().casefold() == p_key and str(v).strip():
                expected = str(v).strip()
                break
        return hmac.compare_digest(_hash_pin(pin_in), _hash_pin(expected))

    return False


def _stok_sup_key(tanggal_str: str, team_name: str, brand_name: str) -> str:
    return "|".join([
        str(tanggal_str or "").strip(),
        str(team_name or "").strip().casefold(),
        str(brand_name or "").strip().casefold(),
    ])


def load_stok_supervisi() -> dict:
    data = _read_json_safe(STOK_SUPERVISI_FILE)
    return data if isinstance(data, dict) else {}


def save_stok_supervisi(stok_map: dict) -> bool:
    cleaned = {}
    for k, v in (stok_map or {}).items():
        try:
            cleaned[str(k)] = max(0, int(float(v)))
        except (ValueError, TypeError):
            cleaned[str(k)] = 0
    with open(STOK_SUPERVISI_FILE, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=2)
    st.cache_data.clear()
    return True


def get_stok_awal_supervisi(tanggal_str: str, team_name: str, brand_name: str, stok_map: dict | None = None) -> int:
    smap = stok_map if isinstance(stok_map, dict) else load_stok_supervisi()
    key = _stok_sup_key(tanggal_str, team_name, brand_name)
    val = smap.get(key, 0)
    try:
        return max(0, int(float(val)))
    except (ValueError, TypeError):
        return 0


DEFAULT_HARGA_KONSUMEN = {
    "Black Matcha K12": 22000,
    "D.Super 12": 24000,
    "D.Super Kretek": 16000,
    "D.76 Apel Royal": 18000,
    "D.76 Apel": 16000,
    "Djarum 76 Aksara": 16000,
    "Black Matcha Siro": 23000,
    "Black Matcha Kuro": 23000,
}


def load_harga_konsumen() -> dict:
    data = _read_json_safe(MASTER_HARGA_FILE)
    if isinstance(data, dict) and data:
        cleaned = {}
        for k, v in data.items():
            label = str(k or "").strip()
            if label:
                try:
                    cleaned[label] = max(0, int(float(v)))
                except (ValueError, TypeError):
                    cleaned[label] = 0
        if cleaned:
            return cleaned
    return dict(DEFAULT_HARGA_KONSUMEN)


def save_harga_konsumen(harga_map: dict) -> bool:
    cleaned = {}
    for k, v in (harga_map or {}).items():
        label = str(k or "").strip()
        if label:
            try:
                cleaned[label] = max(0, int(float(v)))
            except (ValueError, TypeError):
                cleaned[label] = 0
    with open(MASTER_HARGA_FILE, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=2)
    st.cache_data.clear()
    return True


def get_harga_konsumen_brand(brand: str, harga_map: dict | None = None) -> int:
    hmap = harga_map if isinstance(harga_map, dict) else load_harga_konsumen()
    b_key = normalize_brand_key(brand)
    if not b_key:
        return 0
    for k, v in hmap.items():
        if normalize_brand_key(k) == b_key:
            try:
                return max(0, int(float(v)))
            except (ValueError, TypeError):
                return 0
    return 0


MASTER_LOKASI_FILE = "Master WarkopLKK.xlsx"
MASTER_SPG_FILE = "master_nama_spg.json"
MASTER_TEAM_BRAND_FILE = "master_team_brand.json"
MASTER_PLAT_FILE = "master_plat_kendaraan.json"
MASTER_TEAM_NAME_FILE = "master_nama_team.json"
JADWAL_SPG_FILE = "Jadwal SPG.xlsx"

EXPECTED_COLUMNS = [
    "Waktu",
    "Promotor",
    "Plat_Mobil",
    "Nama_SPG",
    "Kota_Kab",
    "Kecamatan",
    "Warkop_LKK",
    "Alamat_Warkop",
    "Brand_Rokok",
    "Nama_Konsumen",
    "Gender",
    "Range_Umur",
    "No_HP",
    "Instagram",
    "Jumlah_Bungkus",
    "Rokok_Asal_BUMO",
    "Latitude",
    "Longitude",
]

EXPECTED_SUPERVISI_COLUMNS = [
    "Waktu",
    "Promotor",
    "Plat_Mobil",
    "Kota_Kab",
    "Kecamatan",
    "Warkop_LKK",
    "Alamat_Warkop",
    "Jumlah_Kontak_Manual",
]

LOCKED_LKK_POINT_FILE = "titik_lkk_aktif_team.json"
WARKOP_VISIT_STATUS_FILE = "status_warkop_kunjungan.json"

VISIT_STATUS_WAJIB = "Wajib Kunjung"
VISIT_STATUS_TIDAK_WAJIB = "Opsional"
VISIT_STATUS_OPTIONS = [VISIT_STATUS_WAJIB, VISIT_STATUS_TIDAK_WAJIB]


def _warkop_status_key(kota: str, kecamatan: str, warkop: str) -> str:
    return "|".join([
        str(kota or "").strip().casefold(),
        str(kecamatan or "").strip().casefold(),
        str(warkop or "").strip().casefold(),
    ])


def load_warkop_visit_status_map() -> dict:
    data = _read_json_safe(WARKOP_VISIT_STATUS_FILE)
    return data if isinstance(data, dict) else {}


def save_warkop_visit_status_map(status_map: dict) -> bool:
    try:
        cleaned = {}
        for k, v in (status_map or {}).items():
            val = str(v or "").strip()
            if val in VISIT_STATUS_OPTIONS:
                cleaned[str(k)] = val
            elif "tidak" in val.casefold() or "opsional" in val.casefold():
                cleaned[str(k)] = VISIT_STATUS_TIDAK_WAJIB
            else:
                cleaned[str(k)] = VISIT_STATUS_WAJIB
        with open(WARKOP_VISIT_STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(cleaned, f, ensure_ascii=False, indent=2)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Gagal menyimpan status warkop wajib/tidak wajib: {e}")
        return False


def get_warkop_visit_status(kota: str, kecamatan: str, warkop: str, status_map: dict | None = None) -> str:
    smap = status_map if isinstance(status_map, dict) else load_warkop_visit_status_map()
    key = _warkop_status_key(kota, kecamatan, warkop)
    raw_val = smap.get(key)
    if raw_val in VISIT_STATUS_OPTIONS:
        return raw_val
    suffix = f"|{str(kecamatan or '').strip().casefold()}|{str(warkop or '').strip().casefold()}"
    for k, v in smap.items():
        if str(k).endswith(suffix) and v in VISIT_STATUS_OPTIONS:
            return v
    return VISIT_STATUS_TIDAK_WAJIB


def build_warkop_status_dataframe(df_lokasi: pd.DataFrame, status_map: dict | None = None) -> pd.DataFrame:
    smap = status_map if isinstance(status_map, dict) else load_warkop_visit_status_map()
    empty_cols = ["Kota", "Kecamatan", "Nama Warkop / LKK", "Alamat Warkop / LKK", "Status Kunjungan"]
    if df_lokasi is None or df_lokasi.empty:
        return pd.DataFrame(columns=empty_cols)

    c_kota = next((c for c in df_lokasi.columns if "kota" in str(c).lower()), None)
    c_kec = next((c for c in df_lokasi.columns if "kec" in str(c).lower() or "wilayah" in str(c).lower()), None)
    c_wrk = next((c for c in df_lokasi.columns if "warkop" in str(c).lower() or "lkk" in str(c).lower() or "nama" in str(c).lower()), None)
    c_alm = next((c for c in df_lokasi.columns if "alamat" in str(c).lower() or "address" in str(c).lower()), None)

    out = pd.DataFrame({
        "Kota": df_lokasi[c_kota].astype(str).str.strip().replace("", "Surabaya") if c_kota else "Surabaya",
        "Kecamatan": df_lokasi[c_kec].astype(str).str.strip() if c_kec else "",
        "Nama Warkop / LKK": df_lokasi[c_wrk].astype(str).str.strip() if c_wrk else "",
        "Alamat Warkop / LKK": (df_lokasi[c_alm].astype(str).str.strip().replace("", "-") if c_alm else "-"),
    })
    out = out[out["Nama Warkop / LKK"] != ""].reset_index(drop=True)

    out["Status Kunjungan"] = [
        get_warkop_visit_status(k, kc, w, smap)
        for k, kc, w in zip(out["Kota"], out["Kecamatan"], out["Nama Warkop / LKK"])
    ]
    return out[empty_cols]


def load_locked_lkk_points() -> dict:
    data = _read_json_safe(LOCKED_LKK_POINT_FILE)
    return data if isinstance(data, dict) else {}


def save_locked_lkk_point(team_name: str, point_info: dict) -> bool:
    today_str = (datetime.utcnow() + timedelta(hours=7)).strftime("%Y-%m-%d")
    all_locked = load_locked_lkk_points()
    key = str(team_name or "").strip().casefold()
    payload = dict(point_info)
    payload["status_kunjungan"] = str(payload.get("status_kunjungan") or VISIT_STATUS_WAJIB).strip()
    payload["tanggal"] = today_str
    payload["locked_at"] = (datetime.utcnow() + timedelta(hours=7)).strftime("%Y-%m-%d %H:%M:%S")
    all_locked[key] = payload
    try:
        with open(LOCKED_LKK_POINT_FILE, "w", encoding="utf-8") as f:
            json.dump(all_locked, f, ensure_ascii=False, indent=2)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Gagal menyimpan titik LKK aktif: {e}")
        return False


def clear_locked_lkk_point(team_name: str) -> bool:
    """Membuka kunci titik LKK aktif setelah Supervisi menyelesaikan kunjungan & menyimpan kontak konsumen."""
    all_locked = load_locked_lkk_points()
    key = str(team_name or "").strip().casefold()
    if key in all_locked:
        all_locked.pop(key, None)
        try:
            with open(LOCKED_LKK_POINT_FILE, "w", encoding="utf-8") as f:
                json.dump(all_locked, f, ensure_ascii=False, indent=2)
            st.cache_data.clear()
            return True
        except Exception:
            return False
    return True


def get_active_locked_lkk_point_today(team_name: str, fallback_kota: str = "") -> dict | None:
    """Mengambil titik LKK yang sudah di-save / di-lock oleh Supervisi untuk team hari ini (WIB)."""
    today_str = (datetime.utcnow() + timedelta(hours=7)).strftime("%Y-%m-%d")
    all_locked = load_locked_lkk_points()
    key = str(team_name or "").strip().casefold()
    entry = all_locked.get(key)
    if not isinstance(entry, dict):
        return None
    if str(entry.get("tanggal", "")).strip() != today_str:
        return None
    warkop = str(entry.get("warkop", "") or "").strip()
    if not warkop:
        return None
    kota = str(entry.get("kota", fallback_kota) or fallback_kota).strip()
    if fallback_kota and kota and kota.casefold() != str(fallback_kota).strip().casefold():
        return None
    kec = str(entry.get("kecamatan", "") or "").strip()
    status_kunjungan = str(entry.get("status_kunjungan") or "").strip()
    if status_kunjungan not in VISIT_STATUS_OPTIONS:
        status_kunjungan = get_warkop_visit_status(kota, kec, warkop)
    return {
        "kota": kota,
        "kecamatan": kec,
        "warkop": warkop,
        "alamat": str(entry.get("alamat", "-") or "-").strip() or "-",
        "status_kunjungan": status_kunjungan,
        "locked_at": str(entry.get("locked_at", "") or "").strip(),
    }


def get_saved_contact_warkops_on_date(
    team_name: str,
    target_date_str: str,
    df_sup: pd.DataFrame | None = None,
) -> set[tuple[str, str]]:
    """Mengambil himpunan (kecamatan_casefold, warkop_casefold) yang sudah disimpan datanya lewat Save Jumlah Kontak Konsumen pada tanggal tertentu."""
    if df_sup is None:
        df_sup = load_supervisi_database()
    if df_sup is None or df_sup.empty:
        return set()

    mask = (
        df_sup["Promotor"].astype(str).str.strip().str.casefold()
        == str(team_name or "").strip().casefold()
    ) & (
        df_sup["Waktu"].astype(str).str.startswith(str(target_date_str or "").strip())
    )
    saved_pairs = set()
    for _, row in df_sup[mask].iterrows():
        w_val = str(row.get("Warkop_LKK", "") or "").strip().casefold()
        kc_val = str(row.get("Kecamatan", "") or "").strip().casefold()
        if w_val:
            saved_pairs.add((kc_val, w_val))
    return saved_pairs


def df_to_sheet_rows(df: pd.DataFrame):
    if df is None:
        return []
    columns = [str(column) for column in df.columns]
    if df.empty:
        return [columns] if columns else []

    rows = []
    for row in df.itertuples(index=False, name=None):
        serialized_row = []
        for value in row:
            if pd.isna(value):
                serialized_row.append("")
            elif isinstance(value, (datetime, pd.Timestamp)):
                serialized_row.append(value.strftime("%Y-%m-%d %H:%M:%S"))
            elif isinstance(value, date):
                serialized_row.append(value.isoformat())
            else:
                serialized_row.append(str(value))
        rows.append(serialized_row)

    return [columns] + rows


def google_json_default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    item = getattr(value, "item", None)
    if callable(item):
        return item()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def sheet_rows_to_df(rows, expected_columns=None):
    if not rows:
        return pd.DataFrame(columns=expected_columns)

    columns = [str(column) for column in rows[0]]
    df = pd.DataFrame(rows[1:], columns=columns)
    if expected_columns is not None:
        for column in expected_columns:
            if column not in df.columns:
                df[column] = ""
        return df[expected_columns]
    return df


def post_google_sheet(payload):
    payload_json = json.dumps(payload, ensure_ascii=False, default=google_json_default)
    response = requests.post(
        WEB_APP_URL,
        data=payload_json,
        headers={"Content-Type": "application/json"},
        timeout=(10, 120),
    )
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise RuntimeError(
            f"Google Apps Script mengembalikan HTTP {response.status_code} "
            f"(Content-Type: {response.headers.get('Content-Type', 'tidak diketahui')})."
        ) from exc

    try:
        result = response.json()
    except ValueError as exc:
        raise RuntimeError(
            "Google Apps Script tidak mengembalikan JSON "
            f"(HTTP {response.status_code}, "
            f"Content-Type: {response.headers.get('Content-Type', 'tidak diketahui')}). "
            "Periksa URL Web App, akses deployment, dan handler doPost."
        ) from exc

    if not isinstance(result, dict):
        raise RuntimeError("Format respons Google Apps Script tidak valid.")
    return result


def load_supabase_backup_data():
    df_rekap = pd.read_csv(DB_FILE) if os.path.exists(DB_FILE) else pd.DataFrame(columns=EXPECTED_COLUMNS)
    df_sup = pd.read_csv(DB_SUPERVISI_KONTAK_FILE) if os.path.exists(DB_SUPERVISI_KONTAK_FILE) else pd.DataFrame(columns=EXPECTED_SUPERVISI_COLUMNS)
    df_jdw = pd.read_excel(JADWAL_SPG_FILE) if os.path.exists(JADWAL_SPG_FILE) else pd.DataFrame()
    df_wrk = pd.read_excel(MASTER_LOKASI_FILE) if os.path.exists(MASTER_LOKASI_FILE) else pd.DataFrame()

    def read_json_file(file_path):
        return _read_json_safe(file_path)

    return {
        "backup_version": 1,
        "datasets": {
            "rekap_laporan": df_to_sheet_rows(df_rekap),
            "rekap_supervisi": df_to_sheet_rows(df_sup),
            "jadwal_spg": df_to_sheet_rows(df_jdw),
            "master_warkop": df_to_sheet_rows(df_wrk),
        },
        "master_data": {
            "nama_spg": read_json_file(MASTER_SPG_FILE),
            "nama_team": read_json_file(MASTER_TEAM_NAME_FILE),
            "team_brand": read_json_file(MASTER_TEAM_BRAND_FILE),
            "brand_rokok": read_json_file(MASTER_BRAND_FILE),
            "target_brand": read_json_file(MASTER_TARGET_FILE),
            "harga_konsumen": read_json_file(MASTER_HARGA_FILE),
            "plat_kendaraan": read_json_file(MASTER_PLAT_FILE),
            "jadwal_detail": read_json_file(SCHEDULE_DETAIL_FILE),
            "akses_user": read_json_file(MASTER_AKSES_FILE),
            "status_warkop": read_json_file(WARKOP_VISIT_STATUS_FILE),
        },
    }


def get_supabase_config():
    try:
        supabase_url = st.secrets.get("SUPABASE_URL", os.environ.get("SUPABASE_URL"))
        supabase_key = st.secrets.get("SUPABASE_KEY", os.environ.get("SUPABASE_KEY"))
    except FileNotFoundError:
        supabase_url = os.environ.get("SUPABASE_URL")
        supabase_key = os.environ.get("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        raise RuntimeError(
            "Konfigurasi SUPABASE_URL dan SUPABASE_KEY belum tersedia di Streamlit secrets atau environment."
        )

    return supabase_url.rstrip("/"), supabase_key


def post_supabase_backup(snapshot):
    supabase_url, supabase_key = get_supabase_config()
    response = requests.post(
        f"{supabase_url}/rest/v1/app_backups",
        json={"data": snapshot},
        headers={
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        timeout=(10, 120),
    )
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise RuntimeError(
            f"Supabase mengembalikan HTTP {response.status_code}: {response.text[:500]}"
        ) from exc


def get_latest_supabase_backup():
    supabase_url, supabase_key = get_supabase_config()
    response = requests.get(
        f"{supabase_url}/rest/v1/app_backups",
        params={
            "select": "id,created_at,data",
            "order": "created_at.desc,id.desc",
            "limit": "1",
        },
        headers={
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
        },
        timeout=(10, 120),
    )
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise RuntimeError(
            f"Supabase mengembalikan HTTP {response.status_code}: {response.text[:500]}"
        ) from exc

    try:
        backups = response.json()
    except ValueError as exc:
        raise RuntimeError("Supabase tidak mengembalikan JSON yang valid.") from exc

    if not isinstance(backups, list):
        raise RuntimeError("Format respons backup Supabase tidak valid.")
    if not backups:
        raise RuntimeError("Belum ada backup yang tersimpan di Supabase.")
    if not isinstance(backups[0], dict) or not isinstance(backups[0].get("data"), dict):
        raise RuntimeError("Isi backup terbaru di Supabase tidak valid.")
    return backups[0]


def restore_supabase_backup(snapshot):
    if not isinstance(snapshot, dict) or snapshot.get("backup_version") != 1:
        raise RuntimeError("Versi atau format backup Supabase tidak didukung.")

    datasets = snapshot.get("datasets")
    master_data = snapshot.get("master_data")
    if not isinstance(datasets, dict) or not isinstance(master_data, dict):
        raise RuntimeError("Struktur data backup Supabase tidak lengkap.")

    dataset_specs = {
        "rekap_laporan": (DB_FILE, EXPECTED_COLUMNS, "csv"),
        "rekap_supervisi": (DB_SUPERVISI_KONTAK_FILE, EXPECTED_SUPERVISI_COLUMNS, "csv"),
        "jadwal_spg": (JADWAL_SPG_FILE, None, "excel"),
        "master_warkop": (MASTER_LOKASI_FILE, None, "excel"),
    }
    file_contents = {}
    for dataset_name, (file_path, expected_columns, file_type) in dataset_specs.items():
        rows = datasets.get(dataset_name)
        if not isinstance(rows, list):
            raise RuntimeError(f"Data `{dataset_name}` tidak ditemukan pada backup Supabase.")
        dataframe = sheet_rows_to_df(rows, expected_columns)
        if file_type == "csv":
            file_contents[file_path] = dataframe.to_csv(index=False).encode("utf-8")
        else:
            excel_buffer = BytesIO()
            dataframe.to_excel(excel_buffer, index=False)
            file_contents[file_path] = excel_buffer.getvalue()

    master_file_paths = {
        "nama_spg": MASTER_SPG_FILE,
        "nama_team": MASTER_TEAM_NAME_FILE,
        "team_brand": MASTER_TEAM_BRAND_FILE,
        "brand_rokok": MASTER_BRAND_FILE,
        "target_brand": MASTER_TARGET_FILE,
        "harga_konsumen": MASTER_HARGA_FILE,
        "plat_kendaraan": MASTER_PLAT_FILE,
        "jadwal_detail": SCHEDULE_DETAIL_FILE,
    }
    files_to_remove = []
    for master_name, file_path in master_file_paths.items():
        if master_name not in master_data:
            raise RuntimeError(f"Data master `{master_name}` tidak ditemukan pada backup Supabase.")
        master_value = master_data[master_name]
        if master_value is None:
            files_to_remove.append(file_path)
        else:
            file_contents[file_path] = json.dumps(
                master_value, ensure_ascii=False, indent=2
            ).encode("utf-8")

    if "akses_user" in master_data and master_data["akses_user"] is not None:
        file_contents[MASTER_AKSES_FILE] = json.dumps(
            master_data["akses_user"], ensure_ascii=False, indent=2
        ).encode("utf-8")

    if "status_warkop" in master_data and master_data["status_warkop"] is not None:
        file_contents[WARKOP_VISIT_STATUS_FILE] = json.dumps(
            master_data["status_warkop"], ensure_ascii=False, indent=2
        ).encode("utf-8")

    staged_files = {}
    try:
        for file_path, content in file_contents.items():
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=os.path.dirname(os.path.abspath(file_path)),
                prefix=f".{os.path.basename(file_path)}.",
                suffix=".tmp",
                delete=False,
            ) as staged_file:
                staged_file.write(content)
                staged_files[file_path] = staged_file.name

        for file_path, staged_path in staged_files.items():
            os.replace(staged_path, file_path)
        for file_path in files_to_remove:
            if os.path.exists(file_path):
                os.remove(file_path)
    finally:
        for staged_path in staged_files.values():
            if os.path.exists(staged_path):
                os.remove(staged_path)


def render_google_sheet_backup_controls():
    with st.expander("☁️ Backup & Load Data", expanded=False):
        st.caption("Backup data aplikasi ke Google Spreadsheet atau Supabase.")

        col_backup_gs, col_backup_supabase = st.columns(2)
        with col_backup_gs:
            btn_backup_gs = st.button(
                "⬆️ Backup ke Sheet",
                use_container_width=True,
                key="backup_google_sheet",
            )
        with col_backup_supabase:
            btn_backup_supabase = st.button(
                "⬆️ Backup ke Supabase",
                use_container_width=True,
                key="backup_supabase",
            )
        col_load_gs, col_load_supabase = st.columns(2)
        with col_load_gs:
            btn_load_gs = st.button(
                "⬇️ Load dari Sheet",
                use_container_width=True,
                key="load_google_sheet",
            )
        with col_load_supabase:
            btn_load_supabase = st.button(
                "⬇️ Load dari Supabase",
                use_container_width=True,
                key="load_supabase",
            )

        if btn_backup_gs:
            try:
                with st.spinner("Mem-backup data ke Google Sheet..."):
                    snapshot = load_supabase_backup_data()
                    ds = snapshot["datasets"]
                    payload = {
                        "action": "backup",
                        "rekap_laporan": ds["rekap_laporan"],
                        "rekap_supervisi": ds["rekap_supervisi"],
                        "jadwal_spg": ds["jadwal_spg"],
                        "master_warkop": ds["master_warkop"],
                    }
                    res_json = post_google_sheet(payload)
                    if res_json.get("status") == "success":
                        st.success("✅ " + res_json.get("message", "Backup berhasil!"))
                    else:
                        st.error("❌ " + res_json.get("message", "Gagal backup."))
            except Exception as e:
                st.error(f"Error backup: {e}")
        if btn_backup_supabase:
            try:
                with st.spinner("Mem-backup data ke Supabase..."):
                    snapshot = load_supabase_backup_data()
                    post_supabase_backup(snapshot)
                    st.success("✅ Backup berhasil disimpan ke Supabase.")
            except Exception as e:
                st.error(f"Error backup Supabase: {e}")

        if btn_load_supabase:
            try:
                with st.spinner("Memuat backup terbaru dari Supabase..."):
                    backup = get_latest_supabase_backup()
                    restore_supabase_backup(backup["data"])
                    st.cache_data.clear()
                    st.success(
                        f"✅ Backup Supabase {backup.get('created_at', '')} "
                        "berhasil dimuat. Data lokal telah diganti."
                    )
                    st.rerun()
            except Exception as e:
                st.error(f"Error load Supabase: {e}")

        if btn_load_gs:
            try:
                with st.spinner("Memuat data dari Google Sheet..."):
                    res_json = post_google_sheet({"action": "load"})
                    if res_json.get("status") == "success":
                        data_gs = res_json.get("data", {})

                        if "rekap_laporan" in data_gs and len(data_gs["rekap_laporan"]) > 0:
                            sheet_rows_to_df(data_gs["rekap_laporan"], EXPECTED_COLUMNS).to_csv(DB_FILE, index=False)
                        if "rekap_supervisi" in data_gs and len(data_gs["rekap_supervisi"]) > 0:
                            sheet_rows_to_df(data_gs["rekap_supervisi"], EXPECTED_SUPERVISI_COLUMNS).to_csv(DB_SUPERVISI_KONTAK_FILE, index=False)
                        if "jadwal_spg" in data_gs and len(data_gs["jadwal_spg"]) > 0:
                            sheet_rows_to_df(data_gs["jadwal_spg"]).to_excel(JADWAL_SPG_FILE, index=False)
                        if "master_warkop" in data_gs and len(data_gs["master_warkop"]) > 0:
                            sheet_rows_to_df(data_gs["master_warkop"]).to_excel(MASTER_LOKASI_FILE, index=False)

                        st.cache_data.clear()
                        st.success("✅ Data berhasil dimuat dari Google Sheet!")
                        st.rerun()
                    else:
                        st.error("❌ " + res_json.get("message", "Gagal load."))
            except Exception as e:
                st.error(f"Error load: {e}")


# ====================================================
# FUNGSI BANTUAN UMUM
# ====================================================
def normalize_text(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def get_custom_week_info(dt):
    if pd.isna(dt):
        return "-", "-"
    d = pd.to_datetime(dt).date()
    wd = d.weekday()

    if wd == 5:
        fri_date = d + timedelta(days=6)
    elif wd == 6:
        fri_date = d + timedelta(days=5)
    else:
        fri_date = d + timedelta(days=(4 - wd))

    _, iso_w, _ = fri_date.isocalendar()
    periode_label = f"Minggu ke-{iso_w}"
    return periode_label, iso_w


def add_custom_week_columns(df, date_col="Waktu_Dt"):
    if df.empty or date_col not in df.columns:
        df["Periode_Minggu"] = "-"
        return df
    periods = []
    for val in df[date_col]:
        p_label, _ = get_custom_week_info(val)
        periods.append(p_label)
    df["Periode_Minggu"] = periods
    return df


# ====================================================
# DATABASE TRANSAKSI & SUPERVISI
# ====================================================
@st.cache_data(show_spinner=False)
def _cached_load_db_transformed(path: str, mtime: float) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "Usia" in df.columns and "Range_Umur" not in df.columns:
        df = df.rename(columns={"Usia": "Range_Umur"})
    for col in EXPECTED_COLUMNS:
        if col not in df.columns:
            df[col] = "-"
    return df[EXPECTED_COLUMNS]


def load_database():
    if os.path.exists(DB_FILE):
        try:
            return _cached_load_db_transformed(DB_FILE, _file_mtime(DB_FILE)).copy()
        except Exception:
            return pd.DataFrame(columns=EXPECTED_COLUMNS)
    return pd.DataFrame(columns=EXPECTED_COLUMNS)


def save_database(df):
    df.to_csv(DB_FILE, index=False)


@st.cache_data(show_spinner=False)
def _cached_load_sup_transformed(path: str, mtime: float) -> pd.DataFrame:
    df = pd.read_csv(path)
    for col in EXPECTED_SUPERVISI_COLUMNS:
        if col not in df.columns:
            df[col] = "-"
    return df[EXPECTED_SUPERVISI_COLUMNS]


def load_supervisi_database():
    if os.path.exists(DB_SUPERVISI_KONTAK_FILE):
        try:
            return _cached_load_sup_transformed(
                DB_SUPERVISI_KONTAK_FILE,
                _file_mtime(DB_SUPERVISI_KONTAK_FILE),
            ).copy()
        except Exception:
            return pd.DataFrame(columns=EXPECTED_SUPERVISI_COLUMNS)
    return pd.DataFrame(columns=EXPECTED_SUPERVISI_COLUMNS)


def save_supervisi_database(df):
    df.to_csv(DB_SUPERVISI_KONTAK_FILE, index=False)


def get_latest_supervisi_point_today(
    team_name: str,
    fallback_kota: str = "",
    fallback_kec: str = "",
    df_sup: pd.DataFrame | None = None,
) -> dict | None:
    """Mengambil titik LKK terbaru yang sudah diinput & disimpan oleh Supervisi hari ini untuk team tersebut."""
    today_str = (datetime.utcnow() + timedelta(hours=7)).strftime("%Y-%m-%d")
    if df_sup is None:
        df_sup = load_supervisi_database()
    if df_sup is None or df_sup.empty:
        return None

    mask = (
        df_sup["Promotor"].astype(str).str.strip().str.casefold()
        == str(team_name or "").strip().casefold()
    ) & (
        df_sup["Waktu"].astype(str).str.startswith(today_str)
    )
    if fallback_kota:
        mask = mask & (
            df_sup["Kota_Kab"].astype(str).str.strip().str.casefold()
            == str(fallback_kota).strip().casefold()
        )

    df_today = df_sup[mask].copy()
    if df_today.empty:
        return None

    parsed = pd.to_datetime(df_today["Waktu"], errors="coerce")
    if parsed.notna().any():
        df_today = df_today.assign(_dt=parsed).sort_values("_dt", ascending=False)
    else:
        df_today = df_today.iloc[::-1]

    for _, row in df_today.iterrows():
        warkop = str(row.get("Warkop_LKK", "") or "").strip()
        if warkop:
            return {
                "kota": str(row.get("Kota_Kab", fallback_kota) or fallback_kota).strip(),
                "kecamatan": str(row.get("Kecamatan", fallback_kec) or fallback_kec).strip(),
                "warkop": warkop,
                "alamat": str(row.get("Alamat_Warkop", "-") or "-").strip() or "-",
                "kontak": int(pd.to_numeric(row.get("Jumlah_Kontak_Manual", 0), errors="coerce") or 0),
                "waktu": str(row.get("Waktu", "") or "").strip(),
            }
    return None


def get_supervisi_points_today(
    team_name: str,
    fallback_kota: str = "",
    fallback_kec: str = "",
    df_sup: pd.DataFrame | None = None,
) -> list[dict]:
    """Mengambil daftar titik LKK unik yang sudah diinput Supervisi hari ini (terbaru di atas)."""
    today_str = (datetime.utcnow() + timedelta(hours=7)).strftime("%Y-%m-%d")
    if df_sup is None:
        df_sup = load_supervisi_database()
    if df_sup is None or df_sup.empty:
        return []

    mask = (
        df_sup["Promotor"].astype(str).str.strip().str.casefold()
        == str(team_name or "").strip().casefold()
    ) & (
        df_sup["Waktu"].astype(str).str.startswith(today_str)
    )
    if fallback_kota:
        mask = mask & (
            df_sup["Kota_Kab"].astype(str).str.strip().str.casefold()
            == str(fallback_kota).strip().casefold()
        )

    df_today = df_sup[mask].copy()
    if df_today.empty:
        return []

    parsed = pd.to_datetime(df_today["Waktu"], errors="coerce")
    if parsed.notna().any():
        df_today = df_today.assign(_dt=parsed).sort_values("_dt", ascending=False)
    else:
        df_today = df_today.iloc[::-1]

    points = []
    seen = set()
    for _, row in df_today.iterrows():
        warkop = str(row.get("Warkop_LKK", "") or "").strip()
        if not warkop:
            continue
        kec = str(row.get("Kecamatan", fallback_kec) or fallback_kec).strip()
        key = (kec.casefold(), warkop.casefold())
        if key in seen:
            continue
        seen.add(key)
        points.append({
            "kota": str(row.get("Kota_Kab", fallback_kota) or fallback_kota).strip(),
            "kecamatan": kec,
            "warkop": warkop,
            "alamat": str(row.get("Alamat_Warkop", "-") or "-").strip() or "-",
            "kontak": int(pd.to_numeric(row.get("Jumlah_Kontak_Manual", 0), errors="coerce") or 0),
            "waktu": str(row.get("Waktu", "") or "").strip(),
        })
    return points


# ====================================================
# MASTER WILAYAH / GEOJSON (ON-DEMAND PER KECAMATAN)
# ====================================================
GEOJSON_INDEX_FILE = os.path.join("geojson_by_kecamatan", "_index.json")

KECAMATAN_BY_KOTA = {
    "Surabaya": [
        "Asem Rowo", "Benowo", "Bubutan", "Dukuh Pakis", "Genteng",
        "Karang Pilang", "Krembangan", "Lakarsantri", "Pabean Cantian",
        "Pakal", "Sambikerep", "Sawahan", "Sukomanunggal", "Tandes",
        "Tegalsari", "Wiyung",
    ],
    "Gresik": [
        "Balongpanggang", "Benjeng", "Bungah", "Cerme", "Driyorejo",
        "Duduksampeyan", "Dukun", "Gresik", "Kebomas", "Kedamean",
        "Manyar", "Menganti", "Panceng", "Sangkapura", "Sidayu",
        "Tambak", "Ujungpangkah", "Wringinanom",
    ],
}


@st.cache_data(ttl=3600, show_spinner=False)
def _get_kecamatan_filepath_map() -> dict:
    """Cache mapping nama kecamatan (casefold) → filepath. Sekali baca index per jam."""
    result = {}
    if os.path.exists(GEOJSON_INDEX_FILE):
        try:
            idx = _cached_read_json(GEOJSON_INDEX_FILE, _file_mtime(GEOJSON_INDEX_FILE))
            if isinstance(idx, dict):
                for k, v in idx.items():
                    if isinstance(v, dict) and v.get("file"):
                        result[str(k).strip().casefold()] = v["file"]
        except Exception:
            pass
    return result


@st.cache_data(ttl=3600, show_spinner=False)
def load_geojson_index(mtime: float = 0.0) -> dict:
    if os.path.exists(GEOJSON_INDEX_FILE):
        try:
            raw_idx = _cached_read_json(GEOJSON_INDEX_FILE, _file_mtime(GEOJSON_INDEX_FILE))
            if isinstance(raw_idx, dict):
                return {
                    str(k).strip().casefold(): {"nm_kecamatan": str(k).strip(), **v}
                    for k, v in raw_idx.items()
                    if isinstance(v, dict)
                }
        except Exception:
            pass
    return {}


def _resolve_kecamatan_filepath(nm_kecamatan: str) -> str | None:
    if not nm_kecamatan:
        return None
    target = str(nm_kecamatan).strip()
    fmap = _get_kecamatan_filepath_map()
    cand = fmap.get(target.casefold())
    if cand:
        if os.path.exists(cand):
            return cand
        base_cand = os.path.join("geojson_by_kecamatan", os.path.basename(cand))
        if os.path.exists(base_cand):
            return base_cand
    slug = re.sub(r"[^a-z0-9]+", "_", target.lower()).strip("_")
    fallback_path = os.path.join("geojson_by_kecamatan", f"{slug}.geojson")
    if os.path.exists(fallback_path):
        return fallback_path
    return None


@st.cache_data(ttl=3600, max_entries=40, show_spinner=False)
def load_kecamatan_geojson(nm_kecamatan: str, mtime: float = 0.0) -> dict | None:
    filepath = _resolve_kecamatan_filepath(nm_kecamatan)
    if not filepath:
        return None
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Gagal memuat GeoJSON kecamatan '{nm_kecamatan}': {e}")
        return None


@st.cache_data(ttl=3600, max_entries=40, show_spinner=False)
def load_kecamatan_gdf(nm_kecamatan: str, mtime: float = 0.0):
    data = load_kecamatan_geojson(nm_kecamatan, mtime)
    if not data:
        return None
    try:
        gdf = gpd.GeoDataFrame.from_features(data)
        if gdf.crs is None:
            gdf.set_crs("EPSG:4326", inplace=True)
        return gdf
    except Exception as e:
        st.error(f"Gagal memproses geometri kecamatan '{nm_kecamatan}': {e}")
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def build_polygon_features(kecamatan_tuple: tuple) -> list:
    """Build features gabungan untuk PyDeck — cache by tuple kecamatan terpilih."""
    gresik_set = {k.casefold() for k in KECAMATAN_BY_KOTA["Gresik"]}
    features = []
    for kec_name in kecamatan_tuple:
        gj = load_kecamatan_geojson(kec_name)
        if not gj or not isinstance(gj.get("features"), list):
            continue
        is_gresik = kec_name.strip().casefold() in gresik_set
        fill_col = [16, 185, 129, 35] if is_gresik else [30, 144, 255, 35]
        line_col = [5, 150, 105, 210] if is_gresik else [37, 99, 235, 210]
        kota_label = "Gresik" if is_gresik else "Surabaya"
        for feat in gj["features"]:
            props = dict(feat.get("properties") or {})
            props.setdefault("Kota_Wilayah", kota_label)
            props["fill_color"] = fill_col
            props["line_color"] = line_col
            features.append({
                "type": "Feature",
                "properties": props,
                "geometry": feat.get("geometry"),
            })
    return features


def load_master_wilayah(kota, kecamatan_list=None):
    k_norm = str(kota or "").strip().casefold()
    if k_norm == "surabaya":
        all_kec = KECAMATAN_BY_KOTA["Surabaya"]
    elif k_norm == "gresik":
        all_kec = KECAMATAN_BY_KOTA["Gresik"]
    else:
        return None

    target_kec = (
        [str(k).strip() for k in kecamatan_list if str(k).strip()]
        if kecamatan_list is not None
        else all_kec
    )
    gdfs = []
    for kec in target_kec:
        gdf_k = load_kecamatan_gdf(kec)
        if gdf_k is not None and not gdf_k.empty:
            gdf_copy = gdf_k.copy()
            if "nm_kecamatan" not in gdf_copy.columns:
                gdf_copy["nm_kecamatan"] = kec
            gdfs.append(gdf_copy)
    if not gdfs:
        return None
    combined = pd.concat(gdfs, ignore_index=True)
    return gpd.GeoDataFrame(combined, crs="EPSG:4326")


def get_geo_districts(kota: str) -> list[str]:
    """Mengambil daftar nama kecamatan secara ringan tanpa memuat seluruh poligon."""
    k_norm = str(kota or "").strip().casefold()
    if k_norm == "surabaya":
        return sorted(KECAMATAN_BY_KOTA["Surabaya"])
    if k_norm == "gresik":
        return sorted(KECAMATAN_BY_KOTA["Gresik"])
    idx = load_geojson_index(_file_mtime(GEOJSON_INDEX_FILE))
    return sorted(v["nm_kecamatan"] for v in idx.values())


def get_scheduled_slots_for_date(target_date: date | None = None) -> list[dict]:
    """Mengambil seluruh jadwal penugasan (Tanggal, Team, Kota, Kecamatan) dari Jadwal SPG.xlsx."""
    df_j = load_jadwal_spg()
    if df_j is None or df_j.empty:
        return []

    kota_col = next((c for c in df_j.columns if "kota" in str(c).lower()), None)
    kec_col = next((c for c in df_j.columns if "kecamatan" in str(c).lower()), None)
    if not kota_col or not kec_col:
        return []

    ref_date = target_date or (datetime.utcnow() + timedelta(hours=7)).date()
    date_cols = []
    for c in df_j.columns:
        if c in {kota_col, kec_col}:
            continue
        try:
            parsed_dt = pd.to_datetime(c).date()
            date_cols.append((c, parsed_dt))
        except Exception:
            continue

    if target_date is not None:
        date_cols = [(c, dt) for c, dt in date_cols if dt == ref_date]

    slots = []
    seen = set()
    for _, row in df_j.iterrows():
        kota_val = normalize_text(row.get(kota_col, "")) or "Surabaya"
        kec_val = normalize_text(row.get(kec_col, ""))
        if not kec_val:
            continue
        for c_name, dt_val in date_cols:
            team_val = normalize_text(row.get(c_name, ""))
            if not team_val or team_val.lower() in {"nan", "none", "-"}:
                continue
            key = (dt_val.isoformat(), team_val.casefold(), kota_val.casefold(), kec_val.casefold())
            if key in seen:
                continue
            seen.add(key)
            slots.append({
                "tanggal": dt_val,
                "tanggal_str": dt_val.strftime("%d %b %Y"),
                "team": team_val,
                "kota": kota_val,
                "kecamatan": kec_val,
            })

    slots.sort(key=lambda item: (item["tanggal"], item["team"].casefold(), item["kota"].casefold(), item["kecamatan"].casefold()))
    return slots


# ====================================================
# MASTER BRAND / TARGET / TEAM / PLAT / NAMA TEAM (CACHED)
# ====================================================
DEFAULT_BRANDS = [
    "D.Super 12",
    "D.Super Kretek",
    "D.76 Apel",
    "D.76 Apel Royal",
    "Black Matcha K12",
    "Djarum 76 Aksara",
    "Black Matcha Siro",
    "Black Matcha Kuro",
]
DEFAULT_SPGS = ["Nanda"]
DEFAULT_PLATS = ["L 1234 ABC"]


def load_master_team_names():
    default_teams = {f"Team SPG {i}": f"Team SPG {i}" for i in range(1, 21)}
    data = _read_json_safe(MASTER_TEAM_NAME_FILE)
    if not isinstance(data, dict):
        save_master_team_names(default_teams)
        return default_teams
    for i in range(1, 21):
        key = f"Team SPG {i}"
        if key not in data:
            data[key] = key
        else:
            data[key] = str(data[key]).strip()
    return data


def save_master_team_names(team_names_dict):
    active_names = [str(name).strip() for name in team_names_dict.values() if str(name).strip()]
    if not active_names:
        st.error("Minimal satu nama team harus diisi. Unggah jadwal SPG untuk mengatur nama team otomatis.")
        return False
    if len({name.casefold() for name in active_names}) != len(active_names):
        st.error("Nama team tidak boleh duplikat.")
        return False
    try:
        with open(MASTER_TEAM_NAME_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {
                    f"Team SPG {i}": str(team_names_dict.get(f"Team SPG {i}", "")).strip()
                    for i in range(1, 21)
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Gagal menyimpan master nama team: {e}")
        return False


def load_master_brands():
    data = _read_json_safe(MASTER_BRAND_FILE)
    return data if isinstance(data, list) else DEFAULT_BRANDS


def save_master_brands(brands):
    try:
        with open(MASTER_BRAND_FILE, "w", encoding="utf-8") as f:
            json.dump(brands, f, ensure_ascii=False, indent=2)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Gagal menyimpan file master_brand_rokok.json: {e}")
        return False


def load_master_team_brands():
    current_brands = load_master_brands()
    team_map = load_master_team_names()
    active_team_names = [team_map[f"Team SPG {i}"] for i in range(1, 21) if team_map[f"Team SPG {i}"]]
    default_teams = {
        team_name: match_brands_by_team_name(team_name, current_brands)
        for team_name in active_team_names
    }
    data = _read_json_safe(MASTER_TEAM_BRAND_FILE)
    if not isinstance(data, dict):
        save_master_team_brands(default_teams)
        return default_teams
    for i, t_name in enumerate(active_team_names, start=1):
        t_key = f"Team SPG {i}"
        if t_name not in data and t_key not in data:
            data[t_name] = match_brands_by_team_name(t_name, current_brands)
    return data


def save_master_team_brands(team_brands):
    try:
        cleaned_data = {
            str(team): [str(b).strip() for b in brands]
            for team, brands in team_brands.items()
        }
        with open(MASTER_TEAM_BRAND_FILE, "w", encoding="utf-8") as f:
            json.dump(cleaned_data, f, ensure_ascii=False, indent=2)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"❌ Gagal menyimpan ke `{MASTER_TEAM_BRAND_FILE}`: {e}")
        return False


def load_master_plat_kendaraan():
    data = _read_json_safe(MASTER_PLAT_FILE)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return list(data.values())
    return DEFAULT_PLATS


def save_master_plat_kendaraan(plat_list):
    with open(MASTER_PLAT_FILE, "w", encoding="utf-8") as f:
        json.dump(plat_list, f, ensure_ascii=False, indent=2)
    st.cache_data.clear()


def load_master_spgs():
    data = _read_json_safe(MASTER_SPG_FILE)
    return data if isinstance(data, list) else DEFAULT_SPGS


def save_master_spgs(spgs):
    with open(MASTER_SPG_FILE, "w", encoding="utf-8") as f:
        json.dump(spgs, f, ensure_ascii=False, indent=2)
    st.cache_data.clear()


def load_master_lokasi_excel():
    if os.path.exists(MASTER_LOKASI_FILE):
        try:
            df_excel = _cached_read_excel(MASTER_LOKASI_FILE, _file_mtime(MASTER_LOKASI_FILE)).copy()
            return df_excel
        except Exception as e:
            st.error(f"Gagal membaca file Excel {MASTER_LOKASI_FILE}: {e}")
            return pd.DataFrame(columns=["Kota", "Kecamatan", "Nama Warkop / LKK", "Alamat Warkop / LKK"])
    else:
        return pd.DataFrame(
            columns=["Kota", "Kecamatan", "Nama Warkop / LKK", "Alamat Warkop / LKK"],
            data=[
                ["Surabaya", "Kecamatan Default", "Warkop Cak No", "-"],
                ["Surabaya", "Kecamatan Default", "Warkop Pitoe", "-"],
            ],
        )


def save_master_lokasi_excel(df_excel):
    try:
        df_excel.to_excel(MASTER_LOKASI_FILE, index=False)
        return True
    except Exception as e:
        st.error(f"Gagal menyimpan file Excel: {e}")
        return False


# ====================================================
# JADWAL SPG
# ====================================================
def load_jadwal_spg():
    if os.path.exists(JADWAL_SPG_FILE):
        try:
            df_jadwal = _cached_read_excel(JADWAL_SPG_FILE, _file_mtime(JADWAL_SPG_FILE)).copy()
            return df_jadwal
        except Exception as e:
            st.error(f"Gagal membaca file Jadwal SPG {JADWAL_SPG_FILE}: {e}")
            return pd.DataFrame()
    return pd.DataFrame()


def save_jadwal_spg(df):
    try:
        df.to_excel(JADWAL_SPG_FILE, index=False)
        return True
    except Exception as e:
        st.error(f"Gagal menyimpan file Jadwal SPG {JADWAL_SPG_FILE}: {e}")
        return False


def _is_same_team_reference(team_cell, team_name):
    team_cell = normalize_text(team_cell).lower()
    team_name = normalize_text(team_name).lower()
    if not team_cell or team_cell == "nan" or team_cell == "none":
        return False

    if team_cell == team_name:
        return True

    return False


def get_schedule_info_for_team(team_name):
    df_j = load_jadwal_spg()
    if df_j.empty:
        return False, "Tidak Ada Jadwal Team Tersebut Untuk Hari Ini", "Surabaya", [], pd.DataFrame()

    kota_col = next((c for c in df_j.columns if "kota" in str(c).lower()), None)
    kec_col = next((c for c in df_j.columns if "kecamatan" in str(c).lower()), None)

    if not kota_col or not kec_col:
        return False, "Tidak Ada Jadwal Team Tersebut Untuk Hari Ini", "Surabaya", [], pd.DataFrame()

    today_date = (datetime.utcnow() + timedelta(hours=7)).date()
    today_col = None
    for c in df_j.columns:
        try:
            parsed_dt = pd.to_datetime(c).date()
            if parsed_dt == today_date:
                today_col = c
                break
        except Exception:
            continue

    if not today_col:
        return False, "Tidak Ada Jadwal Team Tersebut Untuk Hari Ini", "Surabaya", [], pd.DataFrame()

    matched_rows = []
    for _, row in df_j.iterrows():
        val_cell = normalize_text(row.get(today_col, ""))
        if not val_cell or val_cell.lower() == "nan" or val_cell == "-":
            continue
        if _is_same_team_reference(val_cell, team_name):
            kota_val = normalize_text(row.get(kota_col, ""))
            kec_val = normalize_text(row.get(kec_col, ""))
            if kota_val or kec_val:
                matched_rows.append({"Kota": kota_val, "Kecamatan": kec_val})

    if not matched_rows:
        return False, "Tidak Ada Jadwal Team Tersebut Untuk Hari Ini", "Surabaya", [], pd.DataFrame()

    kec_list = sorted({r["Kecamatan"] for r in matched_rows if r["Kecamatan"]})
    kota_list = [r["Kota"] for r in matched_rows if r["Kota"]]
    found_kota = kota_list[0] if kota_list else "Surabaya"

    return True, "", found_kota, kec_list, pd.DataFrame(matched_rows)


# ====================================================
# TARGET BRAND PER SPG / TEAM
# ====================================================
DEFAULT_TARGET_RULES = {
    "Black Matcha K12": {"target_spg": 40, "target_team": 80, "group": "Black_Matcha"},
    "D.Super 12": {"target_spg": 40, "target_team": 80, "group": "D_Super"},
    "D.Super Kretek": {"target_spg": 40, "target_team": 80, "group": "D_Super"},
    "D.76 Apel Royal": {"target_spg": 40, "target_team": 80},
    "D.76 Apel": {"target_spg": 30, "target_team": 60},
    "Djarum 76 Aksara": {"target_spg": 30, "target_team": 60},
    "Black Matcha Siro": {"target_spg": 40, "target_team": 80, "group": "Black_Matcha"},
    "Black Matcha Kuro": {"target_spg": 40, "target_team": 80, "group": "Black_Matcha"},
}

TARGET_GROUP_LABELS = {
    "D_Super": "D. Super (Gabungan)",
    "Black_Matcha": "Black Matcha (Gabungan)",
    "Black_Siro_Kuro": "Black Matcha (Gabungan)",
}
TARGET_GROUP_OPTIONS = {
    "": "Tidak digabungkan",
    "D_Super": TARGET_GROUP_LABELS["D_Super"],
    "Black_Matcha": TARGET_GROUP_LABELS["Black_Matcha"],
}


def load_target_rules():
    data = _read_json_safe(MASTER_TARGET_FILE)
    return data if isinstance(data, dict) else dict(DEFAULT_TARGET_RULES)


def refresh_target_rules():
    global TARGET_RULES
    TARGET_RULES = load_target_rules()
    return TARGET_RULES


def save_target_rules(rules):
    global TARGET_RULES
    cleaned = rules if isinstance(rules, dict) else {}
    with open(MASTER_TARGET_FILE, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=2)
    st.cache_data.clear()
    TARGET_RULES = load_target_rules()


TARGET_RULES = load_target_rules()


def normalize_brand_key(brand):
    return "".join(str(brand).casefold().split())


def get_brand_target_rule(brand):
    brand_key = normalize_brand_key(brand)
    return next(
        (rule for rule_brand, rule in TARGET_RULES.items() if normalize_brand_key(rule_brand) == brand_key),
        {},
    )


def clean_brand_target_name(brand):
    group = get_brand_target_rule(brand).get("group")
    return TARGET_GROUP_LABELS.get(group, brand)


def get_group_target(group_name, target_key, default_val):
    rules_map = TARGET_RULES
    for brand, rule in rules_map.items():
        rule_group = rule.get("group")
        if rule_group == "Black_Siro_Kuro":
            rule_group = "Black_Matcha"
        if rule_group == group_name and target_key in rule:
            return rule[target_key]
    return default_val


def get_target_for_brand(brand, target_key, default_val):
    brand_str = str(brand or "").strip()
    if not brand_str:
        return default_val

    for group_key, label in TARGET_GROUP_LABELS.items():
        if brand_str.casefold() == label.casefold():
            canonical_group = "Black_Matcha" if group_key == "Black_Siro_Kuro" else group_key
            return get_group_target(canonical_group, target_key, default_val)

    rule = get_brand_target_rule(brand_str)
    group = rule.get("group")
    if group:
        canonical_group = "Black_Matcha" if group == "Black_Siro_Kuro" else group
        return get_group_target(canonical_group, target_key, default_val)
    return rule.get(target_key, default_val)


def style_status_target(val):
    if val == "Not Achieved":
        return "color: #DC2626; font-weight: 700;"
    elif val == "Achieved":
        return "color: #16A34A; font-weight: 700;"
    return ""


# ====================================================
# FUNGSI REPORT REKAPITULASI PENJUALAN & KONTROL STOK ROKOK
# ====================================================
def render_rekapitulasi_penjualan_report(team_name: str, target_date_str: str, allow_edit_stok: bool = True):
    """Menampilkan komponen laporan:
    1. Rekap Penjualan 2 SPG & Kontrol Stok Rokok
    2. Breakdown Penjualan Per Nama SPG Hari Ini
    3. Rekap Stok Dibawa, Terjual 2 SPG & Sisa Stok Per Merk
    4. Rekap Kunjungan Warkop / LKK Hari Ini (4A Wajib Kunjung Belum Dikunjungi & 4B Semua Warkop Dikunjungi)
    """
    df_all_db = load_database()
    df_all_sup_db = load_supervisi_database()
    harga_konsumen_map = load_harga_konsumen()
    stok_sup_map = load_stok_supervisi()
    status_map_report = load_warkop_visit_status_map()
    df_warkop_master = build_warkop_status_dataframe(load_master_lokasi_excel(), status_map_report)

    df_team_spg_today = pd.DataFrame()
    if not df_all_db.empty and "Promotor" in df_all_db.columns:
        df_team_spg_today = df_all_db[
            (df_all_db["Promotor"].astype(str).str.strip().str.casefold() == str(team_name).strip().casefold())
            & (df_all_db["Waktu"].astype(str).str.startswith(str(target_date_str).strip()))
        ].copy()

    if not df_team_spg_today.empty:
        df_team_spg_today["Jumlah_Bungkus"] = pd.to_numeric(
            df_team_spg_today["Jumlah_Bungkus"], errors="coerce"
        ).fillna(0)
        df_team_spg_today["Harga_Konsumen"] = df_team_spg_today["Brand_Rokok"].apply(
            lambda b: get_harga_konsumen_brand(b, harga_konsumen_map)
        )
        df_team_spg_today["Total_Uang_Rp"] = (
            df_team_spg_today["Jumlah_Bungkus"] * df_team_spg_today["Harga_Konsumen"]
        ).astype(int)

    df_team_sup_today = pd.DataFrame()
    if not df_all_sup_db.empty and "Promotor" in df_all_sup_db.columns:
        df_team_sup_today = df_all_sup_db[
            (df_all_sup_db["Promotor"].astype(str).str.strip().str.casefold() == str(team_name).strip().casefold())
            & (df_all_sup_db["Waktu"].astype(str).str.startswith(str(target_date_str).strip()))
        ].copy()
        if not df_team_sup_today.empty:
            df_team_sup_today["Jumlah_Kontak_Manual"] = pd.to_numeric(
                df_team_sup_today["Jumlah_Kontak_Manual"], errors="coerce"
            ).fillna(0).astype(int)

    all_brands_sup = load_master_brands()
    team_brands_sup_map = load_master_team_brands()
    team_names_sup_map = load_master_team_names()
    allowed_brands_sup = resolve_team_allowed_brands(
        team_name=team_name,
        all_brands=all_brands_sup,
        team_brands_map=team_brands_sup_map,
        team_names_map=team_names_sup_map,
        prefer_keyword_match=True,
    )
    if not allowed_brands_sup:
        allowed_brands_sup = all_brands_sup

    sold_brands_today = (
        df_team_spg_today["Brand_Rokok"].dropna().astype(str).str.strip().unique().tolist()
        if not df_team_spg_today.empty
        else []
    )
    brand_list_sup_stok = list(
        dict.fromkeys([b for b in allowed_brands_sup if b] + [b for b in sold_brands_today if b])
    )

    try:
        parsed_target_date = datetime.strptime(str(target_date_str).strip(), "%Y-%m-%d").date()
    except ValueError:
        parsed_target_date = (datetime.utcnow() + timedelta(hours=7)).date()

    locked_point_today = get_active_locked_lkk_point_today(team_name=team_name)
    sched_spg_today = get_scheduled_personnel_for_team(
        team_name,
        parsed_target_date,
        selected_kecamatan=locked_point_today["kecamatan"] if locked_point_today else "",
    ).get("spg_all", [])
    tx_spg_today = (
        df_team_spg_today["Nama_SPG"].dropna().astype(str).str.strip().unique().tolist()
        if not df_team_spg_today.empty
        else []
    )
    spg_2_list = list(dict.fromkeys([s for s in sched_spg_today if s] + [s for s in tx_spg_today if s]))
    if not spg_2_list:
        spg_2_list = ["SPG 1", "SPG 2"]

    total_bks_2spg_today = int(df_team_spg_today["Jumlah_Bungkus"].sum()) if not df_team_spg_today.empty else 0
    total_uang_2spg_today = int(df_team_spg_today["Total_Uang_Rp"].sum()) if not df_team_spg_today.empty else 0

    # --- 1. REKAP PENJUALAN 2 SPG & KONTROL STOK ROKOK ---
    st.markdown(f"### 1️⃣ Rekap Penjualan 2 SPG & Kontrol Stok Rokok ({team_name})")
    st.caption("Dashboard Monitoring")

    st.info(
        f"💵 **Jumlah Uang Terkumpul ({target_date_str}) — Penjualan 2 SPG:** "
        f"**Rp {total_uang_2spg_today:,}** ({total_bks_2spg_today:,} bungkus • "
        f"SPG: {', '.join(tx_spg_today) if tx_spg_today else 'Belum ada penjualan'})"
    )

    if allow_edit_stok:
        with st.form(f"form_input_stok_supervisi_{team_name}_{target_date_str}"):
            st.markdown("#### 📥 Input Jumlah Stok Rokok yang Dibawa (Per Merk)")
            st.caption(f"Tanggal: **{target_date_str}** • Team: **{team_name}**")
            stok_input_dict = {}
            if not brand_list_sup_stok:
                st.info("Belum ada daftar merk rokok untuk tim ini.")
            else:
                for idx_b, b_name in enumerate(brand_list_sup_stok):
                    existing_stok = get_stok_awal_supervisi(target_date_str, team_name, b_name, stok_sup_map)
                    col_sb1, col_sb2 = st.columns([0.6, 0.4])
                    with col_sb1:
                        st.markdown(f"**🚬 {b_name}**")
                        st.caption(f"Harga konsumen: Rp {get_harga_konsumen_brand(b_name, harga_konsumen_map):,} / bks")
                    with col_sb2:
                        stok_input_dict[b_name] = st.number_input(
                            f"Stok dibawa {b_name}",
                            min_value=0,
                            step=1,
                            value=int(existing_stok),
                            label_visibility="collapsed",
                            key=f"inp_stok_sup_{team_name}_{target_date_str}_{idx_b}_{b_name}",
                        )
            btn_save_stok_sup = st.form_submit_button("💾 Simpan Stok Dibawa Supervisi", type="primary", use_container_width=True)
            if btn_save_stok_sup:
                for b_name, qty_val in stok_input_dict.items():
                    k_stok = _stok_sup_key(target_date_str, team_name, b_name)
                    stok_sup_map[k_stok] = int(qty_val)
                if save_stok_supervisi(stok_sup_map):
                    st.success("✅ Jumlah stok rokok yang dibawa Supervisi berhasil disimpan!")
                    st.rerun()

    st.markdown("---")
    # --- 2. BREAKDOWN PENJUALAN PER NAMA SPG HARI INI ---
    st.markdown("### 2️⃣ Breakdown Penjualan Per Nama SPG Hari Ini")
    spg_cols = st.columns(min(2, len(spg_2_list)) if spg_2_list else 1)
    for idx_s, spg_nm in enumerate(spg_2_list[:2]):
        df_s = (
            df_team_spg_today[
                df_team_spg_today["Nama_SPG"].astype(str).str.strip().str.casefold() == spg_nm.strip().casefold()
            ]
            if not df_team_spg_today.empty
            else pd.DataFrame()
        )
        bks_s = int(df_s["Jumlah_Bungkus"].sum()) if not df_s.empty else 0
        uang_s = int(df_s["Total_Uang_Rp"].sum()) if not df_s.empty else 0
        trx_s = int(len(df_s)) if not df_s.empty else 0
        with spg_cols[idx_s % len(spg_cols)]:
            st.markdown(
                f"""
                <div class="dashboard-card">
                    <div>
                        <div style="font-size:0.85rem;font-weight:700;color:#334155;">👩‍💼 {spg_nm}</div>
                        <div class="card-value" style="margin-top:6px;">{bks_s:,} bks</div>
                        <div class="card-subtext">Rp {uang_s:,} • {trx_s} transaksi</div>
                    </div>
                    <div class="card-label">Penjualan SPG #{idx_s + 1} Hari Ini</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    if not df_team_spg_today.empty:
        df_breakdown_spg_merk = (
            df_team_spg_today.groupby(["Nama_SPG", "Brand_Rokok"])
            .agg(
                Transaksi=("Nama_Konsumen", "count"),
                Terjual_Bungkus=("Jumlah_Bungkus", "sum"),
                Total_Uang_Rp=("Total_Uang_Rp", "sum"),
            )
            .reset_index()
        )
        df_breakdown_spg_merk["Terjual_Bungkus"] = df_breakdown_spg_merk["Terjual_Bungkus"].astype(int)
        df_breakdown_spg_merk["Total_Uang_Rp"] = df_breakdown_spg_merk["Total_Uang_Rp"].astype(int)
        st.dataframe(df_breakdown_spg_merk, use_container_width=True, hide_index=True)
    else:
        st.info("Belum ada penjualan SPG tercatat pada tanggal ini.")

    st.markdown("---")
    # --- 3. REKAP STOK DIBAWA, TERJUAL 2 SPG & SISA STOK PER MERK ---
    st.markdown("### 3️⃣ Rekap Stok Dibawa, Terjual 2 SPG & Sisa Stok Per Merk")
    rows_stok_rekap = []
    for b_name in brand_list_sup_stok:
        stok_dibawa = get_stok_awal_supervisi(target_date_str, team_name, b_name, stok_sup_map)
        df_b = (
            df_team_spg_today[
                df_team_spg_today["Brand_Rokok"].astype(str).str.strip().str.casefold() == b_name.strip().casefold()
            ]
            if not df_team_spg_today.empty
            else pd.DataFrame()
        )
        terjual_spg_b = int(df_b["Jumlah_Bungkus"].sum()) if not df_b.empty else 0
        sisa_stok_b = stok_dibawa - terjual_spg_b
        uang_b = int(df_b["Total_Uang_Rp"].sum()) if not df_b.empty else 0

        r_detail = {"Merk_Rokok": b_name, "Stok_Dibawa": stok_dibawa}
        for spg_nm in spg_2_list[:2]:
            col_key = f"Terjual_{spg_nm}"
            if not df_b.empty:
                val_spg_b = int(
                    df_b[df_b["Nama_SPG"].astype(str).str.strip().str.casefold() == spg_nm.strip().casefold()][
                        "Jumlah_Bungkus"
                    ].sum()
                )
            else:
                val_spg_b = 0
            r_detail[col_key] = val_spg_b

        r_detail["Total_Terjual_SPG"] = terjual_spg_b
        r_detail["Sisa_Stok"] = sisa_stok_b
        r_detail["Uang_Merk_Rp"] = uang_b
        rows_stok_rekap.append(r_detail)

    if rows_stok_rekap:
        df_stok_rekap = pd.DataFrame(rows_stok_rekap)
        st.dataframe(df_stok_rekap, use_container_width=True, hide_index=True)

        total_stok_dibawa_all = int(df_stok_rekap["Stok_Dibawa"].sum())
        total_terjual_all = int(df_stok_rekap["Total_Terjual_SPG"].sum())
        total_sisa_stok_all = int(df_stok_rekap["Sisa_Stok"].sum())
        st.info(
            f"📦 **Ringkasan Stok ({target_date_str}):** Stok Dibawa: **{total_stok_dibawa_all:,} bks** • "
            f"Terjual 2 SPG: **{total_terjual_all:,} bks** • "
            f"**Sisa Stok: {total_sisa_stok_all:,} bks**"
        )
    else:
        st.info("Belum ada data stok atau merk untuk direkap.")

    st.markdown("---")
    # --- 4. REKAP KUNJUNGAN WARKOP / LKK HARI INI ---
    st.markdown(f"### 4️⃣ Rekap Kunjungan Warkop / LKK ({target_date_str})")

    # Kumpulkan data kunjungan dari log Supervisi dan transaksi SPG pada tanggal tersebut
    visited_records_map = {}

    if not df_team_sup_today.empty:
        for _, r_sup in df_team_sup_today.iterrows():
            w_nm = str(r_sup.get("Warkop_LKK", "") or "").strip()
            if not w_nm:
                continue
            kc_nm = str(r_sup.get("Kecamatan", "") or "").strip()
            kt_nm = str(r_sup.get("Kota_Kab", "Surabaya") or "Surabaya").strip()
            alm_nm = str(r_sup.get("Alamat_Warkop", "-") or "-").strip() or "-"
            wkt_nm = str(r_sup.get("Waktu", "") or "").strip()
            knt_val = int(pd.to_numeric(r_sup.get("Jumlah_Kontak_Manual", 0), errors="coerce") or 0)
            key_pair = (kc_nm.casefold(), w_nm.casefold())
            if key_pair not in visited_records_map:
                visited_records_map[key_pair] = {
                    "Kota": kt_nm,
                    "Kecamatan": kc_nm,
                    "Warkop_LKK": w_nm,
                    "Alamat_Warkop": alm_nm,
                    "Status_Kunjungan": get_warkop_visit_status(kt_nm, kc_nm, w_nm, status_map_report),
                    "Waktu_Kunjungan": wkt_nm,
                    "Jumlah_Kontak_Tim": knt_val,
                    "Jumlah_Konsumen_Beli": 0,
                    "Total_Bungkus_Terjual": 0,
                }
            else:
                visited_records_map[key_pair]["Jumlah_Kontak_Tim"] += knt_val
                if wkt_nm and (
                    not visited_records_map[key_pair]["Waktu_Kunjungan"]
                    or wkt_nm > visited_records_map[key_pair]["Waktu_Kunjungan"]
                ):
                    visited_records_map[key_pair]["Waktu_Kunjungan"] = wkt_nm

    if not df_team_spg_today.empty:
        for _, r_spg in df_team_spg_today.iterrows():
            w_nm = str(r_spg.get("Warkop_LKK", "") or "").strip()
            if not w_nm:
                continue
            kc_nm = str(r_spg.get("Kecamatan", "") or "").strip()
            kt_nm = str(r_spg.get("Kota_Kab", "Surabaya") or "Surabaya").strip()
            alm_nm = str(r_spg.get("Alamat_Warkop", "-") or "-").strip() or "-"
            wkt_nm = str(r_spg.get("Waktu", "") or "").strip()
            bks_val = int(pd.to_numeric(r_spg.get("Jumlah_Bungkus", 0), errors="coerce") or 0)
            key_pair = (kc_nm.casefold(), w_nm.casefold())
            if key_pair not in visited_records_map:
                visited_records_map[key_pair] = {
                    "Kota": kt_nm,
                    "Kecamatan": kc_nm,
                    "Warkop_LKK": w_nm,
                    "Alamat_Warkop": alm_nm,
                    "Status_Kunjungan": get_warkop_visit_status(kt_nm, kc_nm, w_nm, status_map_report),
                    "Waktu_Kunjungan": wkt_nm,
                    "Jumlah_Kontak_Tim": 0,
                    "Jumlah_Konsumen_Beli": 1,
                    "Total_Bungkus_Terjual": bks_val,
                }
            else:
                visited_records_map[key_pair]["Jumlah_Konsumen_Beli"] += 1
                visited_records_map[key_pair]["Total_Bungkus_Terjual"] += bks_val
                if wkt_nm and (
                    not visited_records_map[key_pair]["Waktu_Kunjungan"]
                    or wkt_nm > visited_records_map[key_pair]["Waktu_Kunjungan"]
                ):
                    visited_records_map[key_pair]["Waktu_Kunjungan"] = wkt_nm

    visited_keys_set = set(visited_records_map.keys())
    visited_warkop_names_only = {w for _, w in visited_keys_set}

    # Tentukan kecamatan yang relevan pada tanggal tersebut (jadwal tanggal tsb + warkop yang sudah dikunjungi)
    slots_for_date = get_scheduled_slots_for_date(parsed_target_date)
    active_kec_set = {
        str(s.get("kecamatan", "") or "").strip().casefold()
        for s in slots_for_date
        if str(s.get("team", "") or "").strip().casefold() == str(team_name or "").strip().casefold()
        and str(s.get("kecamatan", "") or "").strip()
    }
    for kc_k, _ in visited_keys_set:
        if kc_k:
            active_kec_set.add(kc_k)

    # --- 4A. DAFTAR WARKOP WAJIB KUNJUNG YANG BELUM DIKUNJUNGI ---
    st.markdown("#### 4A. Daftar Warkop Wajib Kunjung yang Belum Dikunjungi")
    unvisited_wajib_rows = []
    if not df_warkop_master.empty:
        wajib_df = df_warkop_master[df_warkop_master["Status Kunjungan"] == VISIT_STATUS_WAJIB].copy()
        if active_kec_set:
            wajib_df = wajib_df[
                wajib_df["Kecamatan"].astype(str).str.strip().str.casefold().isin(active_kec_set)
            ]
        for _, rw in wajib_df.iterrows():
            kt_w = str(rw.get("Kota", "") or "").strip()
            kc_w = str(rw.get("Kecamatan", "") or "").strip()
            nm_w = str(rw.get("Nama Warkop / LKK", "") or "").strip()
            alm_w = str(rw.get("Alamat Warkop / LKK", "-") or "-").strip() or "-"
            pair_w = (kc_w.casefold(), nm_w.casefold())
            if pair_w not in visited_keys_set and nm_w.casefold() not in visited_warkop_names_only:
                unvisited_wajib_rows.append({
                    "Kota": kt_w,
                    "Kecamatan": kc_w,
                    "Nama Warkop / LKK": nm_w,
                    "Alamat Warkop / LKK": alm_w,
                    "Status Kunjungan": VISIT_STATUS_WAJIB,
                })

    if unvisited_wajib_rows:
        df_4a = pd.DataFrame(unvisited_wajib_rows).sort_values(
            by=["Kecamatan", "Nama Warkop / LKK"]
        ).reset_index(drop=True)
        st.dataframe(df_4a, use_container_width=True, hide_index=True)
        st.warning(f"⚠️ Terdapat **{len(df_4a)}** warkop **Wajib Kunjung** yang belum dikunjungi pada {target_date_str}.")
    else:
        st.success(f"✅ Seluruh warkop **Wajib Kunjung** pada wilayah aktif ({target_date_str}) sudah dikunjungi!")

    # --- 4B. SEMUA WARKOP YANG DIKUNJUNGI HARI INI ---
    st.markdown("#### 4B. Semua Warkop yang Dikunjungi Hari Ini")
    if visited_records_map:
        df_4b = pd.DataFrame(list(visited_records_map.values())).sort_values(
            by=["Waktu_Kunjungan", "Kecamatan", "Warkop_LKK"],
            ascending=[False, True, True],
        ).reset_index(drop=True)
        st.dataframe(df_4b, use_container_width=True, hide_index=True)
        st.info(
            f"📍 **Ringkasan Kunjungan ({target_date_str}):** **{len(df_4b)}** warkop dikunjungi • "
            f"Total Kontak Tim: **{int(df_4b['Jumlah_Kontak_Tim'].sum()):,}** • "
            f"Konsumen Beli: **{int(df_4b['Jumlah_Konsumen_Beli'].sum()):,}** • "
            f"Terjual: **{int(df_4b['Total_Bungkus_Terjual'].sum()):,} bks**"
        )
    else:
        st.info(f"Belum ada warkop yang tercatat dikunjungi pada tanggal {target_date_str}.")


# ====================================================
# SESSION STATE
# ====================================================
def reset_session_on_user_change():
    st.session_state["logged_in"] = False
    st.session_state["user_spg"] = st.session_state.get("selected_team_login", "")
    st.session_state["nama_supervisi_aktif"] = ""
    st.session_state["spg_terjadwal_list"] = []
    st.session_state["sektor_terjadwal_login"] = ""
    st.session_state["spg_authenticated_name"] = ""
    st.session_state["show_titik_lkk_spg"] = False
    st.session_state["draft_konsumen"] = ""
    st.session_state["draft_nohp"] = ""
    st.session_state["draft_ig"] = ""
    st.session_state["draft_bungkus"] = 0
    st.session_state["draft_bumo"] = ""
    st.session_state["draft_brand"] = ""
    st.session_state["draft_gender"] = "L"
    st.session_state["draft_range_umur"] = ""
    st.session_state["spg_form_nonce"] = st.session_state.get("spg_form_nonce", 0) + 1
    st.session_state["sup_kontak_nonce"] = st.session_state.get("sup_kontak_nonce", 0) + 1


if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "user_spg" not in st.session_state:
    st.session_state["user_spg"] = ""
if "plat_mobil" not in st.session_state:
    st.session_state["plat_mobil"] = ""
if "kota_kab" not in st.session_state:
    st.session_state["kota_kab"] = ""
if "nama_supervisi_aktif" not in st.session_state:
    st.session_state["nama_supervisi_aktif"] = ""
if "spg_terjadwal_list" not in st.session_state:
    st.session_state["spg_terjadwal_list"] = []
if "sektor_terjadwal_login" not in st.session_state:
    st.session_state["sektor_terjadwal_login"] = ""
if "spg_authenticated_name" not in st.session_state:
    st.session_state["spg_authenticated_name"] = ""
if "show_titik_lkk_spg" not in st.session_state:
    st.session_state["show_titik_lkk_spg"] = False
if "login_mode" not in st.session_state:
    st.session_state["login_mode"] = "SPG"
if "admin_logged_in" not in st.session_state:
    st.session_state["admin_logged_in"] = False
if "admin_view" not in st.session_state:
    st.session_state["admin_view"] = "Dashboard"
if "draft_konsumen" not in st.session_state:
    st.session_state["draft_konsumen"] = ""
if "draft_nohp" not in st.session_state:
    st.session_state["draft_nohp"] = ""
if "draft_ig" not in st.session_state:
    st.session_state["draft_ig"] = ""
if "draft_bungkus" not in st.session_state:
    st.session_state["draft_bungkus"] = 0
if "draft_bumo" not in st.session_state:
    st.session_state["draft_bumo"] = ""
if "draft_brand" not in st.session_state:
    st.session_state["draft_brand"] = ""
if "draft_gender" not in st.session_state:
    st.session_state["draft_gender"] = "L"
if "draft_range_umur" not in st.session_state:
    st.session_state["draft_range_umur"] = ""
if "spg_form_nonce" not in st.session_state:
    st.session_state["spg_form_nonce"] = 0
if "sup_kontak_nonce" not in st.session_state:
    st.session_state["sup_kontak_nonce"] = 0

# ====================================================
# AKSES TERPISAH HALAMAN ADMIN VIA QUERY PARAM (?page=admin)
# ====================================================
_qp_page = str(st.query_params.get("page", "")).strip().lower()
_admin_portal_requested = (_qp_page == "admin")

if not _admin_portal_requested and st.session_state.get("admin_logged_in"):
    st.session_state["admin_logged_in"] = False

# ====================================================
# SIDEBAR ADMIN (HANYA TAMPIL SAAT ?page=admin AKTIF)
# ====================================================
if _admin_portal_requested and not st.session_state["logged_in"]:
    with st.sidebar:
        st.markdown("### 🔐 Panel Admin & Supervisor")
        st.caption("Pusat kontrol data lapangan dan konfigurasi master.")

        if not st.session_state["admin_logged_in"]:
            with st.form("form_admin_login"):
                pass_input = st.text_input("Kata Sandi Admin", type="password", placeholder="••••••••")
                btn_pass = st.form_submit_button("Masuk Dashboard Admin", use_container_width=True)

                if btn_pass:
                    if pass_input == "admin123":
                        st.session_state["admin_logged_in"] = True
                        st.session_state["admin_view"] = "Dashboard"
                        st.success("✅ Berhasil masuk sebagai Admin!")
                        st.rerun()
                    else:
                        st.error("❌ Password salah!")
        else:
            st.success("🟢 Mode Admin Aktif")

            st.markdown("##### 📊 Monitoring & Laporan")
            if st.button("🏠 Dashboard Utama", use_container_width=True, type="primary" if st.session_state["admin_view"] == "Dashboard" else "secondary"):
                st.session_state["admin_view"] = "Dashboard"
                st.rerun()
            if st.button("📅 Entry & Jadwal SPG", use_container_width=True, type="primary" if st.session_state["admin_view"] == "Master_Jadwal_Excel" else "secondary"):
                st.session_state["admin_view"] = "Master_Jadwal_Excel"
                st.rerun()
            if st.button("📈 Analitik Lapangan", use_container_width=True, type="primary" if st.session_state["admin_view"] == "Analitik" else "secondary"):
                st.session_state["admin_view"] = "Analitik"
                st.rerun()
            if st.button("🗺️ Peta Rute & Poligon", use_container_width=True, type="primary" if st.session_state["admin_view"] == "Peta_Rute" else "secondary"):
                st.session_state["admin_view"] = "Peta_Rute"
                st.rerun()

            st.markdown("##### ⚙️ Master Data")
            if st.button("🔑 PIN & Hak Akses User", use_container_width=True, type="primary" if st.session_state["admin_view"] == "Master_Akses" else "secondary"):
                st.session_state["admin_view"] = "Master_Akses"
                st.rerun()
            if st.button("🏷️ Master Nama Team", use_container_width=True):
                st.session_state["admin_view"] = "Master_Nama_Team"
                st.rerun()
            if st.button("👥 Team & Alokasi Brand", use_container_width=True):
                st.session_state["admin_view"] = "Master_Team"
                st.rerun()
            if st.button("👩‍💼 Master Nama SPG", use_container_width=True):
                st.session_state["admin_view"] = "Master_SPG"
                st.rerun()
            if st.button("🚬 Merek Rokok & Target", use_container_width=True):
                st.session_state["admin_view"] = "Master_Brand"
                st.rerun()
            if st.button("💰 Harga Rokok Konsumen", use_container_width=True):
                st.session_state["admin_view"] = "Master_Harga"
                st.rerun()
            if st.button("🚗 Plat Kendaraan", use_container_width=True):
                st.session_state["admin_view"] = "Master_Plat"
                st.rerun()
            if st.button("📍 Lokasi Warkop (Excel)", use_container_width=True):
                st.session_state["admin_view"] = "Master_Lokasi"
                st.rerun()

            st.markdown("---")
            if st.button("🔒 Keluar Mode Admin", use_container_width=True):
                st.session_state["admin_logged_in"] = False
                st.query_params.clear()
                st.rerun()

# ====================================================
# HALAMAN ADMIN
# ====================================================
if _admin_portal_requested and not st.session_state["logged_in"] and st.session_state["admin_logged_in"]:

    # --- MASTER PIN & HAK AKSES USER ---
    if st.session_state["admin_view"] == "Master_Akses":
        st.markdown("## 🔑 Pengaturan PIN & Hak Akses SPG / Supervisi")
        st.caption(
            "Atur PIN login Supervisi dan SPG agar setiap peran/orang tidak saling masuk ke akun atau mengubah data milik rekan lain."
        )
        akses_cfg = load_master_akses()
        spv_list_known = sorted(
            set(
                [s.get("supervisi", "") for s in get_scheduled_slots_for_date(None) if s.get("supervisi")]
                + list(akses_cfg.get("supervisi_pins", {}).keys())
            )
        )
        sched_detail_raw = _read_json_safe(SCHEDULE_DETAIL_FILE)
        if isinstance(sched_detail_raw, dict):
            for rec in sched_detail_raw.values():
                if isinstance(rec, dict):
                    spv_v = str(rec.get("supervisi") or "").strip()
                    if spv_v and spv_v not in spv_list_known:
                        spv_list_known.append(spv_v)
        spv_list_known = sorted(set(spv_list_known))
        spg_list_known = sorted(set(load_master_spgs() + list(akses_cfg.get("spg_pins", {}).keys())))

        with st.form("form_pengaturan_akses_pin"):
            col_pin1, col_pin2 = st.columns(2)
            with col_pin1:
                sup_def_pin = st.text_input(
                    "PIN Default Supervisi",
                    value=akses_cfg.get("supervisi_default_pin", DEFAULT_SUPERVISI_PIN),
                    key="cfg_sup_def_pin",
                )
            with col_pin2:
                spg_def_pin = st.text_input(
                    "PIN Default SPG",
                    value=akses_cfg.get("spg_default_pin", DEFAULT_SPG_PIN),
                    key="cfg_spg_def_pin",
                )

            req_spg_pin = st.checkbox(
                "Wajibkan PIN saat login SPG (mengunci nama SPG per sesi agar tidak saling mengganti nama)",
                value=bool(akses_cfg.get("require_spg_pin", False)),
                key="cfg_req_spg_pin",
            )

            st.markdown("---")
            st.markdown("#### 🧑‍💼 PIN Khusus Per Nama Supervisi (Opsional)")
            edited_sup_pins = {}
            for idx_sp, sp_nm in enumerate(spv_list_known):
                edited_sup_pins[sp_nm] = st.text_input(
                    f"PIN Supervisi — {sp_nm}",
                    value=akses_cfg.get("supervisi_pins", {}).get(sp_nm, ""),
                    placeholder=f"Kosongkan untuk pakai PIN default ({sup_def_pin})",
                    key=f"cfg_sup_pin_{idx_sp}_{sp_nm}",
                )

            st.markdown("---")
            st.markdown("#### 👩‍💼 PIN Khusus Per Nama SPG (Opsional)")
            edited_spg_pins = {}
            for idx_sg, sg_nm in enumerate(spg_list_known):
                edited_spg_pins[sg_nm] = st.text_input(
                    f"PIN SPG — {sg_nm}",
                    value=akses_cfg.get("spg_pins", {}).get(sg_nm, ""),
                    placeholder=f"Kosongkan untuk pakai PIN default ({spg_def_pin})",
                    key=f"cfg_spg_pin_{idx_sg}_{sg_nm}",
                )

            if st.form_submit_button("💾 Simpan Pengaturan PIN & Akses", type="primary", use_container_width=True):
                new_cfg = {
                    "supervisi_default_pin": sup_def_pin.strip() or DEFAULT_SUPERVISI_PIN,
                    "spg_default_pin": spg_def_pin.strip() or DEFAULT_SPG_PIN,
                    "require_spg_pin": req_spg_pin,
                    "supervisi_pins": {k: v.strip() for k, v in edited_sup_pins.items() if v.strip()},
                    "spg_pins": {k: v.strip() for k, v in edited_spg_pins.items() if v.strip()},
                }
                if save_master_akses(new_cfg):
                    st.success("✅ Pengaturan PIN & hak akses berhasil disimpan!")
                    st.rerun()

        st.markdown("---")
        if st.button("⬅️ Kembali ke Dashboard", key="btn_back_master_akses"):
            st.session_state["admin_view"] = "Dashboard"
            st.rerun()
        st.stop()

    # --- MASTER NAMA TEAM ---
    elif st.session_state["admin_view"] == "Master_Nama_Team":
        st.markdown("## 🏷️ Master Data: Nama Team (1 - 20)")
        st.caption("Ubah dan sesuaikan nama alias untuk Team SPG 1 sampai 20. Perubahan akan otomatis terhubung ke menu alokasi brand dan login.")

        team_names_map = load_master_team_names()

        with st.form("form_edit_nama_team"):
            st.markdown("#### Edit Nama Team")
            updated_names = {}

            for i in range(1, 21):
                key = f"Team SPG {i}"
                current_val = team_names_map.get(key, key)
                new_val = st.text_input(f"Nama untuk `{key}`", value=current_val, key=f"input_team_name_{i}")
                updated_names[key] = new_val.strip()

            btn_save_team_names = st.form_submit_button("💾 Simpan Perubahan Nama Team", type="primary")

            if btn_save_team_names:
                if save_master_team_names(updated_names):
                    st.success("✅ Perubahan nama team berhasil disimpan dan langsung terhubung ke seluruh sistem!")
                    st.rerun()

        st.markdown("---")
        if st.button("⬅️ Kembali ke Dashboard"):
            st.session_state["admin_view"] = "Dashboard"
            st.rerun()
        st.stop()

    # --- MASTER PLAT ---
    elif st.session_state["admin_view"] == "Master_Plat":
        st.markdown("## 🚗 Master Data: Plat Nomor Kendaraan Operasional")
        st.caption("Tambah atau hapus daftar plat nomor kendaraan operasional secara fleksibel.")

        plat_list = load_master_plat_kendaraan()

        with st.form("form_tambah_plat"):
            st.markdown("#### Tambah Plat Nomor Kendaraan Baru")
            new_plat_input = st.text_input("Plat Nomor Kendaraan", placeholder="Contoh: L 1234 ABC")
            btn_add_plat = st.form_submit_button("➕ Tambah Plat Kendaraan")

            if btn_add_plat:
                p_clean = new_plat_input.strip().upper()
                if p_clean:
                    if p_clean not in plat_list:
                        plat_list.append(p_clean)
                        save_master_plat_kendaraan(plat_list)
                        st.success(f"✅ Plat kendaraan '{p_clean}' berhasil ditambahkan!")
                        st.rerun()
                    else:
                        st.warning("Plat nomor kendaraan tersebut sudah ada dalam daftar.")
                else:
                    st.warning("Mohon masukkan nomor plat kendaraan.")

        st.markdown("---")
        st.markdown("#### 📋 Daftar Plat Kendaraan Terdaftar")
        for idx, p in enumerate(plat_list):
            col_p1, col_p2 = st.columns([0.8, 0.2])
            with col_p1:
                st.write(f"**{idx+1}.** `{p}`")
            with col_p2:
                if st.button("🗑️ Hapus", key=f"del_plat_{idx}"):
                    plat_list.pop(idx)
                    save_master_plat_kendaraan(plat_list)
                    st.success("Plat kendaraan berhasil dihapus!")
                    st.rerun()

        st.markdown("---")
        if st.button("⬅️ Kembali ke Dashboard"):
            st.session_state["admin_view"] = "Dashboard"
            st.rerun()
        st.stop()

    # --- MASTER TEAM & BRAND ---
    elif st.session_state["admin_view"] == "Master_Team":
        st.markdown("## 👥 Master Data: Team 1 - 20 & Alokasi Brand Rokok")
        st.caption("Atur pilihan merek rokok yang dapat dibawa oleh masing-masing Team SPG (Team 1 sampai 20).")

        all_available_brands = load_master_brands()
        team_brands_dict = load_master_team_brands()
        team_name_mapping = load_master_team_names()
        active_team_slots = [
            (f"Team SPG {i}", team_name_mapping[f"Team SPG {i}"])
            for i in range(1, 21)
            if team_name_mapping[f"Team SPG {i}"]
        ]
        team_options = [team_name for _, team_name in active_team_slots]
        if not team_options:
            st.info("Belum ada nama team. Unggah jadwal SPG untuk mengisi daftar team.")
            if st.button("⬅️ Kembali ke Dashboard", key="btn_back_master_team_empty"):
                st.session_state["admin_view"] = "Dashboard"
                st.rerun()
            st.stop()

        selected_team_config = st.selectbox(
            "Pilih Team SPG untuk Konfigurasi Brand",
            options=team_options,
            key="sb_pilih_team_master",
        )

        current_assigned_brands = team_brands_dict.get(selected_team_config, [])
        valid_defaults = [b for b in current_assigned_brands if b in all_available_brands]

        with st.form(key=f"form_config_{selected_team_config}"):
            st.markdown(f"#### Alokasi Merek untuk `{selected_team_config}`")
            selected_brands_input = st.multiselect(
                "Pilih Brand Rokok yang Diizinkan",
                options=all_available_brands,
                default=valid_defaults,
                key=f"ms_brands_{selected_team_config}",
            )
            btn_save_team_brand = st.form_submit_button("💾 Simpan Alokasi Brand Team")

            if btn_save_team_brand:
                team_brands_dict[selected_team_config] = selected_brands_input
                if save_master_team_brands(team_brands_dict):
                    st.success(f"✅ Alokasi brand rokok untuk **{selected_team_config}** berhasil disimpan!")
                    st.rerun()

        st.markdown("---")
        st.markdown("#### 📋 Ringkasan Alokasi Brand Seluruh Team (1 - 20)")
        fresh_team_brands = load_master_team_brands()
        summary_list = []
        for t_key, t_name in active_team_slots:
            b_list = fresh_team_brands.get(t_name, fresh_team_brands.get(t_key, []))
            summary_list.append({
                "Team": t_name,
                "Brand Diizinkan": ", ".join(b_list) if b_list else "(Belum ada brand)",
            })

        st.dataframe(pd.DataFrame(summary_list), use_container_width=True)

        st.markdown("---")
        if st.button("⬅️ Kembali ke Dashboard", key="btn_back_master_team"):
            st.session_state["admin_view"] = "Dashboard"
            st.rerun()
        st.stop()

    # --- MASTER SPG ---
    elif st.session_state["admin_view"] == "Master_SPG":
        st.markdown("## 👩‍💼 Master Data: Nama SPG")
        st.caption("Tambah, ubah, atau hapus daftar nama SPG aktif.")

        current_spgs = load_master_spgs()

        with st.form("form_tambah_spg"):
            new_spg_name = st.text_input("Nama SPG Baru", placeholder="Contoh: Siska")
            btn_add_spg = st.form_submit_button("➕ Tambah Nama SPG")
            if btn_add_spg:
                spg_clean = new_spg_name.strip()
                if spg_clean:
                    if spg_clean not in current_spgs:
                        current_spgs.append(spg_clean)
                        save_master_spgs(current_spgs)
                        st.success(f"✅ Nama SPG '{spg_clean}' berhasil ditambahkan!")
                        st.rerun()
                    else:
                        st.warning("Nama SPG tersebut sudah ada dalam daftar.")
                else:
                    st.warning("Mohon masukkan nama SPG.")

        st.markdown("---")
        st.markdown("#### 📋 Daftar Nama SPG Terdaftar")
        for idx, s in enumerate(current_spgs):
            col_s1, col_s2 = st.columns([0.8, 0.2])
            with col_s1:
                st.write(f"**{idx+1}.** {s}")
            with col_s2:
                if st.button("🗑️ Hapus", key=f"del_spg_{idx}"):
                    current_spgs.pop(idx)
                    save_master_spgs(current_spgs)
                    st.success("Nama SPG berhasil dihapus!")
                    st.rerun()

        st.markdown("---")
        if st.button("⬅️ Kembali ke Dashboard"):
            st.session_state["admin_view"] = "Dashboard"
            st.rerun()
        st.stop()

    # --- MASTER BRAND & TARGET ---
    elif st.session_state["admin_view"] == "Master_Brand":
        st.markdown("## 🚬 Master Data: Merek Rokok & Target")
        st.caption("Tambah atau hapus brand, dan ubah target per SPG maupun per Team.")

        current_brands = load_master_brands()
        target_rules_data = load_target_rules()

        with st.form("form_tambah_brand"):
            st.markdown("#### Tambah Merek Rokok & Target Baru")
            new_brand_name = st.text_input("Nama Merek Rokok Baru", placeholder="Contoh: Djarum Super Extra")
            t_spg = st.number_input("Target per SPG (Bungkus)", min_value=1, value=30, step=1)
            t_team = st.number_input("Target per Team (Bungkus)", min_value=1, value=60, step=1)
            new_group = st.selectbox(
                "Grup target gabungan",
                options=list(TARGET_GROUP_OPTIONS),
                format_func=lambda group: TARGET_GROUP_OPTIONS[group],
            )
            btn_add_brand = st.form_submit_button("➕ Tambah Merek Rokok")

            if btn_add_brand:
                b_clean = new_brand_name.strip()
                if b_clean:
                    if b_clean not in current_brands:
                        current_brands.append(b_clean)
                        save_master_brands(current_brands)
                        target_rules_data[b_clean] = {
                            "target_spg": int(t_spg),
                            "target_team": int(t_team),
                        }
                        if new_group:
                            target_rules_data[b_clean]["group"] = new_group
                        save_target_rules(target_rules_data)
                        refresh_target_rules()
                        st.success(f"✅ Merek rokok '{b_clean}' berhasil ditambahkan!")
                        st.rerun()
                    else:
                        st.warning("Merek rokok tersebut sudah ada dalam daftar.")
                else:
                    st.warning("Mohon masukkan nama merek rokok.")

        st.markdown("---")
        st.markdown("#### 📋 Daftar Merek Rokok & Pengaturan Target")

        for idx, b in enumerate(current_brands):
            rule = target_rules_data.get(b, {"target_spg": 25, "target_team": 50})
            with st.expander(f"🚬 {b} (SPG: {rule.get('target_spg', 25)} bks | Team: {rule.get('target_team', 50)} bks)"):
                with st.form(f"form_edit_target_{idx}"):
                    edit_tspg = st.number_input("Target per SPG (Bungkus)", min_value=1, value=int(rule.get("target_spg", 25)), key=f"tspg_{idx}")
                    edit_tteam = st.number_input("Target per Team (Bungkus)", min_value=1, value=int(rule.get("target_team", 50)), key=f"tteam_{idx}")
                    rule_group = rule.get("group")
                    if rule_group == "Black_Siro_Kuro":
                        rule_group = "Black_Matcha"
                    group_index = list(TARGET_GROUP_OPTIONS).index(
                        rule_group if rule_group in TARGET_GROUP_OPTIONS else ""
                    )
                    edit_group = st.selectbox(
                        "Grup target gabungan",
                        options=list(TARGET_GROUP_OPTIONS),
                        index=group_index,
                        format_func=lambda group: TARGET_GROUP_OPTIONS[group],
                        key=f"grp_{idx}",
                    )

                    col_ed1, col_ed2 = st.columns(2)
                    with col_ed1:
                        btn_save_edit = st.form_submit_button("💾 Simpan Perubahan Target")
                    with col_ed2:
                        btn_del_brand = st.form_submit_button("🗑️ Hapus Brand Ini")

                    if btn_save_edit:
                        target_rules_data[b] = {
                            "target_spg": int(edit_tspg),
                            "target_team": int(edit_tteam),
                        }
                        if edit_group:
                            target_rules_data[b]["group"] = edit_group
                        save_target_rules(target_rules_data)
                        refresh_target_rules()
                        st.success(f"✅ Target brand '{b}' berhasil diperbarui!")
                        st.rerun()

                    if btn_del_brand:
                        current_brands.remove(b)
                        save_master_brands(current_brands)
                        if b in target_rules_data:
                            del target_rules_data[b]
                            save_target_rules(target_rules_data)
                        refresh_target_rules()
                        st.success(f"🗑️ Brand '{b}' berhasil dihapus!")
                        st.rerun()

        st.markdown("---")
        if st.button("⬅️ Kembali ke Dashboard"):
            st.session_state["admin_view"] = "Dashboard"
            st.rerun()
        st.stop()

    # --- MASTER HARGA ROKOK KONSUMEN ---
    elif st.session_state["admin_view"] == "Master_Harga":
        st.markdown("## 💰 Master Data: Harga Rokok Konsumen")
        st.caption(
            "Tambah merk baru dan atur/edit harga jual konsumen per bungkus. "
            "Harga otomatis terhubung ke menu report untuk menghitung jumlah uang terkumpul dari penjualan 2 orang SPG hari itu."
        )

        current_brands = load_master_brands()
        harga_map = load_harga_konsumen()
        target_rules_data = load_target_rules()

        with st.form("form_tambah_merk_harga_konsumen"):
            st.markdown("#### ➕ Tambah Merk Baru & Harga Konsumen")
            col_hm1, col_hm2 = st.columns([0.6, 0.4])
            with col_hm1:
                new_merk_nama = st.text_input(
                    "Nama Merk Rokok Baru",
                    placeholder="Contoh: Djarum Black Tea 16",
                )
            with col_hm2:
                new_merk_harga = st.number_input(
                    "Harga Konsumen per Bungkus (Rp)",
                    min_value=0,
                    value=20000,
                    step=500,
                )
            col_ht1, col_ht2 = st.columns(2)
            with col_ht1:
                new_merk_tspg = st.number_input("Target per SPG (Bungkus)", min_value=1, value=30, step=1)
            with col_ht2:
                new_merk_tteam = st.number_input("Target per Team (Bungkus)", min_value=1, value=60, step=1)

            btn_add_merk_harga = st.form_submit_button("💾 Simpan Merk & Harga Baru", type="primary")
            if btn_add_merk_harga:
                b_clean = str(new_merk_nama or "").strip()
                if not b_clean:
                    st.warning("Mohon masukkan nama merk rokok baru.")
                else:
                    if not any(str(b).strip().casefold() == b_clean.casefold() for b in current_brands):
                        current_brands.append(b_clean)
                        save_master_brands(current_brands)
                        target_rules_data[b_clean] = {
                            "target_spg": int(new_merk_tspg),
                            "target_team": int(new_merk_tteam),
                        }
                        save_target_rules(target_rules_data)
                        refresh_target_rules()

                    harga_map[b_clean] = int(new_merk_harga)
                    if save_harga_konsumen(harga_map):
                        st.success(
                            f"✅ Merk **{b_clean}** dengan harga **Rp {int(new_merk_harga):,} / bks** berhasil disimpan!"
                        )
                        st.rerun()

        st.markdown("---")
        st.markdown("#### ✏️ Edit Harga Rokok Konsumen per Merk")

        all_merk_list = list(dict.fromkeys(
            [str(b).strip() for b in current_brands if str(b).strip()]
            + [str(k).strip() for k in harga_map.keys() if str(k).strip()]
        ))

        if not all_merk_list:
            st.info("Belum ada merk rokok terdaftar.")
        else:
            with st.form("form_edit_harga_konsumen"):
                edited_harga_dict = {}
                for idx, merk_item in enumerate(all_merk_list):
                    harga_saat_ini = get_harga_konsumen_brand(merk_item, harga_map)
                    col_m_info, col_m_input = st.columns([0.55, 0.45])
                    with col_m_info:
                        st.markdown(f"**🚬 {merk_item}**")
                        st.caption(f"Harga aktif: Rp {harga_saat_ini:,} / bungkus")
                    with col_m_input:
                        edited_harga_dict[merk_item] = st.number_input(
                            f"Harga {merk_item} (Rp)",
                            min_value=0,
                            value=int(harga_saat_ini),
                            step=500,
                            label_visibility="collapsed",
                            key=f"inp_harga_konsumen_{idx}_{merk_item}",
                        )

                btn_save_edit_harga = st.form_submit_button(
                    "💾 Simpan Perubahan Harga Konsumen",
                    type="primary",
                    use_container_width=True,
                )
                if btn_save_edit_harga:
                    if save_harga_konsumen(edited_harga_dict):
                        st.success("✅ Perubahan harga rokok konsumen berhasil disimpan!")
                        st.rerun()

        st.markdown("---")
        if st.button("⬅️ Kembali ke Dashboard"):
            st.session_state["admin_view"] = "Dashboard"
            st.rerun()
        st.stop()

    # --- MASTER LOKASI WARKOP (SELARAS DENGAN JADWAL SPG) ---
    elif st.session_state["admin_view"] == "Master_Lokasi":
        st.markdown("## 📍 Entry & Pengaturan Warkop Wajib / Tidak Wajib Kunjung")
        st.caption("Selaras dengan **Jadwal SPG**: pilih tanggal & jadwal aktif (Team — Kota / Sektor Kecamatan) untuk melihat daftar warkop yang bisa dikunjungi lalu tentukan mana yang **Wajib Kunjung** dan **Opsional**.")

        df_lokasi_excel = load_master_lokasi_excel()
        status_map_current = load_warkop_visit_status_map()
        df_warkop_view = build_warkop_status_dataframe(df_lokasi_excel, status_map_current)

        c_stat1, c_stat2, c_stat3 = st.columns(3)
        jml_wajib = int((df_warkop_view["Status Kunjungan"] == VISIT_STATUS_WAJIB).sum()) if not df_warkop_view.empty else 0
        jml_tidak_wajib = int((df_warkop_view["Status Kunjungan"] == VISIT_STATUS_TIDAK_WAJIB).sum()) if not df_warkop_view.empty else 0
        with c_stat1:
            st.metric("Total Titik Warkop / LKK", len(df_warkop_view))
        with c_stat2:
            st.metric("🔒 Wajib Kunjung", jml_wajib)
        with c_stat3:
            st.metric("🔓 Opsional", jml_tidak_wajib)

        tab_wrk_jadwal, tab_wrk_add, tab_wrk_manage, tab_wrk_excel = st.tabs(
            [
                "🗓️ Pengaturan per Jadwal SPG",
                "➕ Tambah Warkop Baru",
                "✏️ Kelola Warkop Aktif",
                "📥 Download / Upload Excel",
            ]
        )

        with tab_wrk_jadwal:
            st.markdown("#### Pilih Tanggal & Jadwal SPG Aktif")
            st.caption("Menampilkan jadwal SPG pada tanggal terpilih beserta daftar warkop pada wilayah/sektor kecamatan jadwal tersebut.")

            default_sched_date = (datetime.utcnow() + timedelta(hours=7)).date()
            selected_sched_date = st.date_input(
                "Tanggal Jadwal SPG",
                value=default_sched_date,
                key="wrk_sched_date",
            )

            sched_slots_today = get_scheduled_slots_for_date(selected_sched_date)
            all_sched_slots = get_scheduled_slots_for_date(None)

            if not sched_slots_today:
                st.warning(
                    f"Tidak ada jadwal SPG aktif pada tanggal **{selected_sched_date.strftime('%d %b %Y')}**. "
                    "Anda dapat memilih jadwal dari tanggal lain di bawah atau menambahkan jadwal pada menu **Entry & Jadwal SPG**."
                )
                active_slot_pool = all_sched_slots
            else:
                active_slot_pool = sched_slots_today

            if active_slot_pool:
                slot_labels = [
                    f"{s['tanggal_str']} — {s['team']} | Wilayah / Sektor: {s['kota']} — {s['kecamatan']}"
                    for s in active_slot_pool
                ]
                selected_slot_idx = st.selectbox(
                    "Jadwal SPG Aktif",
                    options=range(len(slot_labels)),
                    format_func=lambda i: slot_labels[i],
                    key="wrk_sched_slot_select",
                )
                chosen_slot = active_slot_pool[selected_slot_idx]
                slot_kota = chosen_slot["kota"]
                slot_kec = chosen_slot["kecamatan"]
                slot_team = chosen_slot["team"]
                slot_tgl_str = chosen_slot["tanggal_str"]

                st.info(
                    f"📅 **Jadwal Terpilih:** **{slot_tgl_str}** • Team: **{slot_team}** • "
                    f"Wilayah / Sektor: **{slot_kota} — {slot_kec}**"
                )

                sub_wrk_df = df_warkop_view[
                    (df_warkop_view["Kota"].astype(str).str.strip().str.casefold() == slot_kota.strip().casefold())
                    & (df_warkop_view["Kecamatan"].astype(str).str.strip().str.casefold() == slot_kec.strip().casefold())
                ].copy()

                all_wrk_names = sub_wrk_df["Nama Warkop / LKK"].tolist() if not sub_wrk_df.empty else []
                default_wajib_names = [
                    r["Nama Warkop / LKK"]
                    for _, r in sub_wrk_df.iterrows()
                    if r["Status Kunjungan"] == VISIT_STATUS_WAJIB
                ] if not sub_wrk_df.empty else []

                if not all_wrk_names:
                    st.warning(
                        f"Belum ada daftar warkop terdaftar untuk wilayah/sektor **{slot_kota} — {slot_kec}**. "
                        "Tambahkan warkop baru pada tab **Tambah Warkop Baru**."
                    )
                else:
                    with st.form("form_batch_status_warkop"):
                        st.markdown(f"#### List Warkop yang Bisa Dikunjungi ({slot_kota} — {slot_kec})")
                        st.caption(
                            f"Tersedia **{len(all_wrk_names)}** warkop pada sektor **{slot_kec}**. "
                            "Centang satu per satu warkop yang **Wajib Kunjung**; yang tidak dicentang otomatis menjadi **Opsional**."
                        )
                        checked_wajib = []
                        for idx, w in enumerate(all_wrk_names):
                            is_checked = st.checkbox(
                                w,
                                value=(w in default_wajib_names),
                                key=f"chk_wajib_{slot_kota}_{slot_kec}_{slot_tgl_str}_{idx}_{w}",
                            )
                            if is_checked:
                                checked_wajib.append(w)
                        opsional_preview = [w for w in all_wrk_names if w not in checked_wajib]
                        st.caption(
                            f"Ringkasan: **{len(checked_wajib)} Wajib Kunjung** • "
                            f"**{len(opsional_preview)} Opsional** "
                            f"({', '.join(opsional_preview) if opsional_preview else '-'})"
                        )
                        btn_save_batch = st.form_submit_button(
                            "💾 Simpan Status Wajib / Opsional Jadwal Ini",
                            type="primary",
                        )

                        if btn_save_batch:
                            wajib_set = {str(x).strip().casefold() for x in checked_wajib}
                            for _, r in sub_wrk_df.iterrows():
                                k_str = _warkop_status_key(r["Kota"], r["Kecamatan"], r["Nama Warkop / LKK"])
                                if str(r["Nama Warkop / LKK"]).strip().casefold() in wajib_set:
                                    status_map_current[k_str] = VISIT_STATUS_WAJIB
                                else:
                                    status_map_current[k_str] = VISIT_STATUS_TIDAK_WAJIB
                            if save_warkop_visit_status_map(status_map_current):
                                st.success(
                                    f"✅ Status warkop untuk **{slot_team}** ({slot_kota} — {slot_kec}, {slot_tgl_str}) "
                                    f"disimpan: **{len(checked_wajib)} Wajib Kunjung** & **{len(opsional_preview)} Opsional**."
                                )
                                st.rerun()
            else:
                st.info("Belum ada data jadwal pada `Jadwal SPG.xlsx`.")

        with tab_wrk_add:
            st.markdown("#### Tambah titik warkop / LKK baru")
            st.caption("Tentukan Kota, Kecamatan, Nama Warkop/LKK, Alamat, dan status Wajib Kunjung atau Opsional.")
            with st.form("form_tambah_lokasi_excel"):
                col_kota_input = st.selectbox("Kota / Kabupaten", options=["Surabaya", "Gresik"], key="add_l_kota")
                kec_geo_opts = get_geo_districts(col_kota_input)
                kec_existing_opts = sorted(
                    df_warkop_view[df_warkop_view["Kota"].str.casefold() == col_kota_input.casefold()]["Kecamatan"]
                    .dropna()
                    .unique()
                    .tolist()
                )
                kec_combined_opts = sorted(set(kec_geo_opts + kec_existing_opts))
                col_kec_select = st.selectbox(
                    "Pilih Kecamatan (atau ketik manual di bawah)",
                    options=[""] + kec_combined_opts,
                    key="add_l_kec_select",
                )
                col_kec_input = st.text_input(
                    "Kecamatan",
                    value=col_kec_select,
                    placeholder="Contoh: Tegalsari atau Sawahan",
                    key="add_l_kec_input",
                )
                col_warkop_input = st.text_input("Nama Warkop / LKK", placeholder="Contoh: Warkop Barokah", key="add_l_warkop")
                col_alamat_input = st.text_input("Alamat Warkop", placeholder="Contoh: Jl. Ngagel Tirto No. 10", key="add_l_alamat")
                col_status_input = st.selectbox(
                    "Status Kunjungan",
                    options=VISIT_STATUS_OPTIONS,
                    index=1,
                    key="add_l_status",
                    help="Pilih Wajib Kunjung untuk titik prioritas wajib, atau Opsional untuk titik non-wajib.",
                )
                btn_add_excel = st.form_submit_button("💾 Simpan Warkop Baru", type="primary")

                if btn_add_excel:
                    kec_clean = col_kec_input.strip()
                    wrk_clean = col_warkop_input.strip()
                    if kec_clean and wrk_clean:
                        kota_col_name = next((c for c in df_lokasi_excel.columns if "kota" in c.lower()), "Kota")
                        kec_col_name = next((c for c in df_lokasi_excel.columns if "kec" in c.lower() or "wilayah" in c.lower()), "Kecamatan")
                        warkop_col_name = next((c for c in df_lokasi_excel.columns if "warkop" in c.lower() or "lkk" in c.lower() or "nama" in c.lower()), "Nama Warkop / LKK")
                        alamat_col_name = next((c for c in df_lokasi_excel.columns if "alamat" in c.lower() or "address" in c.lower()), "Alamat Warkop / LKK")

                        new_row = {
                            kota_col_name: col_kota_input,
                            kec_col_name: kec_clean,
                            warkop_col_name: wrk_clean,
                            alamat_col_name: col_alamat_input.strip() if col_alamat_input.strip() else "-",
                        }
                        df_lokasi_excel = pd.concat([df_lokasi_excel, pd.DataFrame([new_row])], ignore_index=True)
                        status_map_current[_warkop_status_key(col_kota_input, kec_clean, wrk_clean)] = col_status_input
                        if save_master_lokasi_excel(df_lokasi_excel) and save_warkop_visit_status_map(status_map_current):
                            st.success(f"✅ Warkop '{wrk_clean}' ({col_status_input}) berhasil disimpan!")
                            st.rerun()
                    else:
                        st.warning("Mohon isi nama Kecamatan dan Nama Warkop/LKK.")

        with tab_wrk_manage:
            st.markdown("#### Kelola & edit data warkop aktif")
            st.caption("Filter berdasarkan Kota, Kecamatan, atau Status Kunjungan untuk mengubah atau menghapus titik warkop.")
            if df_warkop_view.empty:
                st.info("Belum ada data warkop aktif.")
            else:
                col_f_k, col_f_kec, col_f_st = st.columns(3)
                with col_f_k:
                    f_kota_opts = ["Semua Kota"] + sorted(df_warkop_view["Kota"].unique().tolist())
                    f_kota = st.selectbox("Filter Kota", options=f_kota_opts, key="wrk_manage_kota")
                df_after_kota = df_warkop_view if f_kota == "Semua Kota" else df_warkop_view[df_warkop_view["Kota"] == f_kota]
                with col_f_kec:
                    f_kec_opts = ["Semua Kecamatan"] + sorted(df_after_kota["Kecamatan"].unique().tolist())
                    f_kec = st.selectbox("Filter Kecamatan", options=f_kec_opts, key="wrk_manage_kec")
                with col_f_st:
                    f_st = st.selectbox("Filter Status Kunjungan", options=["Semua Status"] + VISIT_STATUS_OPTIONS, key="wrk_manage_status")

                filtered_manage_df = df_after_kota.copy()
                if f_kec != "Semua Kecamatan":
                    filtered_manage_df = filtered_manage_df[filtered_manage_df["Kecamatan"] == f_kec]
                if f_st != "Semua Status":
                    filtered_manage_df = filtered_manage_df[filtered_manage_df["Status Kunjungan"] == f_st]

                st.markdown(f"**{len(filtered_manage_df)} titik warkop ditampilkan**")
                edited_wrk_df = st.data_editor(
                    filtered_manage_df,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Status Kunjungan": st.column_config.SelectboxColumn(
                            "Status Kunjungan",
                            options=VISIT_STATUS_OPTIONS,
                            required=True,
                        )
                    },
                    key="editor_excel_warkop_terstruktur",
                )
                if st.button("💾 Simpan Perubahan Tabel Warkop", type="primary", key="btn_save_wrk_table"):
                    kota_col_name = next((c for c in df_lokasi_excel.columns if "kota" in c.lower()), "Kota")
                    kec_col_name = next((c for c in df_lokasi_excel.columns if "kec" in c.lower() or "wilayah" in c.lower()), "Kecamatan")
                    warkop_col_name = next((c for c in df_lokasi_excel.columns if "warkop" in c.lower() or "lkk" in c.lower() or "nama" in c.lower()), "Nama Warkop / LKK")
                    alamat_col_name = next((c for c in df_lokasi_excel.columns if "alamat" in c.lower() or "address" in c.lower()), "Alamat Warkop / LKK")

                    updated_lokasi = df_lokasi_excel.copy()
                    for _, er in edited_wrk_df.iterrows():
                        k_v = str(er.get("Kota", "")).strip()
                        kc_v = str(er.get("Kecamatan", "")).strip()
                        w_v = str(er.get("Nama Warkop / LKK", "")).strip()
                        a_v = str(er.get("Alamat Warkop / LKK", "-")).strip() or "-"
                        st_v = str(er.get("Status Kunjungan", VISIT_STATUS_WAJIB)).strip()
                        if not w_v:
                            continue
                        status_map_current[_warkop_status_key(k_v, kc_v, w_v)] = st_v
                        m_idx = updated_lokasi[
                            updated_lokasi[kec_col_name].astype(str).str.strip().str.casefold().eq(kc_v.casefold())
                            & updated_lokasi[warkop_col_name].astype(str).str.strip().str.casefold().eq(w_v.casefold())
                        ].index
                        if len(m_idx) > 0:
                            updated_lokasi.at[m_idx[0], kota_col_name] = k_v
                            updated_lokasi.at[m_idx[0], alamat_col_name] = a_v

                    if save_master_lokasi_excel(updated_lokasi) and save_warkop_visit_status_map(status_map_current):
                        st.success("✅ Perubahan data warkop dan status Wajib / Opsional berhasil disimpan!")
                        st.rerun()

        with tab_wrk_excel:
            st.markdown("#### Unduh dan unggah daftar warkop & status kunjungan melalui Excel")
            st.caption("Download data warkop beserta kolom `Status Kunjungan` (`Wajib Kunjung` / `Opsional`), edit di Excel, lalu unggah kembali.")
            wrk_export_buf = BytesIO()
            with pd.ExcelWriter(wrk_export_buf, engine="openpyxl") as writer:
                df_warkop_view.to_excel(writer, index=False, sheet_name="Master Warkop")

            st.download_button(
                "⬇️ Download Master Warkop & Status Kunjungan (.xlsx)",
                data=wrk_export_buf.getvalue(),
                file_name="Master WarkopLKK Status.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                key="download_master_warkop_status_xlsx",
            )

            uploaded_wrk_file = st.file_uploader(
                "Pilih file Excel warkop untuk diunggah",
                type=["xlsx"],
                key="upload_master_warkop_xlsx",
            )
            if uploaded_wrk_file is not None:
                try:
                    df_up_wrk = pd.read_excel(uploaded_wrk_file)
                    df_up_wrk.columns = [str(c).strip() for c in df_up_wrk.columns]
                    st.dataframe(df_up_wrk.head(20), use_container_width=True, hide_index=True)
                    if st.button("Ganti Master Warkop dengan File Excel Ini", type="primary", key="btn_confirm_up_wrk"):
                        c_k = next((c for c in df_up_wrk.columns if "kota" in c.lower()), None) or "Kota"
                        c_kc = next((c for c in df_up_wrk.columns if "kec" in c.lower() or "wilayah" in c.lower()), None) or "Kecamatan"
                        c_w = next((c for c in df_up_wrk.columns if "warkop" in c.lower() or "lkk" in c.lower() or "nama" in c.lower()), None) or "Nama Warkop / LKK"
                        c_a = next((c for c in df_up_wrk.columns if "alamat" in c.lower() or "address" in c.lower()), None) or "Alamat Warkop / LKK"
                        c_s = next((c for c in df_up_wrk.columns if "status" in c.lower() or "wajib" in c.lower()), None)

                        base_cols = [c for c in [c_k, c_kc, c_w, c_a] if c in df_up_wrk.columns]
                        df_to_save_wrk = df_up_wrk[base_cols].copy()
                        new_status_map = {}
                        for _, r in df_up_wrk.iterrows():
                            k_val = str(r.get(c_k, "Surabaya")).strip()
                            kc_val = str(r.get(c_kc, "")).strip()
                            w_val = str(r.get(c_w, "")).strip()
                            if not w_val:
                                continue
                            raw_st = str(r.get(c_s, VISIT_STATUS_WAJIB) if c_s else VISIT_STATUS_WAJIB).strip()
                            st_val = VISIT_STATUS_TIDAK_WAJIB if ("tidak" in raw_st.casefold() or "opsional" in raw_st.casefold()) else VISIT_STATUS_WAJIB
                            new_status_map[_warkop_status_key(k_val, kc_val, w_val)] = st_val

                        if save_master_lokasi_excel(df_to_save_wrk) and save_warkop_visit_status_map(new_status_map):
                            st.success("✅ Master Warkop dan status Wajib / Opsional berhasil diperbarui dari Excel!")
                            st.rerun()
                except Exception as exc:
                    st.error(f"Gagal membaca file Excel warkop: {exc}")

        st.markdown("---")
        if st.button("⬅️ Kembali ke Dashboard", key="btn_back_master_lokasi"):
            st.session_state["admin_view"] = "Dashboard"
            st.rerun()
        st.stop()

    # --- MONITORING JADWAL SPG ---
    elif st.session_state["admin_view"] == "Master_Jadwal_Excel":
        st.markdown("## 📅 Entry & Monitoring Jadwal SPG (Kecamatan, Team & Tanggal)")
        render_schedule_entry()
        st.stop()

    # --- ANALITIK ---
    elif st.session_state["admin_view"] == "Analitik":
        st.markdown("## 📊 Analitik & Rekapitulasi All User")
        st.caption("Laporan mendalam performa seluruh tim berdasarkan demografi, wilayah, dan sebaran kecamatan.")

        df_all_users = load_database()
        if not df_all_users.empty:
            df_all_users["Jumlah_Bungkus"] = pd.to_numeric(df_all_users["Jumlah_Bungkus"], errors="coerce").fillna(0)

            c1, c2 = st.columns(2)
            with c1:
                st.markdown("#### 👥 Demografi Konsumen (Gender)")
                gender_count = df_all_users["Gender"].value_counts()
                st.bar_chart(gender_count)
            with c2:
                st.markdown("#### 📊 Sebaran Range Umur Konsumen")
                if "Range_Umur" in df_all_users.columns:
                    age_count = df_all_users["Range_Umur"].value_counts()
                    st.bar_chart(age_count)
                else:
                    st.info("Data Range Umur belum tersedia.")

            st.markdown("---")
            st.markdown("#### 🏙️ Sebaran per Wilayah (Kota/Kab)")
            kota_count = df_all_users["Kota_Kab"].value_counts()
            st.bar_chart(kota_count)

            st.markdown("---")
            st.markdown("#### 🗺️ Sebaran Kunjungan & Omset per Kecamatan")

            list_kota_analitik = ["Semua Wilayah"] + sorted(df_all_users["Kota_Kab"].dropna().unique().tolist())
            pilih_kota_kec = st.selectbox("Filter Kota/Kabupaten untuk Sebaran Kecamatan", list_kota_analitik)

            df_kec_analitik = df_all_users.copy()
            if pilih_kota_kec != "Semua Wilayah":
                df_kec_analitik = df_kec_analitik[df_kec_analitik["Kota_Kab"] == pilih_kota_kec]

            if not df_kec_analitik.empty:
                df_sebaran_kec = (
                    df_kec_analitik.groupby(["Kota_Kab", "Kecamatan"])
                    .agg(
                        Titik_Warkop=("Warkop_LKK", lambda x: x.nunique()),
                        Total_Konsumen=("Nama_Konsumen", "count"),
                        Total_Omset_Bungkus=("Jumlah_Bungkus", "sum"),
                    )
                    .reset_index()
                    .sort_values(by="Total_Omset_Bungkus", ascending=False)
                )
                chart_kec = df_sebaran_kec.set_index("Kecamatan")["Total_Omset_Bungkus"]
                st.bar_chart(chart_kec)
                st.dataframe(df_sebaran_kec, use_container_width=True)
            else:
                st.info("Tidak ada data pada wilayah yang dipilih.")
        else:
            st.info("Belum ada data untuk ditampilkan dalam grafik analitik.")

        st.markdown("---")
        if st.button("⬅️ Kembali ke Dashboard"):
            st.session_state["admin_view"] = "Dashboard"
            st.rerun()
        st.stop()

    # --- PETA RUTE ---
    elif st.session_state["admin_view"] == "Peta_Rute":
        st.markdown("## 🗺️ Visualisasi Peta Rute & Poligon Kecamatan")
        st.caption("Pantau urutan kunjungan, jam, rute perjalanan, dan batas wilayah poligon kecamatan berdasarkan filter Team SPG, Nama SPG, dan Tanggal.")

        df_peta_all = load_database()
        if not df_peta_all.empty and "Latitude" in df_peta_all.columns and "Longitude" in df_peta_all.columns:
            df_peta_all = df_peta_all.copy()
            df_peta_all["Latitude"] = pd.to_numeric(df_peta_all["Latitude"], errors="coerce")
            df_peta_all["Longitude"] = pd.to_numeric(df_peta_all["Longitude"], errors="coerce")
            df_peta_all["Waktu_Dt"] = pd.to_datetime(df_peta_all["Waktu"], errors="coerce")
            df_peta_all["Tanggal"] = df_peta_all["Waktu_Dt"].dt.strftime("%d-%m-%Y")
            df_peta_all = df_peta_all.dropna(subset=["Latitude", "Longitude"])

            col_p1, col_p2, col_p3 = st.columns(3)
            with col_p1:
                list_team_filter = ["Semua Team"] + sorted(df_peta_all["Promotor"].dropna().astype(str).unique().tolist())
                pilih_team = st.selectbox("Filter Team SPG", list_team_filter, key="peta_filter_team")
            with col_p2:
                list_spg_filter = ["Semua SPG"] + sorted(df_peta_all["Nama_SPG"].dropna().astype(str).unique().tolist())
                pilih_spg = st.selectbox("Filter Nama SPG", list_spg_filter, key="peta_filter_spg")
            with col_p3:
                list_tgl_filter = ["Semua Tanggal"] + sorted(df_peta_all["Tanggal"].dropna().astype(str).unique().tolist(), reverse=True)
                pilih_tgl = st.selectbox("Filter Tanggal", list_tgl_filter, key="peta_filter_tgl")

            col_opt1, col_opt2 = st.columns([0.65, 0.35])
            with col_opt1:
                mode_warna_titik = st.selectbox(
                    "Warna Titik Kunjungan",
                    options=["Per Tanggal", "Per Nama SPG", "Seragam (Oranye)"],
                    key="peta_warna_titik",
                )
            with col_opt2:
                st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                tampilkan_label = st.checkbox(
                    "Tampilkan label urutan & jam",
                    value=True,
                    key="peta_toggle_label",
                )

            df_filtered_map = df_peta_all.copy()
            if pilih_team != "Semua Team":
                df_filtered_map = df_filtered_map[df_filtered_map["Promotor"].astype(str) == pilih_team]
            if pilih_spg != "Semua SPG":
                df_filtered_map = df_filtered_map[df_filtered_map["Nama_SPG"].astype(str) == pilih_spg]
            if pilih_tgl != "Semua Tanggal":
                df_filtered_map = df_filtered_map[df_filtered_map["Tanggal"].astype(str) == pilih_tgl]

            relevant_kotas = []
            if not df_filtered_map.empty and "Kota_Kab" in df_filtered_map.columns:
                seen_kota = set()
                for raw_kota in df_filtered_map["Kota_Kab"].dropna().astype(str):
                    cleaned_kota = raw_kota.strip()
                    key = cleaned_kota.casefold()
                    if cleaned_kota and key not in seen_kota:
                        seen_kota.add(key)
                        relevant_kotas.append(cleaned_kota)

            if not relevant_kotas:
                relevant_kotas = ["Surabaya", "Gresik"]

            layers_list = []
            kecamatan_dari_data = []
            if not df_filtered_map.empty and "Kecamatan" in df_filtered_map.columns:
                seen_kec = set()
                for raw_kec in df_filtered_map["Kecamatan"].dropna().astype(str):
                    kc_clean = raw_kec.strip()
                    if kc_clean and kc_clean != "-" and kc_clean.casefold() not in seen_kec:
                        seen_kec.add(kc_clean.casefold())
                        kecamatan_dari_data.append(kc_clean)

            opsi_kec_peta = []
            seen_opsi = set()
            for kota_name in relevant_kotas:
                for kc_item in get_geo_districts(kota_name):
                    if kc_item.casefold() not in seen_opsi:
                        seen_opsi.add(kc_item.casefold())
                        opsi_kec_peta.append(kc_item)
            for kc_item in kecamatan_dari_data:
                if kc_item.casefold() not in seen_opsi:
                    seen_opsi.add(kc_item.casefold())
                    opsi_kec_peta.append(kc_item)

            default_kec_peta = [
                kc for kc in kecamatan_dari_data
                if any(kc.casefold() == op.casefold() for op in opsi_kec_peta)
            ]
            if not default_kec_peta and opsi_kec_peta:
                default_kec_peta = opsi_kec_peta[:3]

            if "peta_filter_kecamatan_geojson_pending" in st.session_state:
                st.session_state["peta_filter_kecamatan_geojson"] = [
                    x for x in st.session_state.pop("peta_filter_kecamatan_geojson_pending")
                    if x in opsi_kec_peta
                ]

            if "peta_filter_kecamatan_geojson" not in st.session_state:
                st.session_state["peta_filter_kecamatan_geojson"] = default_kec_peta
            else:
                st.session_state["peta_filter_kecamatan_geojson"] = [
                    x for x in st.session_state["peta_filter_kecamatan_geojson"]
                    if x in opsi_kec_peta
                ]

            col_poly_sel, col_poly_reset = st.columns([0.78, 0.22])
            with col_poly_sel:
                kecamatan_peta_terpilih = st.multiselect(
                    "Poligon Kecamatan Ditampilkan (On-Demand)",
                    options=opsi_kec_peta,
                    key="peta_filter_kecamatan_geojson",
                    max_selections=8,
                    help="Maksimal 8 kecamatan untuk performa optimal.",
                )
            with col_poly_reset:
                st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                if st.button("🔄 Reset Poligon", key="btn_reset_peta_polygon", use_container_width=True):
                    st.session_state["peta_filter_kecamatan_geojson_pending"] = list(default_kec_peta)
                    st.rerun()

            if not kecamatan_peta_terpilih:
                st.caption("ℹ️ Tidak ada kecamatan yang dipilih pada filter poligon—poligon tidak digambar (titik & rute tetap tampil).")

            if len(kecamatan_peta_terpilih) > 8:
                st.warning("⚠️ Maksimal 8 kecamatan untuk performa optimal. Menampilkan 8 pertama.")
                kecamatan_peta_terpilih = kecamatan_peta_terpilih[:8]

            features_gabungan = build_polygon_features(tuple(kecamatan_peta_terpilih))

            if features_gabungan:
                layers_list.append(
                    pdk.Layer(
                        "GeoJsonLayer",
                        data={"type": "FeatureCollection", "features": features_gabungan},
                        stroked=True,
                        filled=True,
                        get_fill_color="properties.fill_color",
                        get_line_color="properties.line_color",
                        get_line_width=3,
                        line_width_min_pixels=2,
                        pickable=True,
                        auto_highlight=True,
                    )
                )
            elif kecamatan_peta_terpilih:
                st.warning(
                    "⚠️ File GeoJSON untuk kecamatan terpilih tidak ditemukan atau kosong di folder `geojson_by_kecamatan/`."
                )

            if not df_filtered_map.empty:
                df_filtered_map = df_filtered_map.sort_values(
                    by=["Waktu_Dt", "Waktu"], ascending=[True, True], na_position="last"
                ).reset_index(drop=True)

                if pilih_tgl == "Semua Tanggal" and df_filtered_map["Tanggal"].nunique(dropna=True) > 1:
                    df_filtered_map["Urutan"] = df_filtered_map.groupby("Tanggal", dropna=False).cumcount() + 1
                else:
                    df_filtered_map["Urutan"] = df_filtered_map.index + 1

                df_filtered_map["Jam_Label"] = df_filtered_map["Waktu_Dt"].dt.strftime("%H:%M").fillna("-")
                df_filtered_map["Warkop_Label"] = df_filtered_map["Warkop_LKK"].fillna("-").astype(str)
                df_filtered_map["Indikator_Titik"] = (
                    "#" + df_filtered_map["Urutan"].astype(str)
                    + " (" + df_filtered_map["Jam_Label"] + ") - "
                    + df_filtered_map["Warkop_Label"]
                )
                _lat_str = df_filtered_map["Latitude"].map(lambda x: f"{x:.6f}")
                _lon_str = df_filtered_map["Longitude"].map(lambda x: f"{x:.6f}")
                df_filtered_map["Koordinat_Str"] = _lat_str + ", " + _lon_str
                df_filtered_map["Link_Google_Maps"] = (
                    "https://www.google.com/maps/search/?api=1&query=" + _lat_str + "," + _lon_str
                )

                point_palette_rgba = [
                    [234, 88, 12, 235],
                    [37, 99, 235, 235],
                    [22, 163, 74, 235],
                    [147, 51, 234, 235],
                    [219, 39, 119, 235],
                    [13, 148, 136, 235],
                    [202, 138, 4, 235],
                    [71, 85, 105, 235],
                ]
                point_palette_hex = [
                    "#EA580C", "#2563EB", "#16A34A", "#9333EA",
                    "#DB2777", "#0D9488", "#CA8A04", "#475569",
                ]

                if mode_warna_titik == "Per Tanggal":
                    categories = sorted(df_filtered_map["Tanggal"].fillna("-").astype(str).unique().tolist())
                    cat_to_idx = {cat: idx % len(point_palette_rgba) for idx, cat in enumerate(categories)}
                    df_filtered_map["_color_idx"] = df_filtered_map["Tanggal"].fillna("-").astype(str).map(cat_to_idx)
                    df_filtered_map["Titik_Color"] = df_filtered_map["_color_idx"].apply(lambda i: point_palette_rgba[i])
                elif mode_warna_titik == "Per Nama SPG":
                    categories = sorted(df_filtered_map["Nama_SPG"].fillna("-").astype(str).unique().tolist())
                    cat_to_idx = {cat: idx % len(point_palette_rgba) for idx, cat in enumerate(categories)}
                    df_filtered_map["_color_idx"] = df_filtered_map["Nama_SPG"].fillna("-").astype(str).map(cat_to_idx)
                    df_filtered_map["Titik_Color"] = df_filtered_map["_color_idx"].apply(lambda i: point_palette_rgba[i])
                else:
                    categories = ["Semua Titik"]
                    cat_to_idx = {"Semua Titik": 0}
                    df_filtered_map["_color_idx"] = 0
                    df_filtered_map["Titik_Color"] = [point_palette_rgba[0]] * len(df_filtered_map)

                koordinat_rute = df_filtered_map[["Longitude", "Latitude"]].values.tolist()
                center_lat = float(df_filtered_map["Latitude"].mean())
                center_lon = float(df_filtered_map["Longitude"].mean())

                if len(koordinat_rute) >= 2:
                    path_layer = pdk.Layer(
                        "PathLayer",
                        data=[
                            {
                                "path": koordinat_rute,
                                "name": f"Rute ({len(koordinat_rute)} titik)",
                            }
                        ],
                        get_path="path",
                        get_color=[220, 38, 38, 220],
                        get_width=6,
                        pickable=True,
                    )
                    layers_list.append(path_layer)

                scatter_layer = pdk.Layer(
                    "ScatterplotLayer",
                    data=df_filtered_map,
                    get_position=["Longitude", "Latitude"],
                    get_fill_color="Titik_Color",
                    get_line_color=[255, 255, 255, 240],
                    line_width_min_pixels=2,
                    get_radius=75,
                    pickable=True,
                )
                layers_list.append(scatter_layer)

                if tampilkan_label:
                    text_layer = pdk.Layer(
                        "TextLayer",
                        data=df_filtered_map,
                        get_position=["Longitude", "Latitude"],
                        get_text="Indikator_Titik",
                        get_size=12,
                        get_color=[15, 23, 42, 255],
                        get_background_color=[255, 255, 255, 225],
                        get_background_padding=[4, 2, 4, 2],
                        get_pixel_offset=[0, -18],
                        pickable=False,
                    )
                    layers_list.append(text_layer)

                view_state = pdk.ViewState(latitude=center_lat, longitude=center_lon, zoom=12, pitch=30)
                deck_map = pdk.Deck(
                    layers=layers_list,
                    initial_view_state=view_state,
                    tooltip={
                        "html": (
                            "<b>Kunjungan Ke:</b> #{Urutan} (Jam: {Jam_Label})<br/>"
                            "<b>Wilayah / Kecamatan:</b> {Kota_Kab} / {Kecamatan}<br/>"
                            "<b>Team & SPG:</b> {Promotor} ({Nama_SPG})<br/>"
                            "<b>Plat Mobil:</b> {Plat_Mobil}<br/>"
                            "<b>Warkop / LKK:</b> {Warkop_LKK}<br/>"
                            "<b>Brand:</b> {Brand_Rokok} ({Jumlah_Bungkus} bks)<br/>"
                            "<b>Koordinat:</b> {Koordinat_Str}<br/>"
                            "<b>Waktu Lengkap:</b> {Waktu}"
                        ),
                        "style": {"backgroundColor": "#0F172A", "color": "white"},
                    },
                )
                st.pydeck_chart(deck_map)

                if mode_warna_titik != "Seragam (Oranye)" and categories:
                    legend_items = []
                    for cat in categories:
                        hex_col = point_palette_hex[cat_to_idx[cat]]
                        legend_items.append(
                            f"<span style='display:inline-flex;align-items:center;gap:6px;margin-right:14px;margin-bottom:4px;'>"
                            f"<span style='width:12px;height:12px;border-radius:50%;background:{hex_col};display:inline-block;border:1px solid #fff;'></span>"
                            f"<span>{cat}</span></span>"
                        )
                    st.markdown(
                        f"<div style='font-size:0.85rem;margin-top:4px;margin-bottom:10px;'><b>Legenda ({mode_warna_titik}):</b> {''.join(legend_items)}</div>",
                        unsafe_allow_html=True,
                    )

                st.markdown("#### 🔗 Buka Titik di Google Maps")
                option_map = {
                    f"#{row['Urutan']} | {row['Tanggal']} {row['Jam_Label']} | {row['Warkop_LKK']} ({row['Koordinat_Str']})": row["Link_Google_Maps"]
                    for _, row in df_filtered_map.iterrows()
                }
                col_pick_gmap, col_btn_gmap = st.columns([0.65, 0.35])
                with col_pick_gmap:
                    selected_point_label = st.selectbox(
                        "Pilih titik kunjungan",
                        options=list(option_map.keys()),
                        key="peta_pilih_titik_gmap",
                    )
                with col_btn_gmap:
                    st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                    st.link_button(
                        "📍 Buka Google Maps",
                        url=option_map[selected_point_label],
                        use_container_width=True,
                    )

                st.markdown("#### 🧭 Urutan Titik Kunjungan Terfilter")
                df_urutan_view = df_filtered_map[
                    [
                        "Urutan",
                        "Tanggal",
                        "Jam_Label",
                        "Promotor",
                        "Nama_SPG",
                        "Kota_Kab",
                        "Kecamatan",
                        "Warkop_LKK",
                        "Brand_Rokok",
                        "Jumlah_Bungkus",
                        "Koordinat_Str",
                        "Link_Google_Maps",
                    ]
                ].rename(columns={"Jam_Label": "Jam", "Koordinat_Str": "Koordinat"})
                st.dataframe(
                    df_urutan_view,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Link_Google_Maps": st.column_config.LinkColumn(
                            "Google Maps",
                            display_text="Buka Maps 📍",
                        )
                    },
                )
            else:
                st.warning("Tidak ada data koordinat yang cocok dengan filter yang dipilih.")
        else:
            st.info("Belum ada data koordinat GPS yang terekam pada sistem.")

        st.markdown("---")
        if st.button("⬅️ Kembali ke Dashboard"):
            st.session_state["admin_view"] = "Dashboard"
            st.rerun()
        st.stop()

    # --- DASHBOARD ADMIN UTAMA ---
    st.markdown("## 📊 Dashboard Admin & Manajemen Lapangan")
    st.caption("Pilih menu master data atau pantau rekapitulasi tim secara real-time.")

    st.markdown("#### 📦 Master Data")
    col_m1, col_m2, col_m3 = st.columns(3)
    with col_m1:
        if st.button("🔑 PIN & Hak Akses User\nAtur PIN SPG & Supervisi", use_container_width=True):
            st.session_state["admin_view"] = "Master_Akses"
            st.rerun()
        if st.button("🏷️ Master Nama Team\nAtur nama team 1 - 20", use_container_width=True):
            st.session_state["admin_view"] = "Master_Nama_Team"
            st.rerun()
        if st.button("👥 Master Team & Brand\nAtur brand rokok per team", use_container_width=True):
            st.session_state["admin_view"] = "Master_Team"
            st.rerun()
    with col_m2:
        if st.button("🚗 Master Plat Kendaraan\nTambah & hapus plat mobil", use_container_width=True):
            st.session_state["admin_view"] = "Master_Plat"
            st.rerun()
        if st.button("🚬 Merek Rokok & Target\nKelola daftar merek & target", use_container_width=True):
            st.session_state["admin_view"] = "Master_Brand"
            st.rerun()
        if st.button("💰 Harga Rokok Konsumen\nAdd & edit harga merk", use_container_width=True):
            st.session_state["admin_view"] = "Master_Harga"
            st.rerun()
    with col_m3:
        if st.button("📍 Lokasi Warkop (Excel)\nKelola dari Master Warkop", use_container_width=True):
            st.session_state["admin_view"] = "Master_Lokasi"
            st.rerun()
        if st.button("📅 Entry & Monitoring Jadwal SPG\nSemua Team", use_container_width=True):
            st.session_state["admin_view"] = "Master_Jadwal_Excel"
            st.rerun()

    st.markdown("---")
    st.markdown("#### 📈 Analitik & Pemetaan")
    col_a1, col_a2, col_a3 = st.columns(3)
    with col_a1:
        if st.button("📊 Analitik Lapangan\nDemografi & Kecamatan", use_container_width=True):
            st.session_state["admin_view"] = "Analitik"
            st.rerun()
    with col_a2:
        if st.button("🗺️ Peta Rute All User\nFilter Team/SPG/Tanggal", use_container_width=True):
            st.session_state["admin_view"] = "Peta_Rute"
            st.rerun()
    with col_a3:
        if st.button("⬅️ Keluar Admin", use_container_width=True):
            st.session_state["admin_logged_in"] = False
            st.rerun()

    st.markdown("---")
    st.markdown("#### ☁️ Backup & Load Data")
    render_google_sheet_backup_controls()

    st.markdown("---")
    st.markdown("#### 📥 Unduh Data Utama")
    st.caption("Unduhan ini hanya tersedia dari Dashboard Admin.")
    col_download_laporan, col_download_supervisi = st.columns(2)
    with col_download_laporan:
        st.download_button(
            "⬇️ Download Rekap Laporan SPG",
            data=load_database().to_csv(index=False).encode("utf-8-sig"),
            file_name=DB_FILE,
            mime="text/csv",
            use_container_width=True,
            key="download_rekap_laporan_admin",
        )
    with col_download_supervisi:
        st.download_button(
            "⬇️ Download Rekap Kontak Supervisi",
            data=load_supervisi_database().to_csv(index=False).encode("utf-8-sig"),
            file_name=DB_SUPERVISI_KONTAK_FILE,
            mime="text/csv",
            use_container_width=True,
            key="download_rekap_supervisi_admin",
        )

    st.markdown("---")
    st.markdown("#### 🌐 Ringkasan Cepat Data Masuk (All User)")

    df_all_users = load_database()
    df_all_supervisi = load_supervisi_database()

    if not df_all_users.empty:
        df_all_users["Waktu_Dt"] = pd.to_datetime(df_all_users["Waktu"], errors="coerce")
        df_all_users["Tanggal"] = df_all_users["Waktu_Dt"].dt.strftime("%d-%m-%Y")
        df_all_users = add_custom_week_columns(df_all_users, "Waktu_Dt")
        df_all_users["Jumlah_Bungkus"] = pd.to_numeric(df_all_users["Jumlah_Bungkus"], errors="coerce").fillna(0)

        today_dt = datetime.utcnow() + timedelta(hours=7)
        today_str = today_dt.strftime("%d-%m-%Y")
        current_month_str = today_dt.strftime("%m-%Y")
        current_week_label, _ = get_custom_week_info(today_dt)

        df_today = df_all_users[df_all_users["Tanggal"] == today_str].copy()
        omset_hari_ini = int(df_today["Jumlah_Bungkus"].sum())
        konsumen_hari_ini = len(df_today)

        if not df_today.empty:
            df_today_lb = (
                df_today.groupby(["Tanggal", "Periode_Minggu", "Promotor", "Kota_Kab", "Brand_Rokok"])
                .agg(Total_Omset_Team=("Jumlah_Bungkus", "sum"))
                .reset_index()
            )
            df_today_lb["Brand_Rokok_Clean"] = df_today_lb["Brand_Rokok"].apply(clean_brand_target_name)
            df_today_lb = (
                df_today_lb.groupby(["Tanggal", "Periode_Minggu", "Promotor", "Kota_Kab", "Brand_Rokok_Clean"])
                .agg(Total_Omset_Team=("Total_Omset_Team", "sum"))
                .reset_index()
                .rename(columns={"Brand_Rokok_Clean": "Brand_Rokok"})
            )
            df_today_lb["Target_Team"] = df_today_lb["Brand_Rokok"].apply(
                lambda brand: get_target_for_brand(brand, "target_team", 50)
            )
            target_hari_ini = int(df_today_lb["Target_Team"].sum())
        else:
            target_hari_ini = 100

        if target_hari_ini <= 0:
            target_hari_ini = 100

        persen_pencapaian = int((omset_hari_ini / target_hari_ini) * 100) if target_hari_ini > 0 else 0

        df_week = df_all_users[df_all_users["Periode_Minggu"] == current_week_label]
        omset_minggu_ini = int(df_week["Jumlah_Bungkus"].sum())
        konsumen_minggu_ini = len(df_week)

        df_all_users["Bulan_Tahun"] = df_all_users["Waktu_Dt"].dt.strftime("%m-%Y")
        df_month = df_all_users[df_all_users["Bulan_Tahun"] == current_month_str]
        omset_bulan_ini = int(df_month["Jumlah_Bungkus"].sum())
        konsumen_bulan_ini = len(df_month)

        kpi_col1, kpi_col2, kpi_col3 = st.columns(3)
        with kpi_col1:
            st.markdown(f"""
            <div class="dashboard-card">
                <div>
                    <div class="card-value">{omset_hari_ini:,} bks</div>
                    <div class="card-subtext">dari {target_hari_ini} target bks</div>
                </div>
                <div class="card-label">Omset Hari Ini</div>
            </div>
            """, unsafe_allow_html=True)
        with kpi_col2:
            bar_width = min(persen_pencapaian, 100)
            st.markdown(f"""
            <div class="dashboard-card">
                <div>
                    <div class="card-value-green">{persen_pencapaian}%</div>
                    <div class="progress-bar-container">
                        <div class="progress-bar-fill" style="width: {bar_width}%;"></div>
                    </div>
                </div>
                <div class="card-label">Pencapaian Omset Hari Ini</div>
            </div>
            """, unsafe_allow_html=True)
        with kpi_col3:
            st.markdown(f"""
            <div class="dashboard-card">
                <div>
                    <div class="card-value">{konsumen_hari_ini:,}</div>
                    <div class="card-subtext" style="opacity: 0;">-</div>
                </div>
                <div class="card-label">Konsumen Beli Hari Ini</div>
            </div>
            """, unsafe_allow_html=True)

        kpi_col4, kpi_col5, kpi_col6 = st.columns(3)
        with kpi_col4:
            st.markdown(f"""
            <div class="dashboard-card">
                <div>
                    <div class="card-value">{omset_minggu_ini:,} bks</div>
                    <div class="card-subtext">{konsumen_minggu_ini:,} Konsumen Minggu Ini</div>
                </div>
                <div class="card-label">Omset Minggu Ini</div>
            </div>
            """, unsafe_allow_html=True)
        with kpi_col5:
            st.markdown(f"""
            <div class="dashboard-card">
                <div>
                    <div class="card-value">{omset_bulan_ini:,} bks</div>
                    <div class="card-subtext" style="opacity: 0;">-</div>
                </div>
                <div class="card-label">Omset Bulan Ini</div>
            </div>
            """, unsafe_allow_html=True)
        with kpi_col6:
            st.markdown(f"""
            <div class="dashboard-card">
                <div>
                    <div class="card-value">{konsumen_bulan_ini:,}</div>
                    <div class="card-subtext" style="opacity: 0;">-</div>
                </div>
                <div class="card-label">Konsumen Beli Bulan Ini</div>
            </div>
            """, unsafe_allow_html=True)

        all_weeks_admin = sorted(df_all_users["Periode_Minggu"].dropna().unique().tolist(), reverse=True)
        all_dates_admin = sorted(df_all_users["Tanggal"].dropna().unique().tolist(), reverse=True)
        all_teams_admin = sorted(df_all_users["Promotor"].dropna().unique().tolist())
        all_spgs_admin = sorted(df_all_users["Nama_SPG"].dropna().unique().tolist())

        st.markdown("---")
        st.markdown("### 🏆 Leaderboard Team SPG (Berdasarkan Target Team)")

        col_lb_w, col_lb_tgl, col_lb_team = st.columns(3)
        with col_lb_w:
            filter_lb_week = st.multiselect("Filter Periode Minggu (Leaderboard)", options=all_weeks_admin, default=all_weeks_admin, key="admin_lb_week")
        with col_lb_tgl:
            filter_lb_tgl = st.multiselect("Filter Tanggal (Leaderboard)", options=all_dates_admin, default=all_dates_admin, key="admin_lb_tgl")
        with col_lb_team:
            filter_lb_team = st.multiselect("Filter Team SPG (Leaderboard)", options=all_teams_admin, default=all_teams_admin, key="admin_lb_team")

        df_lb_filtered = df_all_users.copy()
        if filter_lb_week:
            df_lb_filtered = df_lb_filtered[df_lb_filtered["Periode_Minggu"].isin(filter_lb_week)]
        if filter_lb_tgl:
            df_lb_filtered = df_lb_filtered[df_lb_filtered["Tanggal"].isin(filter_lb_tgl)]
        if filter_lb_team:
            df_lb_filtered = df_lb_filtered[df_lb_filtered["Promotor"].isin(filter_lb_team)]

        if not df_lb_filtered.empty:
            df_team_leaderboard = (
                df_lb_filtered.groupby(["Tanggal", "Periode_Minggu", "Promotor", "Kota_Kab", "Brand_Rokok"])
                .agg(Total_Omset_Team=("Jumlah_Bungkus", "sum"), Total_Konsumen_Beli=("Nama_Konsumen", "count"))
                .reset_index()
            )
            df_team_leaderboard["Brand_Rokok_Clean"] = df_team_leaderboard["Brand_Rokok"].apply(clean_brand_target_name)
            df_team_leaderboard = (
                df_team_leaderboard.groupby(["Tanggal", "Periode_Minggu", "Promotor", "Kota_Kab", "Brand_Rokok_Clean"])
                .agg(Total_Omset_Team=("Total_Omset_Team", "sum"), Total_Konsumen_Beli=("Total_Konsumen_Beli", "sum"))
                .reset_index()
                .rename(columns={"Brand_Rokok_Clean": "Brand_Rokok"})
            )
            df_team_leaderboard["Target_Team"] = df_team_leaderboard["Brand_Rokok"].apply(
                lambda brand: get_target_for_brand(brand, "target_team", 50)
            )
            df_team_leaderboard["Status_Target_Team"] = df_team_leaderboard.apply(
                lambda r: "Achieved" if r["Total_Omset_Team"] >= r["Target_Team"] else "Not Achieved",
                axis=1
            )

            cols_lb_order = ["Tanggal", "Periode_Minggu", "Promotor", "Kota_Kab", "Brand_Rokok", "Total_Omset_Team", "Total_Konsumen_Beli", "Target_Team", "Status_Target_Team"]
            df_team_leaderboard = df_team_leaderboard[[c for c in cols_lb_order if c in df_team_leaderboard.columns]]

            st.dataframe(df_team_leaderboard.style.map(style_status_target, subset=["Status_Target_Team"]), use_container_width=True)
        else:
            st.info("Tidak ada data untuk filter Leaderboard yang dipilih.")

        st.markdown("---")
        st.markdown("### 🚬 Jumlah Rokok Laku Per SPG dan Per Merk")

        col_rk_w, col_rk1, col_rk2, col_rk3 = st.columns(4)
        with col_rk_w:
            filter_rk_week = st.multiselect("Filter Minggu (Rokok Laku)", options=all_weeks_admin, default=all_weeks_admin, key="admin_rk_week")
        with col_rk1:
            filter_rk_tgl = st.multiselect("Filter Tanggal (Rokok Laku)", options=all_dates_admin, default=all_dates_admin, key="admin_rk_tgl")
        with col_rk2:
            filter_rk_team = st.multiselect("Filter Team (Rokok Laku)", options=all_teams_admin, default=all_teams_admin, key="admin_rk_team")
        with col_rk3:
            filter_rk_spg = st.multiselect("Filter Nama SPG (Rokok Laku)", options=all_spgs_admin, default=all_spgs_admin, key="admin_rk_spg")

        df_rk_filtered = df_all_users.copy()
        if filter_rk_week:
            df_rk_filtered = df_rk_filtered[df_rk_filtered["Periode_Minggu"].isin(filter_rk_week)]
        if filter_rk_tgl:
            df_rk_filtered = df_rk_filtered[df_rk_filtered["Tanggal"].isin(filter_rk_tgl)]
        if filter_rk_team:
            df_rk_filtered = df_rk_filtered[df_rk_filtered["Promotor"].isin(filter_rk_team)]
        if filter_rk_spg:
            df_rk_filtered = df_rk_filtered[df_rk_filtered["Nama_SPG"].isin(filter_rk_spg)]

        if not df_rk_filtered.empty:
            df_rokok_summary = (
                df_rk_filtered.groupby(["Tanggal", "Periode_Minggu", "Promotor", "Nama_SPG", "Brand_Rokok"])
                .agg(Jumlah_Bungkus=("Jumlah_Bungkus", "sum"))
                .reset_index()
                .pivot_table(index=["Tanggal", "Periode_Minggu", "Promotor", "Nama_SPG"], columns="Brand_Rokok", values="Jumlah_Bungkus", fill_value=0)
                .reset_index()
            )
            st.dataframe(df_rokok_summary, use_container_width=True)
        else:
            st.info("Tidak ada data untuk filter Rokok Laku yang dipilih.")

    st.stop()

# ====================================================
# PORTAL LOGIN KHUSUS ADMIN (?page=admin)
# ====================================================
if _admin_portal_requested and not st.session_state["logged_in"] and not st.session_state["admin_logged_in"]:
    st.markdown(
        """
        <div class="login-header">
            <div style="font-size: 2.2rem; margin-bottom: 4px;">🔐</div>
            <h1>PORTAL ADMIN &amp; SUPERVISOR</h1>
            <p>Akses Khusus Pengelola Data Master &amp; Monitoring</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.container(border=True):
        with st.form("form_admin_portal_login"):
            admin_pass_main = st.text_input("Kata Sandi Admin", type="password", placeholder="Masukkan kata sandi admin")
            btn_admin_portal = st.form_submit_button("🔓 Masuk Halaman Admin", type="primary", use_container_width=True)
            if btn_admin_portal:
                if admin_pass_main == "admin123":
                    st.session_state["admin_logged_in"] = True
                    st.session_state["admin_view"] = "Dashboard"
                    st.rerun()
                else:
                    st.error("❌ Kata sandi admin salah!")
    st.stop()

# ====================================================
# HALAMAN LOGIN UTAMA (SPG, SUPERVISI & REKAPITULASI PENJUALAN)
# ====================================================
if not st.session_state["logged_in"]:
    st.markdown(
        """
        <div class="login-header">
            <div style="font-size: 2.2rem; margin-bottom: 4px;">📍</div>
            <h1>PORTAL LAPORAN &amp; MONITORING</h1>
            <p>Sistem Pelaporan Lapangan SPG &amp; Supervisi</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="section-title">1️⃣ Pilih Peran Masuk</div>', unsafe_allow_html=True)
    col_btn_mode1, col_btn_mode2, col_btn_mode3 = st.columns(3)
    with col_btn_mode1:
        if st.button(
            "📝 Masuk sebagai SPG",
            use_container_width=True,
            type="primary" if st.session_state["login_mode"] == "SPG" else "secondary",
        ):
            st.session_state["login_mode"] = "SPG"
            st.session_state["spg_authenticated_name"] = ""
            st.session_state["show_titik_lkk_spg"] = False
            st.rerun()

    with col_btn_mode2:
        if st.button(
            "👀 Masuk sebagai Supervisi",
            use_container_width=True,
            type="primary" if st.session_state["login_mode"] == "Supervisi" else "secondary",
        ):
            st.session_state["login_mode"] = "Supervisi"
            st.session_state["spg_authenticated_name"] = ""
            st.rerun()

    with col_btn_mode3:
        if st.button(
            "📊 Rekapitulasi Penjualan",
            use_container_width=True,
            type="primary" if st.session_state["login_mode"] == "Rekapitulasi" else "secondary",
        ):
            st.session_state["login_mode"] = "Rekapitulasi"
            st.session_state["spg_authenticated_name"] = ""
            st.rerun()

    team_name_mapping = load_master_team_names()
    list_team = [
        team_name_mapping[f"Team SPG {i}"]
        for i in range(1, 21)
        if team_name_mapping[f"Team SPG {i}"]
    ]
    akses_cfg_login = load_master_akses()

    if st.session_state["login_mode"] == "Rekapitulasi":
        st.markdown('<div class="section-title">2️⃣ Pilih Tim &amp; Tanggal Rekapitulasi</div>', unsafe_allow_html=True)
        with st.container(border=True):
            today_wib_rek = (datetime.utcnow() + timedelta(hours=7)).date()
            c_rek1, c_rek2 = st.columns([0.65, 0.35])
            with c_rek1:
                pilihan_user_rek = st.selectbox(
                    "👤 Nama Team Operasional",
                    list_team,
                    key="selected_team_rekapitulasi",
                )
            with c_rek2:
                tgl_rekap_input = st.date_input(
                    "📅 Tanggal Laporan",
                    value=today_wib_rek,
                    key="selected_date_rekapitulasi",
                )

        apply_team_theme_css(pilihan_user_rek)
        st.markdown("---")
        render_rekapitulasi_penjualan_report(
            team_name=pilihan_user_rek,
            target_date_str=tgl_rekap_input.strftime("%Y-%m-%d"),
            allow_edit_stok=False,
        )

        st.markdown(
            """
            <div class="footer-note">
                © 2026 Tumarso Monitoring System
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.stop()

    st.markdown('<div class="section-title">2️⃣ Pilih Tim, Identitas &amp; Verifikasi Jadwal</div>', unsafe_allow_html=True)
    with st.container(border=True):
        pilihan_user = st.selectbox(
            "👤 Nama Team Operasional",
            list_team,
            key="selected_team_login",
            on_change=reset_session_on_user_change,
        )

        schedule_ok, schedule_warning_msg, auto_detected_kota, auto_kecamatan_list, matched_schedule_rows = get_schedule_info_for_team(pilihan_user)
        today_wib = (datetime.utcnow() + timedelta(hours=7)).date()

        selected_sektor_login = ""
        if schedule_ok and len(auto_kecamatan_list) > 1:
            selected_sektor_login = st.selectbox(
                "📍 Pilih Sektor / Kecamatan Terjadwal Hari Ini",
                options=auto_kecamatan_list,
                key="login_select_sektor_team",
            )
        elif schedule_ok and len(auto_kecamatan_list) == 1:
            selected_sektor_login = auto_kecamatan_list[0]

        personnel_info = (
            get_scheduled_personnel_for_team(pilihan_user, today_wib, selected_kecamatan=selected_sektor_login)
            if schedule_ok
            else {"found": False, "supervisi": [], "spg_1": [], "spg_2": [], "spg_all": [], "vehicles": [], "records": []}
        )

        if schedule_ok and personnel_info.get("records"):
            auto_detected_kota = personnel_info["records"][0].get("kota") or auto_detected_kota

        scheduled_vehicles = personnel_info.get("vehicles", []) if personnel_info.get("found") else []
        if schedule_ok and not scheduled_vehicles:
            scheduled_vehicles = get_scheduled_vehicles(matched_schedule_rows, today_wib)

        spv_names = personnel_info.get("supervisi", [])
        spg1_names = personnel_info.get("spg_1", [])
        spg2_names = personnel_info.get("spg_2", [])
        spg_all_names = personnel_info.get("spg_all", [])

        spg_login_selected = ""
        pin_login_input = ""

        if not schedule_ok:
            st.error("⚠️ **Tidak Ada Jadwal Team Tersebut Untuk Hari Ini**")
        else:
            spv_label = ", ".join(spv_names) if spv_names else "Belum diatur di jadwal"
            spg1_label = ", ".join(spg1_names) if spg1_names else "-"
            spg2_label = ", ".join(spg2_names) if spg2_names else "-"
            sektor_tampil = selected_sektor_login or (", ".join(auto_kecamatan_list) if auto_kecamatan_list else "-")
            st.success(
                f"✅ **Jadwal Aktif Ditemukan**\n\n"
                f"- **Wilayah / Sektor:** {auto_detected_kota} — **{sektor_tampil}**\n"
                f"- **Supervisi:** **{spv_label}**\n"
                f"- **SPG 1:** **{spg1_label}** | **SPG 2:** **{spg2_label}**"
            )
            if st.session_state["login_mode"] == "Supervisi":
                if len(scheduled_vehicles) == 1:
                    st.info(f"🚗 Plat Kendaraan Terjadwal: **{scheduled_vehicles[0]}**")
                elif not scheduled_vehicles:
                    st.warning("Plat kendaraan belum diatur pada jadwal team hari ini.")
                else:
                    st.error(f"Terdapat lebih dari satu plat kendaraan ({', '.join(scheduled_vehicles)}). Samakan plat pada jadwal.")

                pin_login_input = st.text_input(
                    f"🔐 PIN Supervisi ({spv_label})",
                    type="password",
                    placeholder="Masukkan PIN Supervisi",
                    key="login_pin_supervisi",
                )
            else:
                opsi_spg_login = spg_all_names if spg_all_names else load_master_spgs()
                if opsi_spg_login:
                    spg_login_selected = st.selectbox(
                        "👩‍💼 Pilih Identitas Nama SPG Anda (Terkunci Selama Sesi)",
                        options=opsi_spg_login,
                        key="login_select_spg_identity",
                    )
                if akses_cfg_login.get("require_spg_pin", False):
                    pin_login_input = st.text_input(
                        f"🔐 PIN SPG ({spg_login_selected or 'SPG'})",
                        type="password",
                        placeholder="Masukkan PIN SPG",
                        key="login_pin_spg",
                    )

        st.markdown("")
        btn_login = st.button(f"🚀 Lanjut Masuk ({st.session_state['login_mode']})", type="primary", use_container_width=True)

        if btn_login:
            if not schedule_ok:
                st.error("❌ Akses ditolak: Tidak Ada Jadwal Team Tersebut Untuk Hari Ini.")
            elif st.session_state["login_mode"] == "Supervisi" and len(scheduled_vehicles) != 1:
                st.error("❌ Akses Supervisi ditolak: plat kendaraan pada jadwal belum tersedia atau tidak konsisten.")
            elif st.session_state["login_mode"] == "Supervisi" and not verify_user_pin(
                "Supervisi", spv_names[0] if spv_names else pilihan_user, pin_login_input, akses_cfg_login
            ):
                st.error("❌ PIN Supervisi salah! Masukkan PIN yang sesuai agar data Supervisi tidak tertukar.")
            elif (
                st.session_state["login_mode"] == "SPG"
                and akses_cfg_login.get("require_spg_pin", False)
                and not verify_user_pin("SPG", spg_login_selected, pin_login_input, akses_cfg_login)
            ):
                st.error("❌ PIN SPG salah! Masukkan PIN SPG yang sesuai.")
            else:
                st.session_state["logged_in"] = True
                st.session_state["user_spg"] = pilihan_user
                st.session_state["plat_mobil"] = scheduled_vehicles[0] if len(scheduled_vehicles) == 1 else "-"
                st.session_state["kota_kab"] = auto_detected_kota
                st.session_state["nama_supervisi_aktif"] = spv_names[0] if spv_names else ""
                st.session_state["spg_terjadwal_list"] = spg_all_names
                st.session_state["sektor_terjadwal_login"] = selected_sektor_login
                st.session_state["spg_authenticated_name"] = spg_login_selected
                st.session_state["show_titik_lkk_spg"] = False
                st.rerun()

    st.markdown(
        """
        <div class="footer-note">
            © 2026 Tumarso Monitoring System
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.stop()

# ====================================================
# APLIKASI UTAMA SETELAH LOGIN (TEMA DINAMIS PER TEAM)
# ====================================================
apply_team_theme_css(st.session_state["user_spg"])

# --- GPS & GEOFENCING ---
daftar_kecamatan = get_geo_districts(st.session_state["kota_kab"]) or ["Kecamatan Default"]
loc = get_geolocation()
detected_kecamatan = None

if loc is None or not isinstance(loc, dict) or "coords" not in loc:
    user_lat = -7.2575
    user_lon = 112.7521
    akurasi_meter = 0.0
    is_inside_geofence = True
else:
    user_lat = float(loc["coords"]["latitude"])
    user_lon = float(loc["coords"]["longitude"])
    akurasi_meter = round(float(loc["coords"].get("accuracy", 0)), 1)
    point_user = Point(user_lon, user_lat)
    is_inside_geofence = False

    sched_ok_gps, _, _, kec_terjadwal_gps, _ = get_schedule_info_for_team(st.session_state["user_spg"])
    kandidat_kec_gps = [k for k in (kec_terjadwal_gps or []) if k] if sched_ok_gps else []
    if not kandidat_kec_gps:
        kandidat_kec_gps = [k for k in daftar_kecamatan if k != "Kecamatan Default"]

    checked_any_geom = False
    for kc_cand in kandidat_kec_gps:
        fp_cand = _resolve_kecamatan_filepath(kc_cand)
        gdf_cand = load_kecamatan_gdf(kc_cand, _file_mtime(fp_cand) if fp_cand else 0.0)
        if gdf_cand is not None and not gdf_cand.empty:
            checked_any_geom = True
            col_kec_cand = next(
                (c for c in ["nm_kecamatan", "KECAMATAN", "kecamatan", "Name", "NAME"] if c in gdf_cand.columns),
                None,
            )
            for _, row_geom in gdf_cand.iterrows():
                geom = row_geom.geometry
                if geom is not None and (geom.contains(point_user) or geom.intersects(point_user)):
                    is_inside_geofence = True
                    detected_kecamatan = (
                        str(row_geom[col_kec_cand]).strip()
                        if col_kec_cand and pd.notna(row_geom[col_kec_cand])
                        else kc_cand
                    )
                    break
        if is_inside_geofence:
            break
    if not checked_any_geom:
        is_inside_geofence = True

is_inside_geofence = True

# --- JADWAL & TITIK KUNJUNGAN TERKUNCI ---
schedule_ok, _, _, daftar_kecamatan_terjadwal, _ = get_schedule_info_for_team(st.session_state["user_spg"])
if not schedule_ok:
    daftar_kecamatan_terjadwal = daftar_kecamatan if daftar_kecamatan else ["Kecamatan Umum"]
else:
    daftar_kecamatan_terjadwal = sorted(set(daftar_kecamatan_terjadwal))

df_sup_today_all = load_supervisi_database()
locked_point_today = get_active_locked_lkk_point_today(
    team_name=st.session_state["user_spg"],
    fallback_kota=st.session_state.get("kota_kab", ""),
)
latest_sup_contact = get_latest_supervisi_point_today(
    team_name=st.session_state["user_spg"],
    fallback_kota=st.session_state.get("kota_kab", ""),
    df_sup=df_sup_today_all,
)

df_master_excel = load_master_lokasi_excel()
col_kec_excel = next(
    (c for c in df_master_excel.columns if "kec" in c.lower() or "wilayah" in c.lower()),
    None,
) if not df_master_excel.empty else None
col_warkop_excel = next(
    (c for c in df_master_excel.columns if "warkop" in c.lower() or "lkk" in c.lower() or "nama" in c.lower()),
    None,
) if not df_master_excel.empty else None
col_alamat_excel = next(
    (c for c in df_master_excel.columns if "alamat" in c.lower() or "address" in c.lower()),
    None,
) if not df_master_excel.empty else None

# ====================================================
# MODE SUPERVISI (2 MENU SAVE: SAVE TITIK LKK & SAVE JUMLAH KONTAK)
# ====================================================
if st.session_state["login_mode"] == "Supervisi":
    today_str_sup_hdr = (datetime.utcnow() + timedelta(hours=7)).strftime("%Y-%m-%d")
    saved_contact_pairs_today = get_saved_contact_warkops_on_date(
        team_name=st.session_state["user_spg"],
        target_date_str=today_str_sup_hdr,
        df_sup=df_sup_today_all,
    )
    saved_contact_warkops_names = {w_n for _, w_n in saved_contact_pairs_today}

    # Jika titik yang sedang di-lock sudah disimpan kontaknya hari ini, lepas lock-nya agar tidak mengunci warkop yang sudah selesai
    if locked_point_today:
        lp_kc = str(locked_point_today.get("kecamatan", "") or "").strip().casefold()
        lp_w = str(locked_point_today.get("warkop", "") or "").strip().casefold()
        if (lp_kc, lp_w) in saved_contact_pairs_today or lp_w in saved_contact_warkops_names:
            clear_locked_lkk_point(st.session_state["user_spg"])
            locked_point_today = None

    col_banner, col_logout = st.columns([0.8, 0.2])
    with col_banner:
        spv_aktif = st.session_state.get("nama_supervisi_aktif", "").strip()
        st.markdown(
            f"""
            <div class="user-banner">
                <div class="user-banner-title">
                    <span>👤 {st.session_state['user_spg']}</span>
                    <span class="badge-mode">👀 Supervisi</span>
                </div>
                <div class="user-banner-sub">
                    🚗 Plat: <b>{st.session_state['plat_mobil']}</b> &nbsp;•&nbsp; 🏙️ Wilayah: <b>{st.session_state['kota_kab']}</b> &nbsp;•&nbsp; 🧑‍💼 SPV: <b>{spv_aktif or '-'}</b>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col_logout:
        st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
        if st.button("🚪 Keluar", use_container_width=True):
            st.session_state["logged_in"] = False
            st.session_state["spg_authenticated_name"] = ""
            st.rerun()

    if is_inside_geofence:
        st.success(
            f"📍 **GPS Aktif:** `{user_lat:.6f}`, `{user_lon:.6f}` (±{akurasi_meter}m) — **{st.session_state['kota_kab']}**"
        )
    else:
        st.warning(
            f"⚠️ **Info GPS:** Posisi Anda terdeteksi di luar poligon zona "
            f"{st.session_state['kota_kab']} (Lat: `{user_lat:.6f}`, Lon: `{user_lon:.6f}`)."
        )

    st.markdown('<div class="section-title">📍 Titik Kunjungan Lapangan</div>', unsafe_allow_html=True)
    with st.container(border=True):
        col_sync_1, col_sync_2 = st.columns([0.78, 0.22])
        status_map_sup = load_warkop_visit_status_map()
        with col_sync_1:
            if locked_point_today:
                st_lock = locked_point_today.get("status_kunjungan", VISIT_STATUS_WAJIB)
                st.success(
                    f"🔒 **Titik LKK Terkunci Hari Ini:** **{locked_point_today['warkop']}** "
                    f"({locked_point_today['kecamatan']}) • **{st_lock}** • SPG sudah diizinkan menginput di titik ini."
                )
            else:
                st.warning(
                    "⚠️ **Titik LKK Belum Di-Save / Di-Lock.** Pilih Kecamatan & Warkop/LKK di bawah, "
                    "lalu klik **🔒 Save Titik LKK** agar SPG dapat mulai menginput."
                )
        with col_sync_2:
            st.markdown("<div style='height: 18px;'></div>", unsafe_allow_html=True)
            if st.button("🔄 Refresh", key="btn_refresh_sup_points", use_container_width=True):
                st.rerun()

        default_kec_idx = 0
        if locked_point_today and locked_point_today.get("kecamatan") in daftar_kecamatan_terjadwal:
            default_kec_idx = daftar_kecamatan_terjadwal.index(locked_point_today["kecamatan"])

        kecamatan_pilihan = st.selectbox(
            f"Kecamatan Tujuan ({st.session_state['kota_kab']})",
            options=daftar_kecamatan_terjadwal,
            index=default_kec_idx,
            help="Kecamatan difilter otomatis sesuai penugasan jadwal hari ini yang dikelola di menu admin.",
        )

        filter_kategori_w = st.radio(
            "Filter Kategori Warkop",
            options=["Semua", VISIT_STATUS_WAJIB, VISIT_STATUS_TIDAK_WAJIB],
            horizontal=True,
            key="sup_filter_kategori_warkop",
        )

        filtered_warkop_list = []
        if not df_master_excel.empty and col_kec_excel and col_warkop_excel:
            mask = (
                df_master_excel[col_kec_excel].astype(str).str.strip().str.lower()
                == str(kecamatan_pilihan).strip().lower()
            )
            filtered_df_warkop = df_master_excel[mask]
            if filtered_df_warkop.empty:
                filtered_df_warkop = df_master_excel.copy()
            raw_wrk_names = filtered_df_warkop[col_warkop_excel].dropna().astype(str).str.strip().tolist()
            seen_w = set()
            kc_cf = str(kecamatan_pilihan).strip().casefold()
            for w_item in raw_wrk_names:
                w_cf = w_item.casefold()
                if not w_item or w_cf in seen_w:
                    continue
                seen_w.add(w_cf)
                # Hilangkan warkop yang sudah disimpan datanya lewat Save Jumlah Kontak Konsumen hari ini
                if (kc_cf, w_cf) in saved_contact_pairs_today or w_cf in saved_contact_warkops_names:
                    continue
                st_item = get_warkop_visit_status(st.session_state["kota_kab"], kecamatan_pilihan, w_item, status_map_sup)
                if filter_kategori_w != "Semua" and st_item != filter_kategori_w:
                    continue
                filtered_warkop_list.append(w_item)

        if not filtered_warkop_list:
            st.info(
                f"ℹ️ Semua warkop pada kategori **{filter_kategori_w}** di **{kecamatan_pilihan}** "
                "sudah disimpan jumlah kontaknya hari ini (atau belum ada titik tersisa)."
            )
            nama_warkop_manual = ""
            status_warkop_terpilih = "-"
            alamat_warkop_terpilih = "-"
        else:
            default_w_idx = 0
            if locked_point_today and locked_point_today.get("warkop") in filtered_warkop_list:
                default_w_idx = filtered_warkop_list.index(locked_point_today["warkop"])

            nama_warkop_manual = st.selectbox(
                f"Warkop / LKK di {kecamatan_pilihan}",
                options=filtered_warkop_list,
                index=default_w_idx,
                format_func=lambda w_name: f"[{'WAJIB' if get_warkop_visit_status(st.session_state['kota_kab'], kecamatan_pilihan, w_name, status_map_sup) == VISIT_STATUS_WAJIB else 'OPSI'}] {w_name}",
                help="Menampilkan warkop yang belum dikunjungi & disimpan kontaknya hari ini.",
            )
            status_warkop_terpilih = get_warkop_visit_status(
                st.session_state["kota_kab"], kecamatan_pilihan, nama_warkop_manual, status_map_sup
            )
            alamat_warkop_terpilih = "-"
            if not df_master_excel.empty and col_warkop_excel and col_alamat_excel:
                match_row = df_master_excel[
                    df_master_excel[col_warkop_excel].astype(str).str.strip() == str(nama_warkop_manual).strip()
                ]
                if not match_row.empty:
                    alamat_warkop_terpilih = str(match_row.iloc[0][col_alamat_excel])

            if st.button("🔒 Save Titik LKK (Buka Akses Input SPG)", type="primary", use_container_width=True, key="btn_save_lock_lkk"):
                saved_lock = save_locked_lkk_point(
                    team_name=st.session_state["user_spg"],
                    point_info={
                        "kota": st.session_state["kota_kab"],
                        "kecamatan": str(kecamatan_pilihan).strip(),
                        "warkop": str(nama_warkop_manual).strip(),
                        "alamat": alamat_warkop_terpilih,
                        "status_kunjungan": status_warkop_terpilih,
                    },
                )
                if saved_lock:
                    st.success(
                        f"✅ Titik LKK **{str(nama_warkop_manual).strip()}** ({kecamatan_pilihan} • **{status_warkop_terpilih}**) berhasil di-save & di-lock! "
                        "SPG kini dapat menginput laporan di titik ini."
                    )
                    st.rerun()

        st.markdown(f"""
        <div class="address-box">
            📍 <b>Kecamatan:</b> {kecamatan_pilihan} &nbsp;|&nbsp; <b>Warkop / LKK:</b> {nama_warkop_manual or '(Tidak ada warkop tersisa / belum dipilih)'} &nbsp;|&nbsp; <b>Status:</b> {status_warkop_terpilih}<br/>
            🏠 <b>Alamat:</b> {alamat_warkop_terpilih}
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown(f"### 👀 Dashboard Monitoring & Entry Supervisi: {st.session_state['user_spg']} (Plat Mobil: {st.session_state['plat_mobil']})")

    sup_nonce = st.session_state.get("sup_kontak_nonce", 0)
    with st.form(f"form_entry_kontak_supervisi_{sup_nonce}"):
        st.markdown("#### 📝 Save Jumlah Kontak Konsumen Tim (Setelah SPG Selesai Jualan)")
        if not str(nama_warkop_manual).strip():
            st.warning("Pilih dan save Titik LKK terlebih dahulu sebelum menyimpan jumlah kontak konsumen.")
        jumlah_kontak_input = st.number_input(
            f"Jumlah Kontak Konsumen Tim di {nama_warkop_manual or 'Titik LKK'}",
            min_value=0,
            step=1,
            value=0,
            key=f"input_jumlah_kontak_sup_{sup_nonce}",
            help="Masukkan jumlah total kontak konsumen tim di titik LKK ini setelah SPG selesai jualan (bersifat tim, tidak dipecah per SPG/brand).",
        )
        btn_simpan_kontak = st.form_submit_button("💾 Save Jumlah Kontak Konsumen", type="primary")

        if btn_simpan_kontak:
            if not str(nama_warkop_manual).strip():
                st.error("❌ Gagal menyimpan kontak: Titik LKK belum dipilih/disimpan.")
            else:
                df_sup_db = load_supervisi_database()
                waktu_wib = datetime.utcnow() + timedelta(hours=7)
                warkop_saved_clean = str(nama_warkop_manual).strip()
                new_sup_row = {
                    "Waktu": waktu_wib.strftime("%Y-%m-%d %H:%M:%S"),
                    "Promotor": st.session_state["user_spg"],
                    "Plat_Mobil": st.session_state["plat_mobil"],
                    "Kota_Kab": st.session_state["kota_kab"],
                    "Kecamatan": kecamatan_pilihan,
                    "Warkop_LKK": warkop_saved_clean,
                    "Alamat_Warkop": alamat_warkop_terpilih,
                    "Jumlah_Kontak_Manual": int(jumlah_kontak_input),
                }
                df_sup_db = pd.concat([df_sup_db, pd.DataFrame([new_sup_row])], ignore_index=True)
                save_supervisi_database(df_sup_db)
                clear_locked_lkk_point(st.session_state["user_spg"])
                st.session_state["sup_kontak_nonce"] = sup_nonce + 1
                st.session_state["sup_last_saved_msg"] = (
                    f"✅ Berhasil menyimpan **{jumlah_kontak_input} kontak tim** untuk titik "
                    f"**{warkop_saved_clean}**! Warkop otomatis dihapus dari daftar pilihan hari ini."
                )
                st.rerun()

    if st.session_state.get("sup_last_saved_msg"):
        st.success(st.session_state.pop("sup_last_saved_msg"))

    # --- LIST WARKOP WAJIB KUNJUNG YANG BELUM DIKUNJUNGI DI BAWAH DASHBOARD SUPERVISI ---
    st.markdown("#### 📌 List Warkop Wajib Kunjung yang Belum Dikunjungi Hari Ini")
    df_wrk_all_sup = build_warkop_status_dataframe(df_master_excel, status_map_sup)
    unvisited_wajib_sup_rows = []
    if not df_wrk_all_sup.empty:
        wajib_sup_df = df_wrk_all_sup[
            (df_wrk_all_sup["Status Kunjungan"] == VISIT_STATUS_WAJIB)
            & (
                df_wrk_all_sup["Kecamatan"].astype(str).str.strip().str.casefold()
                == str(kecamatan_pilihan).strip().casefold()
            )
        ]
        for _, rw in wajib_sup_df.iterrows():
            nm_w = str(rw.get("Nama Warkop / LKK", "") or "").strip()
            kc_w = str(rw.get("Kecamatan", "") or "").strip()
            if (kc_w.casefold(), nm_w.casefold()) in saved_contact_pairs_today or nm_w.casefold() in saved_contact_warkops_names:
                continue
            unvisited_wajib_sup_rows.append({
                "Kota": rw.get("Kota", ""),
                "Kecamatan": kc_w,
                "Nama Warkop / LKK": nm_w,
                "Alamat Warkop / LKK": rw.get("Alamat Warkop / LKK", "-"),
                "Status Kunjungan": VISIT_STATUS_WAJIB,
            })

    if unvisited_wajib_sup_rows:
        st.dataframe(pd.DataFrame(unvisited_wajib_sup_rows), use_container_width=True, hide_index=True)
    else:
        st.success(f"✅ Semua warkop **Wajib Kunjung** di **{kecamatan_pilihan}** hari ini sudah dikunjungi & disimpan kontaknya.")

    st.markdown("---")

    df_all_db = load_database()
    df_sup_db = load_supervisi_database()

    df_current_team_spg = pd.DataFrame()
    if not df_all_db.empty and "Promotor" in df_all_db.columns:
        df_current_team_spg = df_all_db[df_all_db["Promotor"] == st.session_state["user_spg"]].copy()

    df_current_team_sup = pd.DataFrame()
    if not df_sup_db.empty and "Promotor" in df_sup_db.columns:
        df_current_team_sup = df_sup_db[df_sup_db["Promotor"] == st.session_state["user_spg"]].copy()

    today_str_sup = (datetime.utcnow() + timedelta(hours=7)).strftime("%Y-%m-%d")
    harga_konsumen_map = load_harga_konsumen()

    df_team_spg_today = pd.DataFrame()
    if not df_current_team_spg.empty:
        df_current_team_spg["Jumlah_Bungkus"] = pd.to_numeric(
            df_current_team_spg["Jumlah_Bungkus"], errors="coerce"
        ).fillna(0)
        df_current_team_spg["Harga_Konsumen"] = df_current_team_spg["Brand_Rokok"].apply(
            lambda b: get_harga_konsumen_brand(b, harga_konsumen_map)
        )
        df_current_team_spg["Total_Uang_Rp"] = (
            df_current_team_spg["Jumlah_Bungkus"] * df_current_team_spg["Harga_Konsumen"]
        ).astype(int)
        df_team_spg_today = df_current_team_spg[
            df_current_team_spg["Waktu"].astype(str).str.startswith(today_str_sup)
        ].copy()

    df_lkk_active_spg = pd.DataFrame()
    if not df_team_spg_today.empty and str(nama_warkop_manual).strip():
        df_lkk_active_spg = df_team_spg_today[
            df_team_spg_today["Warkop_LKK"].astype(str).str.strip() == str(nama_warkop_manual).strip()
        ]

    kontak_supervisi_team_lkk = 0
    if not df_current_team_sup.empty and str(nama_warkop_manual).strip():
        df_lkk_active_sup = df_current_team_sup[
            (df_current_team_sup["Warkop_LKK"].astype(str).str.strip() == str(nama_warkop_manual).strip())
            & (df_current_team_sup["Waktu"].astype(str).str.startswith(today_str_sup))
        ]
        if not df_lkk_active_sup.empty:
            kontak_supervisi_team_lkk = int(
                pd.to_numeric(df_lkk_active_sup["Jumlah_Kontak_Manual"], errors="coerce").fillna(0).sum()
            )

    total_bks_2spg_today = int(df_team_spg_today["Jumlah_Bungkus"].sum()) if not df_team_spg_today.empty else 0
    total_uang_2spg_today = int(df_team_spg_today["Total_Uang_Rp"].sum()) if not df_team_spg_today.empty else 0
    spg_2spg_today_list = (
        df_team_spg_today["Nama_SPG"].dropna().astype(str).str.strip().unique().tolist()
        if not df_team_spg_today.empty else []
    )

    st.info(
        f"💵 **Jumlah Uang Terkumpul Hari Ini ({today_str_sup}) — Penjualan 2 SPG:** "
        f"**Rp {total_uang_2spg_today:,}** ({total_bks_2spg_today:,} bungkus • "
        f"SPG: {', '.join(spg_2spg_today_list) if spg_2spg_today_list else 'Belum ada penjualan'})"
    )

    col_mon1, col_mon2, col_mon3, col_mon4 = st.columns(4)
    with col_mon1:
        st.markdown(f'<div class="dashboard-card"><div class="card-value">{kontak_supervisi_team_lkk}</div><div class="card-label">Kontak Supervisi Team</div></div>', unsafe_allow_html=True)
    with col_mon2:
        total_konsumen_beli = len(df_lkk_active_spg)
        st.markdown(f'<div class="dashboard-card"><div class="card-value">{total_konsumen_beli}</div><div class="card-label">Konsumen Beli (LKK Ini)</div></div>', unsafe_allow_html=True)
    with col_mon3:
        st.markdown(f'<div class="dashboard-card"><div class="card-value" style="color: #16A34A;">Rp {total_uang_2spg_today:,}</div><div class="card-label">Uang Terkumpul 2 SPG Hari Ini</div></div>', unsafe_allow_html=True)
    with col_mon4:
        spg_list_str = ", ".join(spg_2spg_today_list) if spg_2spg_today_list else "Belum ada SPG"
        st.markdown(f'<div class="dashboard-card"><div class="card-value" style="font-size: 1.05rem; padding-top: 6px;">{spg_list_str}</div><div class="card-label">SPG Bertugas Hari Ini</div></div>', unsafe_allow_html=True)

    st.markdown("---")
    render_rekapitulasi_penjualan_report(
        team_name=st.session_state["user_spg"],
        target_date_str=today_str_sup,
        allow_edit_stok=True,
    )

    st.markdown("---")
    st.markdown(f"#### 📊 Rekapitulasi Combine Per Titik LKK ({st.session_state['user_spg']})")

    df_rekap_sup = pd.DataFrame(columns=["Kecamatan", "Warkop_LKK", "Kontak_Supervisi_Team"])
    if not df_current_team_sup.empty:
        df_current_team_sup["Jumlah_Kontak_Manual"] = pd.to_numeric(df_current_team_sup["Jumlah_Kontak_Manual"], errors="coerce").fillna(0).astype(int)
        df_rekap_sup = (
            df_current_team_sup.groupby(["Kecamatan", "Warkop_LKK"])
            .agg(Kontak_Supervisi_Team=("Jumlah_Kontak_Manual", "sum"))
            .reset_index()
        )

    df_rekap_spg = pd.DataFrame(columns=["Kecamatan", "Warkop_LKK", "Alamat_Warkop", "Jumlah_SPG_Bertugas", "Konsumen_Beli", "Total_Omset_Bungkus", "Total_Uang_Rp"])
    if not df_current_team_spg.empty:
        if "Total_Uang_Rp" not in df_current_team_spg.columns:
            hmap_rekap = load_harga_konsumen()
            df_current_team_spg["Jumlah_Bungkus"] = pd.to_numeric(df_current_team_spg["Jumlah_Bungkus"], errors="coerce").fillna(0)
            df_current_team_spg["Total_Uang_Rp"] = (
                df_current_team_spg["Jumlah_Bungkus"]
                * df_current_team_spg["Brand_Rokok"].apply(lambda b: get_harga_konsumen_brand(b, hmap_rekap))
            ).astype(int)
        df_rekap_spg = (
            df_current_team_spg.groupby(["Kecamatan", "Warkop_LKK", "Alamat_Warkop"])
            .agg(
                Jumlah_SPG_Bertugas=("Nama_SPG", lambda x: ", ".join(x.dropna().unique())),
                Konsumen_Beli=("Nama_Konsumen", "count"),
                Total_Omset_Bungkus=("Jumlah_Bungkus", "sum"),
                Total_Uang_Rp=("Total_Uang_Rp", "sum"),
            )
            .reset_index()
        )

    if not df_rekap_sup.empty:
        if df_rekap_spg.empty:
            df_combine_rekap = df_rekap_sup.copy()
            df_combine_rekap["Jumlah_SPG_Bertugas"] = "-"
            df_combine_rekap["Konsumen_Beli"] = 0
            df_combine_rekap["Total_Omset_Bungkus"] = 0
            df_combine_rekap["Total_Uang_Rp"] = 0
            df_combine_rekap["Alamat_Warkop"] = "-"
        else:
            df_combine_rekap = pd.merge(df_rekap_sup, df_rekap_spg, on=["Kecamatan", "Warkop_LKK"], how="left").fillna({
                "Kontak_Supervisi_Team": 0,
                "Konsumen_Beli": 0,
                "Total_Omset_Bungkus": 0,
                "Total_Uang_Rp": 0,
                "Jumlah_SPG_Bertugas": "-",
                "Alamat_Warkop": "-",
            })

        df_combine_rekap["Kontak_Supervisi_Team"] = df_combine_rekap["Kontak_Supervisi_Team"].astype(int)
        df_combine_rekap["Konsumen_Beli"] = df_combine_rekap["Konsumen_Beli"].astype(int)
        df_combine_rekap["Total_Omset_Bungkus"] = df_combine_rekap["Total_Omset_Bungkus"].astype(int)
        df_combine_rekap["Total_Uang_Rp"] = df_combine_rekap["Total_Uang_Rp"].astype(int)
        df_combine_rekap = df_combine_rekap[
            ["Kecamatan", "Warkop_LKK", "Alamat_Warkop", "Jumlah_SPG_Bertugas", "Kontak_Supervisi_Team", "Konsumen_Beli", "Total_Omset_Bungkus", "Total_Uang_Rp"]
        ].sort_values(by="Total_Omset_Bungkus", ascending=False)
        st.dataframe(df_combine_rekap, use_container_width=True)
    else:
        st.info("Titik LKK akan tampil di rekap setelah Supervisi menginput jumlah kontak.")

    st.markdown("#### 📑 Log Detail Transaksi Konsumen Beli (SPG) di Warkop Ini")
    if not df_lkk_active_spg.empty:
        st.dataframe(df_lkk_active_spg.drop(columns=["Waktu", "Promotor", "Plat_Mobil"], errors="ignore"), use_container_width=True)
    else:
        st.info(f"Belum ada data konsumen beli masuk untuk titik Warkop / LKK '{nama_warkop_manual or '-'}'.")

    st.stop()

# ====================================================
# MODE SPG (HEADER DI ATAS SENDIRI, FORM INPUT, TITIK LKK HIDE/UNHIDE DEFAULT HIDE)
# ====================================================
today_wib_spg = (datetime.utcnow() + timedelta(hours=7)).date()
today_str_spg = today_wib_spg.strftime("%Y-%m-%d")
sektor_aktif_spg = locked_point_today["kecamatan"] if locked_point_today else st.session_state.get("sektor_terjadwal_login", "")
personnel_spg_today = get_scheduled_personnel_for_team(
    st.session_state["user_spg"],
    today_wib_spg,
    selected_kecamatan=sektor_aktif_spg,
)
daftar_spg_terjadwal = personnel_spg_today.get("spg_all", []) or st.session_state.get("spg_terjadwal_list", [])
spg_locked_session = str(st.session_state.get("spg_authenticated_name") or "").strip()

if spg_locked_session:
    nama_spg_manual = spg_locked_session
elif daftar_spg_terjadwal:
    nama_spg_manual = daftar_spg_terjadwal[0]
else:
    daftar_master_spg = load_master_spgs()
    nama_spg_manual = daftar_master_spg[0] if daftar_master_spg else "SPG"

if locked_point_today:
    kecamatan_pilihan = locked_point_today["kecamatan"] or "-"
    nama_warkop_manual = locked_point_today["warkop"]
    alamat_warkop_terpilih = locked_point_today["alamat"]
    status_warkop_terpilih = locked_point_today.get("status_kunjungan", VISIT_STATUS_WAJIB)
else:
    kecamatan_pilihan = "-"
    nama_warkop_manual = ""
    alamat_warkop_terpilih = "-"
    status_warkop_terpilih = "-"

has_locked_lkk = locked_point_today is not None and str(nama_warkop_manual).strip() != ""

# --- 1. HEADER TETAP DI ATAS SENDIRI ---
col_banner, col_logout = st.columns([0.8, 0.2])
with col_banner:
    spg_sesi_aktif = st.session_state.get("spg_authenticated_name", "").strip()
    spg_list_aktif = st.session_state.get("spg_terjadwal_list", [])
    personel_badge = f" &nbsp;•&nbsp; 👩‍💼 SPG Terkunci: <b>{spg_sesi_aktif or (', '.join(spg_list_aktif) if spg_list_aktif else nama_spg_manual)}</b>"
    st.markdown(
        f"""
        <div class="user-banner">
            <div class="user-banner-title">
                <span>👤 {st.session_state['user_spg']}</span>
                <span class="badge-mode">📝 SPG</span>
            </div>
            <div class="user-banner-sub">
                🚗 Plat: <b>{st.session_state['plat_mobil']}</b> &nbsp;•&nbsp; 🏙️ Wilayah: <b>{st.session_state['kota_kab']}</b>{personel_badge}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with col_logout:
    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
    if st.button("🚪 Keluar", use_container_width=True):
        st.session_state["logged_in"] = False
        st.session_state["spg_authenticated_name"] = ""
        st.session_state["show_titik_lkk_spg"] = False
        st.rerun()

# --- 2. FORM INPUT KONSUMEN ---
if not has_locked_lkk:
    st.error(
        "🔒 **Form Input SPG Terkunci:** Supervisi belum memilih dan menyimpan (**Save Titik LKK**) titik lokasi LKK hari ini. "
        "Silakan tunggu Supervisi me-lock titik LKK lalu tampilkan **📍 Titik Kunjungan Lapangan** di bawah untuk menekan **🔄 Refresh**."
    )
elif is_inside_geofence and str(nama_spg_manual).strip() != "":
    if st.session_state.get("spg_last_saved_msg"):
        st.balloons()
        st.success(st.session_state.pop("spg_last_saved_msg"))

    spg_nonce = st.session_state.get("spg_form_nonce", 0)
    with st.form(f"form_laporan_spg_{spg_nonce}"):
        st.markdown("### 📝 Form Input Laporan Konsumen")
        st.caption(
            f"Team: **{st.session_state['user_spg']}** • SPG: **{str(nama_spg_manual).strip()}** • "
            f"Titik Terkunci: **{str(nama_warkop_manual).strip()}**"
        )

        all_master_brands = load_master_brands()
        team_brands_map = load_master_team_brands()
        team_names_map = load_master_team_names()
        allowed_brands_for_team = resolve_team_allowed_brands(
            team_name=st.session_state["user_spg"],
            all_brands=all_master_brands,
            team_brands_map=team_brands_map,
            team_names_map=team_names_map,
            prefer_keyword_match=True,
        )
        if not allowed_brands_for_team:
            allowed_brands_for_team = all_master_brands

        default_brand_idx = (
            allowed_brands_for_team.index(st.session_state["draft_brand"])
            if st.session_state.get("draft_brand") in allowed_brands_for_team
            else 0
        )
        gender_options = ["L", "P"]
        default_gender_idx = (
            gender_options.index(st.session_state["draft_gender"])
            if st.session_state.get("draft_gender") in gender_options
            else 0
        )
        age_options = ["", "18-24", "25-30", "31-35", "36-44", "45+"]
        default_age_idx = (
            age_options.index(st.session_state["draft_range_umur"])
            if st.session_state.get("draft_range_umur") in age_options
            else 0
        )

        col_f1, col_f2 = st.columns([1.3, 0.7])
        with col_f1:
            brand_entry = st.selectbox(
                "🚬 Brand Rokok",
                options=allowed_brands_for_team,
                index=default_brand_idx,
                key=f"spg_brand_{spg_nonce}",
                help="Daftar merek rokok disesuaikan dengan alokasi Master Team Admin",
            )
        with col_f2:
            jumlah_bungkus = st.number_input(
                "📦 Jumlah Bungkus",
                min_value=0,
                step=1,
                value=int(st.session_state.get("draft_bungkus", 0) or 0),
                key=f"spg_bungkus_{spg_nonce}",
            )

        nama_konsumen = st.text_input(
            "👤 Nama Konsumen",
            value=st.session_state["draft_konsumen"],
            placeholder="Masukkan nama konsumen",
            key=f"spg_konsumen_{spg_nonce}",
        )

        col_g1, col_g2 = st.columns(2)
        with col_g1:
            gender_entry = st.radio(
                "⚧️ Gender",
                gender_options,
                index=default_gender_idx,
                horizontal=True,
                key=f"spg_gender_{spg_nonce}",
            )
        with col_g2:
            range_umur_entry = st.selectbox(
                "🎂 Range Umur",
                options=age_options,
                index=default_age_idx,
                format_func=lambda x: "-- Pilih Range Umur --" if x == "" else x,
                key=f"spg_umur_{spg_nonce}",
            )

        col_c1, col_c2 = st.columns(2)
        with col_c1:
            nohp_entry = st.text_input(
                "📱 No HP",
                value=st.session_state["draft_nohp"],
                placeholder="081234567890",
                key=f"spg_nohp_{spg_nonce}",
            )
        with col_c2:
            instagram_input = st.text_input(
                "📸 Instagram",
                value=st.session_state["draft_ig"],
                placeholder="username_ig",
                key=f"spg_ig_{spg_nonce}",
            )

        rokok_asal_bumo = st.text_input(
            "🔄 Rokok Asal (BUMO)",
            value=st.session_state["draft_bumo"],
            placeholder="Merk rokok yang biasa dikonsumsi sebelumnya",
            key=f"spg_bumo_{spg_nonce}",
        )

        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            btn_save_draft = st.form_submit_button("💾 Simpan Draft", type="secondary", use_container_width=True)
        with col_btn2:
            btn_kirim = st.form_submit_button("🚀 Kirim Laporan", type="primary", use_container_width=True)

        if btn_save_draft:
            st.session_state["draft_brand"] = brand_entry
            st.session_state["draft_gender"] = gender_entry
            st.session_state["draft_range_umur"] = range_umur_entry
            st.session_state["draft_konsumen"] = nama_konsumen
            st.session_state["draft_nohp"] = nohp_entry
            st.session_state["draft_ig"] = instagram_input
            st.session_state["draft_bungkus"] = jumlah_bungkus
            st.session_state["draft_bumo"] = rokok_asal_bumo
            st.info("💾 Draft laporan berhasil diamankan ke memori sesi sementara!")

        if btn_kirim:
            if not nama_konsumen.strip():
                st.warning("Mohon isi nama konsumen.")
            elif int(jumlah_bungkus) <= 0:
                st.warning("Jumlah bungkus harus lebih dari 0.")
            else:
                ig_formatted = f"@{instagram_input.strip().lstrip('@')}" if instagram_input.strip() else "-"
                waktu_wib = datetime.utcnow() + timedelta(hours=7)
                data_baru = {
                    "Waktu": waktu_wib.strftime("%Y-%m-%d %H:%M:%S"),
                    "Promotor": st.session_state["user_spg"],
                    "Plat_Mobil": st.session_state["plat_mobil"],
                    "Nama_SPG": str(nama_spg_manual).strip(),
                    "Kota_Kab": st.session_state["kota_kab"],
                    "Kecamatan": kecamatan_pilihan,
                    "Warkop_LKK": str(nama_warkop_manual).strip(),
                    "Alamat_Warkop": alamat_warkop_terpilih,
                    "Brand_Rokok": brand_entry,
                    "Nama_Konsumen": nama_konsumen.strip(),
                    "Gender": gender_entry,
                    "Range_Umur": range_umur_entry,
                    "No_HP": nohp_entry.strip(),
                    "Instagram": ig_formatted,
                    "Jumlah_Bungkus": int(jumlah_bungkus),
                    "Rokok_Asal_BUMO": rokok_asal_bumo.strip(),
                    "Latitude": user_lat,
                    "Longitude": user_lon,
                }
                df_all = load_database()
                df_new_row = pd.DataFrame([data_baru])
                df_all = pd.concat([df_all, df_new_row], ignore_index=True)
                save_database(df_all)

                st.session_state["draft_konsumen"] = ""
                st.session_state["draft_nohp"] = ""
                st.session_state["draft_ig"] = ""
                st.session_state["draft_bungkus"] = 0
                st.session_state["draft_bumo"] = ""
                st.session_state["draft_brand"] = ""
                st.session_state["draft_gender"] = "L"
                st.session_state["draft_range_umur"] = ""
                st.session_state["spg_form_nonce"] = spg_nonce + 1
                st.session_state["spg_last_saved_msg"] = (
                    f"Laporan konsumen '{nama_konsumen.strip()}' ({jumlah_bungkus} bks {brand_entry}) berhasil disimpan!"
                )
                st.rerun()

# --- 3. BLOK TITIK KUNJUNGAN LAPANGAN (DEFAULT HIDE / UNHIDE) ---
st.markdown("---")
col_titik_hdr, col_titik_toggle = st.columns([0.65, 0.35])
with col_titik_hdr:
    st.markdown('<div class="section-title" style="margin:0;">📍 Titik Kunjungan Lapangan</div>', unsafe_allow_html=True)
with col_titik_toggle:
    is_titik_shown = bool(st.session_state.get("show_titik_lkk_spg", False))
    toggle_label = "🙈 Hide Titik LKK" if is_titik_shown else "👁️ Unhide Titik LKK"
    if st.button(toggle_label, key="btn_toggle_titik_lkk_spg", use_container_width=True):
        st.session_state["show_titik_lkk_spg"] = not is_titik_shown
        st.rerun()

if st.session_state.get("show_titik_lkk_spg", False):
    with st.container(border=True):
        col_spg_ref1, col_spg_ref2 = st.columns([0.78, 0.22])
        with col_spg_ref1:
            if has_locked_lkk:
                st.success(
                    f"🔒 **Titik LKK Terkunci oleh Supervisi:** **{nama_warkop_manual}** "
                    f"({kecamatan_pilihan} • **{status_warkop_terpilih}**)"
                )
            else:
                st.warning(
                    "⚠️ **Belum ada Titik LKK yang di-save / di-lock Supervisi hari ini.** "
                    "Klik **🔄 Refresh** setelah Supervisi menyimpan Titik LKK."
                )
        with col_spg_ref2:
            st.markdown("<div style='height: 18px;'></div>", unsafe_allow_html=True)
            if st.button("🔄 Refresh", key="btn_refresh_spg_locked_lkk", use_container_width=True):
                st.rerun()

        st.markdown(f"""
        <div class="address-box">
            📍 <b>Kecamatan:</b> {kecamatan_pilihan} &nbsp;|&nbsp; <b>Warkop / LKK:</b> {nama_warkop_manual or '(Belum di-lock Supervisi)'} &nbsp;|&nbsp; <b>Status:</b> {status_warkop_terpilih}<br/>
            🏠 <b>Alamat:</b> {alamat_warkop_terpilih}
        </div>
        """, unsafe_allow_html=True)

# --- 4. RINGKASAN PERFORMA ---
st.markdown("---")
st.markdown(f"### 📈 Ringkasan Performa: {st.session_state['user_spg']} ({nama_spg_manual or 'Semua SPG'})")

df_all = load_database()
if not df_all.empty and "Promotor" in df_all.columns:
    df_user = df_all[df_all["Promotor"] == st.session_state["user_spg"]].copy()
else:
    df_user = pd.DataFrame(columns=EXPECTED_COLUMNS)

if not df_user.empty:
    df_user["Waktu_Dt"] = pd.to_datetime(df_user["Waktu"], errors="coerce")
    df_user["Tanggal"] = df_user["Waktu_Dt"].dt.strftime("%d-%m-%Y")
    df_user = add_custom_week_columns(df_user, "Waktu_Dt")
    df_user["Jumlah_Bungkus"] = pd.to_numeric(df_user["Jumlah_Bungkus"], errors="coerce").fillna(0)

    today_dt = datetime.utcnow() + timedelta(hours=7)
    today_str = today_dt.strftime("%d-%m-%Y")
    current_week_label, _ = get_custom_week_info(today_dt)
    current_month_str = today_dt.strftime("%m-%Y")

    df_today_u = df_user[df_user["Tanggal"] == today_str].copy()
    omset_hari_ini_u = int(df_today_u["Jumlah_Bungkus"].sum())
    konsumen_hari_ini_u = len(df_today_u)

    if not df_today_u.empty:
        df_today_u_lb = (
            df_today_u.groupby(["Tanggal", "Periode_Minggu", "Promotor", "Kota_Kab", "Brand_Rokok"])
            .agg(Total_Omset_Team=("Jumlah_Bungkus", "sum"))
            .reset_index()
        )
        df_today_u_lb["Brand_Rokok_Clean"] = df_today_u_lb["Brand_Rokok"].apply(clean_brand_target_name)
        df_today_u_lb = (
            df_today_u_lb.groupby(["Tanggal", "Periode_Minggu", "Promotor", "Kota_Kab", "Brand_Rokok_Clean"])
            .agg(Total_Omset_Team=("Total_Omset_Team", "sum"))
            .reset_index()
            .rename(columns={"Brand_Rokok_Clean": "Brand_Rokok"})
        )
        df_today_u_lb["Target_Team"] = df_today_u_lb["Brand_Rokok"].apply(
            lambda brand: get_target_for_brand(brand, "target_team", 50)
        )
        target_hari_ini_u = int(df_today_u_lb["Target_Team"].sum())
    else:
        target_hari_ini_u = 100

    if target_hari_ini_u <= 0:
        target_hari_ini_u = 100

    persen_pencapaian_u = int((omset_hari_ini_u / target_hari_ini_u) * 100) if target_hari_ini_u > 0 else 0

    df_week_u = df_user[df_user["Periode_Minggu"] == current_week_label]
    omset_minggu_ini_u = int(df_week_u["Jumlah_Bungkus"].sum())
    konsumen_minggu_ini_u = len(df_week_u)

    df_user["Bulan_Tahun"] = df_user["Waktu_Dt"].dt.strftime("%m-%Y")
    df_month_u = df_user[df_user["Bulan_Tahun"] == current_month_str]
    omset_bulan_ini_u = int(df_month_u["Jumlah_Bungkus"].sum())
    konsumen_bulan_ini_u = len(df_month_u)

    kpi_u1, kpi_u2, kpi_u3 = st.columns(3)
    with kpi_u1:
        st.markdown(f"""
        <div class="dashboard-card">
            <div>
                <div class="card-value">{omset_hari_ini_u:,} bks</div>
                <div class="card-subtext">dari {target_hari_ini_u} target bks</div>
            </div>
            <div class="card-label">Omset Hari Ini</div>
        </div>
        """, unsafe_allow_html=True)
    with kpi_u2:
        bar_w_u = min(persen_pencapaian_u, 100)
        st.markdown(f"""
        <div class="dashboard-card">
            <div>
                <div class="card-value-green">{persen_pencapaian_u}%</div>
                <div class="progress-bar-container">
                    <div class="progress-bar-fill" style="width: {bar_w_u}%;"></div>
                </div>
            </div>
            <div class="card-label">Pencapaian Omset Hari Ini</div>
        </div>
        """, unsafe_allow_html=True)
    with kpi_u3:
        st.markdown(f"""
        <div class="dashboard-card">
            <div>
                <div class="card-value">{konsumen_hari_ini_u:,}</div>
                <div class="card-subtext" style="opacity: 0;">-</div>
            </div>
            <div class="card-label">Konsumen Beli Hari Ini</div>
        </div>
        """, unsafe_allow_html=True)

    kpi_u4, kpi_u5, kpi_u6 = st.columns(3)
    with kpi_u4:
        st.markdown(f"""
        <div class="dashboard-card">
            <div>
                <div class="card-value">{omset_minggu_ini_u:,} bks</div>
                <div class="card-subtext">{konsumen_minggu_ini_u:,} Konsumen Minggu Ini</div>
            </div>
            <div class="card-label">Omset Minggu Ini</div>
        </div>
        """, unsafe_allow_html=True)
    with kpi_u5:
        st.markdown(f"""
        <div class="dashboard-card">
            <div>
                <div class="card-value">{omset_bulan_ini_u:,} bks</div>
                <div class="card-subtext" style="opacity: 0;">-</div>
            </div>
            <div class="card-label">Omset Bulan Ini</div>
        </div>
        """, unsafe_allow_html=True)
    with kpi_u6:
        st.markdown(f"""
        <div class="dashboard-card">
            <div>
                <div class="card-value">{konsumen_bulan_ini_u:,}</div>
                <div class="card-subtext" style="opacity: 0;">-</div>
            </div>
            <div class="card-label">Konsumen Beli Bulan Ini</div>
        </div>
        """, unsafe_allow_html=True)

    all_weeks_u = sorted(df_user["Periode_Minggu"].dropna().unique().tolist(), reverse=True)
    all_dates_u = sorted(df_user["Tanggal"].dropna().unique().tolist(), reverse=True)
    all_spgs_u = sorted(df_user["Nama_SPG"].dropna().unique().tolist())

    st.markdown("---")
    st.markdown("### 👩‍💼 Pencapaian Per SPG (Berdasarkan Target SPG)")

    col_spg_w, col_spg_tgl, col_spg_nm = st.columns(3)
    with col_spg_w:
        filter_spg_week = st.multiselect("Filter Periode Minggu (Pencapaian SPG)", options=all_weeks_u, default=all_weeks_u, key="user_spg_week")
    with col_spg_tgl:
        filter_spg_tgl = st.multiselect("Filter Tanggal (Pencapaian SPG)", options=all_dates_u, default=all_dates_u, key="user_spg_tgl")
    with col_spg_nm:
        filter_spg_nm = st.multiselect("Filter Nama SPG (Pencapaian SPG)", options=all_spgs_u, default=all_spgs_u, key="user_spg_nm")

    df_spg_filtered = df_user.copy()
    if filter_spg_week:
        df_spg_filtered = df_spg_filtered[df_spg_filtered["Periode_Minggu"].isin(filter_spg_week)]
    if filter_spg_tgl:
        df_spg_filtered = df_spg_filtered[df_spg_filtered["Tanggal"].isin(filter_spg_tgl)]
    if filter_spg_nm:
        df_spg_filtered = df_spg_filtered[df_spg_filtered["Nama_SPG"].isin(filter_spg_nm)]

    if not df_spg_filtered.empty:
        df_spg_achievement = (
            df_spg_filtered.groupby(["Tanggal", "Periode_Minggu", "Promotor", "Nama_SPG", "Kota_Kab", "Brand_Rokok"])
            .agg(Total_Omset_SPG=("Jumlah_Bungkus", "sum"), Total_Konsumen_Beli=("Nama_Konsumen", "count"))
            .reset_index()
        )
        df_spg_achievement["Brand_Rokok_Clean"] = df_spg_achievement["Brand_Rokok"].apply(clean_brand_target_name)
        df_spg_achievement = (
            df_spg_achievement.groupby(["Tanggal", "Periode_Minggu", "Promotor", "Nama_SPG", "Kota_Kab", "Brand_Rokok_Clean"])
            .agg(Total_Omset_SPG=("Total_Omset_SPG", "sum"), Total_Konsumen_Beli=("Total_Konsumen_Beli", "sum"))
            .reset_index()
            .rename(columns={"Brand_Rokok_Clean": "Brand_Rokok"})
        )
        df_spg_achievement["Target_SPG"] = df_spg_achievement["Brand_Rokok"].apply(
            lambda brand: get_target_for_brand(brand, "target_spg", 25)
        )
        df_spg_achievement["Status_Target_SPG"] = df_spg_achievement.apply(
            lambda r: "Achieved" if r["Total_Omset_SPG"] >= r["Target_SPG"] else "Not Achieved",
            axis=1
        )
        cols_spg_order = ["Tanggal", "Periode_Minggu", "Promotor", "Nama_SPG", "Kota_Kab", "Brand_Rokok", "Total_Omset_SPG", "Total_Konsumen_Beli", "Target_SPG", "Status_Target_SPG"]
        df_spg_achievement = df_spg_achievement[[c for c in cols_spg_order if c in df_spg_achievement.columns]]

        st.dataframe(df_spg_achievement.style.map(style_status_target, subset=["Status_Target_SPG"]), use_container_width=True)
    else:
        st.info("Tidak ada data untuk filter Pencapaian SPG yang dipilih.")

    st.markdown("---")
    st.markdown("### 🏆 Pencapaian Team SPG (Berdasarkan Target Team)")

    col_tm_w, col_tm_tgl = st.columns(2)
    with col_tm_w:
        filter_tm_week = st.multiselect("Filter Periode Minggu (Pencapaian Team)", options=all_weeks_u, default=all_weeks_u, key="user_tm_week")
    with col_tm_tgl:
        filter_tm_tgl = st.multiselect("Filter Tanggal (Pencapaian Team)", options=all_dates_u, default=all_dates_u, key="user_tm_tgl")

    df_tm_filtered = df_user.copy()
    if filter_tm_week:
        df_tm_filtered = df_tm_filtered[df_tm_filtered["Periode_Minggu"].isin(filter_tm_week)]
    if filter_tm_tgl:
        df_tm_filtered = df_tm_filtered[df_tm_filtered["Tanggal"].isin(filter_tm_tgl)]

    if not df_tm_filtered.empty:
        df_tm_achievement = (
            df_tm_filtered.groupby(["Tanggal", "Periode_Minggu", "Promotor", "Kota_Kab", "Brand_Rokok"])
            .agg(Total_Omset_Team=("Jumlah_Bungkus", "sum"), Total_Konsumen_Beli=("Nama_Konsumen", "count"))
            .reset_index()
        )
        df_tm_achievement["Brand_Rokok_Clean"] = df_tm_achievement["Brand_Rokok"].apply(clean_brand_target_name)
        df_tm_achievement = (
            df_tm_achievement.groupby(["Tanggal", "Periode_Minggu", "Promotor", "Kota_Kab", "Brand_Rokok_Clean"])
            .agg(Total_Omset_Team=("Total_Omset_Team", "sum"), Total_Konsumen_Beli=("Total_Konsumen_Beli", "sum"))
            .reset_index()
            .rename(columns={"Brand_Rokok_Clean": "Brand_Rokok"})
        )
        df_tm_achievement["Target_Team"] = df_tm_achievement["Brand_Rokok"].apply(
            lambda brand: get_target_for_brand(brand, "target_team", 50)
        )
        df_tm_achievement["Status_Target_Team"] = df_tm_achievement.apply(
            lambda r: "Achieved" if r["Total_Omset_Team"] >= r["Target_Team"] else "Not Achieved",
            axis=1
        )
        cols_tm_order = ["Tanggal", "Periode_Minggu", "Promotor", "Kota_Kab", "Brand_Rokok", "Total_Omset_Team", "Total_Konsumen_Beli", "Target_Team", "Status_Target_Team"]
        df_tm_achievement = df_tm_achievement[[c for c in cols_tm_order if c in df_tm_achievement.columns]]

        st.dataframe(df_tm_achievement.style.map(style_status_target, subset=["Status_Target_Team"]), use_container_width=True)
    else:
        st.info("Tidak ada data untuk filter Pencapaian Team yang dipilih.")

    st.markdown("---")
    st.markdown("### 📑 Riwayat Laporan Anda")
    st.dataframe(df_user.drop(columns=["Waktu_Dt", "Periode_Minggu", "Tanggal", "Bulan_Tahun"], errors="ignore").tail(20), use_container_width=True)
else:
    st.info("Belum ada data laporan untuk akun ini.")

st.markdown("""
<div class="footer-note">
    © 2026 Tumarso Monitoring System
</div>
""", unsafe_allow_html=True)
