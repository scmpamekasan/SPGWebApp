from team_brand_sync import (
    resolve_team_allowed_brands,
    sync_masters_from_schedule_upload,
)

import json
import re
from datetime import date, timedelta
from io import BytesIO
import os

import openpyxl
import pandas as pd
import streamlit as st


SCHEDULE_FILE = "Jadwal_SPG_1.1.xlsx"
SCHEDULE_DETAIL_FILE = "jadwal_spg_detail.json"
TEAM_NAMES_FILE = "master_nama_team.json"
TEAM_BRANDS_FILE = "master_team_brand.json"
BRANDS_FILE = "master_brand_rokok.json"
VEHICLES_FILE = "master_plat_kendaraan.json"
MASTER_SPG_FILE = "master_spg.json"
CITIES = ["Surabaya", "Gresik"]
WEEKDAYS = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
DEFAULT_VEHICLES = ["L 1234 ABC"]
DEFAULT_BRANDS = [
    "D.Super 12", "D.76 Apel", "D.76 Apel Royal", "Black Matcha K12",
    "Djarum 76 Aksara", "Black Matcha Siro", "Black Matcha Kuro",
]

FLAT_SCHEDULE_REQUIRED_COLS = {
    "tanggal",
    "nama team",
    "nama spg 1",
    "nama spg 2",
    "nama supervisi",
    "kendaraan / plat nomor",
    "kota",
    "sektor",
}


def _file_mtime(path: str) -> float:
    return os.path.getmtime(path) if os.path.exists(path) else 0.0


@st.cache_data(show_spinner=False)
def _cached_read_excel_file(path: str, mtime: float) -> pd.DataFrame:
    frame = pd.read_excel(path)
    frame.columns = [str(column).strip() for column in frame.columns]
    return frame


@st.cache_data(show_spinner=False)
def _cached_read_json_file(path: str, mtime: float):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def load_schedule():
    if not os.path.exists(SCHEDULE_FILE):
        return pd.DataFrame(columns=["Kota", "Kecamatan"])
    try:
        return _cached_read_excel_file(SCHEDULE_FILE, _file_mtime(SCHEDULE_FILE)).copy()
    except Exception as exc:
        st.error(f"Gagal membaca {SCHEDULE_FILE}: {exc}")
        return pd.DataFrame(columns=["Kota", "Kecamatan"])


def save_schedule(frame):
    try:
        frame.to_excel(SCHEDULE_FILE, index=False)
        st.cache_data.clear()
        return True
    except Exception as exc:
        st.error(f"Gagal menyimpan {SCHEDULE_FILE}: {exc}")
        return False


def read_json(path, fallback):
    if os.path.exists(path):
        try:
            data = _cached_read_json_file(path, _file_mtime(path))
            if data is not None:
                return data
        except (OSError, ValueError, TypeError):
            pass
    return fallback


def load_details():
    details = read_json(SCHEDULE_DETAIL_FILE, {})
    return dict(details) if isinstance(details, dict) else {}


def save_details(details):
    try:
        with open(SCHEDULE_DETAIL_FILE, "w", encoding="utf-8") as file:
            json.dump(details, file, ensure_ascii=False, indent=2)
        st.cache_data.clear()
        return True
    except (OSError, TypeError, ValueError) as exc:
        st.error(f"Gagal menyimpan detail jadwal: {exc}")
        return False


def team_mapping():
    defaults = {f"Team SPG {number}": f"Team SPG {number}" for number in range(1, 21)}
    if not os.path.exists(TEAM_NAMES_FILE):
        return defaults
    mapping = read_json(TEAM_NAMES_FILE, {})
    if isinstance(mapping, dict):
        defaults.update({key: str(mapping.get(key, key)).strip() for key in defaults})
    return defaults


def team_choices():
    return [team for team in team_mapping().values() if team]


def schedule_team_names(frame, date_cols):
    names = []
    seen = set()
    for _, row in frame.iterrows():
        for date_col in date_cols:
            value = row.get(date_col)
            if not is_active(value):
                continue
            name = str(value).strip()
            normalized = name.casefold()
            if normalized not in seen:
                seen.add(normalized)
                names.append(name)
    return names


def brands_for_team(team):
    all_brands = read_json(BRANDS_FILE, DEFAULT_BRANDS)
    if not isinstance(all_brands, list) or not all_brands:
        all_brands = DEFAULT_BRANDS
    allocations = read_json(TEAM_BRANDS_FILE, {})
    names_map = team_mapping()
    return resolve_team_allowed_brands(
        team_name=team,
        all_brands=all_brands,
        team_brands_map=allocations if isinstance(allocations, dict) else {},
        team_names_map=names_map,
        prefer_keyword_match=True,
    )


def vehicle_choices():
    vehicles = read_json(VEHICLES_FILE, DEFAULT_VEHICLES)
    if isinstance(vehicles, dict):
        vehicles = list(vehicles.values())
    if not isinstance(vehicles, list):
        vehicles = DEFAULT_VEHICLES
    cleaned = list(dict.fromkeys(str(vehicle).strip() for vehicle in vehicles if str(vehicle).strip()))
    return cleaned or DEFAULT_VEHICLES


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_geo_districts(filename: str, mtime: float) -> list[str]:
    try:
        with open(filename, "r", encoding="utf-8") as file:
            geojson = json.load(file)
        districts = []
        for feature in geojson.get("features", []):
            props = feature.get("properties") or {}
            for col_name in ["nm_kecamatan", "KECAMATAN", "kecamatan", "Name", "NAME"]:
                val = props.get(col_name)
                if val is not None and str(val).strip():
                    districts.append(str(val).strip())
                    break
        if districts:
            return sorted(set(districts))
    except (OSError, ValueError, TypeError):
        pass
    return ["Tegalsari", "Wonokromo", "Rungkut", "Asemrowo", "Benowo"]


def get_geo_districts(city):
    filename = "Gresik.geojson" if city == "Gresik" else "Surabaya Barat.geojson"
    return _cached_geo_districts(filename, _file_mtime(filename))


def is_active(value):
    if pd.isna(value):
        return False
    return str(value).strip().lower() not in {"", "-", "nan", "none"}


def parse_schedule_date(value):
    if pd.isna(value):
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def clean_str_cell(value) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.casefold() in {"nan", "none"} else text


def date_column(value):
    return pd.Timestamp(value).strftime("%Y-%m-%d 00:00:00")


def assignment_key(work_date, city, district):
    normalized_city = str(city).strip().casefold()
    normalized_district = str(district).strip().casefold()
    return f"{date_column(work_date)}|{normalized_city}|{normalized_district}"


def assignment_details(details, work_date, city, district, team):
    saved = details.get(assignment_key(work_date, city, district), {})
    saved = saved if isinstance(saved, dict) else {}
    return {
        "team": team,
        "spg_1": str(saved.get("spg_1", "")),
        "spg_2": str(saved.get("spg_2", "")),
        "supervisi": str(saved.get("supervisi", "")),
        "vehicle": str(saved.get("vehicle", "")),
        "brands": saved.get("brands", []) if isinstance(saved.get("brands", []), list) else [],
    }


def get_scheduled_vehicles(schedule_rows, work_date):
    if schedule_rows is None or schedule_rows.empty:
        return []

    details = load_details()
    vehicles = {}
    for _, row in schedule_rows.iterrows():
        saved = details.get(
            assignment_key(work_date, row.get("Kota", ""), row.get("Kecamatan", "")),
            {},
        )
        if not isinstance(saved, dict):
            continue
        assigned = saved.get("vehicle", "")
        if not isinstance(assigned, str):
            continue
        assigned = assigned.strip()
        if assigned.casefold() not in {"", "-", "nan", "none"}:
            vehicles.setdefault(assigned.casefold(), assigned)

    return sorted(vehicles.values(), key=str.casefold)


def get_scheduled_personnel_for_team(team_name: str, work_date, selected_kecamatan: str = "") -> dict:
    """
    Mengambil data Supervisi, SPG 1, SPG 2, Plat Kendaraan, dan Brand dari jadwal_spg_detail.json
    berdasarkan nama team dan tanggal kerja (serta opsional kecamatan/sektor).
    """
    details = load_details()
    date_prefix = date_column(work_date)[:10]
    target_team = " ".join(str(team_name or "").strip().split()).casefold()
    target_kec = str(selected_kecamatan or "").strip().casefold()

    matches = []
    for key, item in details.items():
        if not isinstance(item, dict):
            continue
        if not str(key).startswith(date_prefix):
            continue
        item_team = " ".join(str(item.get("team", "")).strip().split()).casefold()
        if item_team != target_team:
            continue
        item_kec = str(item.get("kecamatan", "")).strip()
        if target_kec and item_kec.casefold() != target_kec:
            continue
        matches.append(item)

    if not matches:
        return {
            "found": False,
            "supervisi": [],
            "spg_1": [],
            "spg_2": [],
            "spg_all": [],
            "vehicles": [],
            "brands": brands_for_team(team_name),
            "records": [],
        }

    spv_list = list(dict.fromkeys(str(m.get("supervisi", "")).strip() for m in matches if str(m.get("supervisi", "")).strip()))
    spg1_list = list(dict.fromkeys(str(m.get("spg_1", "")).strip() for m in matches if str(m.get("spg_1", "")).strip()))
    spg2_list = list(dict.fromkeys(str(m.get("spg_2", "")).strip() for m in matches if str(m.get("spg_2", "")).strip()))
    spg_all = list(dict.fromkeys(spg1_list + spg2_list))
    vehicles = list(
        dict.fromkeys(
            str(m.get("vehicle", "")).strip()
            for m in matches
            if str(m.get("vehicle", "")).strip().casefold() not in {"", "-", "nan", "none"}
        )
    )
    brands = matches[0].get("brands") or brands_for_team(team_name)

    return {
        "found": True,
        "supervisi": spv_list,
        "spg_1": spg1_list,
        "spg_2": spg2_list,
        "spg_all": spg_all,
        "vehicles": vehicles,
        "brands": brands,
        "records": matches,
    }


def parse_flat_schedule_header(column):
    label = str(column).strip()
    lowered = label.casefold()
    kind = "team"
    if "kendaraan" in lowered or "plat" in lowered:
        kind = "vehicle"
        label = re.sub(r"(kendaraan|plat(?:\s*(?:nomor|nomer))?)", "", label, flags=re.IGNORECASE)
    elif "nama team" in lowered:
        label = re.sub(r"nama\s*team", "", label, flags=re.IGNORECASE)
    label = label.strip(" -|:_/")
    return parse_schedule_date(label), kind


def _parse_flat_row_schedule_upload(uploaded_file):
    """
    Parser khusus format tabel baru (`Jadwal SPG 1.1_2.xlsx`):
    Tanggal | Nama Team | Nama SPG 1 | Nama SPG 2 | Nama Supervisi | Kendaraan / Plat Nomor | Kota | Sektor
    """
    uploaded_file.seek(0)
    raw_df = pd.read_excel(uploaded_file)
    col_map = {str(c).strip().casefold(): c for c in raw_df.columns}

    if not FLAT_SCHEDULE_REQUIRED_COLS.issubset(set(col_map.keys())):
        return None

    date_col_src = col_map["tanggal"]
    team_col_src = col_map["nama team"]
    spg1_col_src = col_map["nama spg 1"]
    spg2_col_src = col_map["nama spg 2"]
    spv_col_src = col_map["nama supervisi"]
    plat_col_src = col_map["kendaraan / plat nomor"]
    kota_col_src = col_map["kota"]
    sektor_col_src = col_map["sektor"]

    location_order = []
    location_meta = {}
    date_order = []
    assignments_grid = {}
    uploaded_details = {}
    uploaded_vehicles = {}
    uploaded_spgs = []

    for idx, row in raw_df.iterrows():
        row_num = idx + 2
        raw_date = row.get(date_col_src)
        team = clean_str_cell(row.get(team_col_src))
        spg1 = clean_str_cell(row.get(spg1_col_src))
        spg2 = clean_str_cell(row.get(spg2_col_src))
        spv = clean_str_cell(row.get(spv_col_src))
        plat = clean_str_cell(row.get(plat_col_src))
        kota = clean_str_cell(row.get(kota_col_src))
        sektor = clean_str_cell(row.get(sektor_col_src))

        if not any([pd.notna(raw_date), team, spg1, spg2, spv, plat, kota, sektor]):
            continue

        work_date = parse_schedule_date(raw_date)
        if work_date is None:
            return None, None, None, None, None, None, f"Baris {row_num}: Format Tanggal tidak valid ({raw_date})."
        if not team or not kota or not sektor:
            return None, None, None, None, None, None, (
                f"Baris {row_num}: Kolom Nama Team, Kota, dan Sektor wajib diisi."
            )

        d_col = date_column(work_date)
        if d_col not in date_order:
            date_order.append(d_col)

        loc_key = (kota.casefold(), sektor.casefold())
        if loc_key not in location_meta:
            location_meta[loc_key] = (kota, sektor)
            location_order.append(loc_key)

        a_key = assignment_key(work_date, kota, sektor)
        if a_key in uploaded_details:
            return None, None, None, None, None, None, (
                f"Baris {row_num}: Duplikat jadwal pada tanggal {work_date.strftime('%d-%m-%Y')} "
                f"di {kota} - {sektor}."
            )

        assignments_grid[(loc_key, d_col)] = team
        vehicle_val = plat if plat and plat != "-" else "-"
        uploaded_vehicles[a_key] = vehicle_val if vehicle_val != "-" else ""

        if spg1:
            uploaded_spgs.append(spg1)
        if spg2:
            uploaded_spgs.append(spg2)

        uploaded_details[a_key] = {
            "tanggal": work_date.strftime("%Y-%m-%d"),
            "kota": kota,
            "kecamatan": sektor,
            "team": team,
            "spg_1": spg1,
            "spg_2": spg2,
            "supervisi": spv,
            "vehicle": vehicle_val if vehicle_val != "-" else "",
            "brands": brands_for_team(team),
        }

    if not uploaded_details:
        return None, None, None, None, None, None, "File Excel tidak memiliki baris jadwal yang aktif."

    date_order.sort()
    matrix_rows = []
    for loc_key in location_order:
        kota_val, sektor_val = location_meta[loc_key]
        row_dict = {"Kota": kota_val, "Kecamatan": sektor_val}
        for d_col in date_order:
            row_dict[d_col] = assignments_grid.get((loc_key, d_col), "-")
        matrix_rows.append(row_dict)

    matrix_df = pd.DataFrame(matrix_rows, columns=["Kota", "Kecamatan", *date_order])
    extra_payload = {
        "format": "flat_personnel",
        "details": uploaded_details,
        "spgs": uploaded_spgs,
    }
    return matrix_df, "Kota", "Kecamatan", date_order, uploaded_vehicles, extra_payload, None


def validate_schedule_upload(uploaded_file):
    try:
        uploaded_file.seek(0)
        head_df = pd.read_excel(uploaded_file, nrows=1)
        head_cols = {str(c).strip().casefold() for c in head_df.columns}
        if FLAT_SCHEDULE_REQUIRED_COLS.issubset(head_cols):
            return _parse_flat_row_schedule_upload(uploaded_file)

        uploaded_file.seek(0)
        raw = pd.read_excel(uploaded_file, header=None)
    except Exception as exc:
        return None, None, None, None, None, None, f"File Excel tidak dapat dibaca: {exc}"
    if raw.empty or len(raw.index) < 2:
        return None, None, None, None, None, None, "File tidak memiliki header dan data jadwal."

    header = raw.iloc[0]
    normalized_header = {
        index: str(value).strip().casefold()
        for index, value in header.items()
        if not pd.isna(value)
    }
    city_index = next((i for i, value in normalized_header.items() if "kota" in value), None)
    district_index = next((i for i, value in normalized_header.items() if "kecamatan" in value or "sektor" in value), None)
    if city_index is None or district_index is None or city_index == district_index:
        return None, None, None, None, None, None, "File harus memiliki kolom Kota dan Kecamatan/Sektor."

    subheader = raw.iloc[1]
    subheader_labels = {
        index: str(value).strip().casefold()
        for index, value in subheader.items()
        if not pd.isna(value)
    }
    team_indexes = {}
    vehicle_indexes = {}
    raw_has_two_header_rows = True
    for index, value in header.items():
        work_date = parse_schedule_date(value)
        if work_date is None:
            continue
        date_key = date_column(work_date)
        label = subheader_labels.get(index, "")
        if "kendaraan" in label or "plat" in label:
            return None, None, None, None, None, None, "Kolom tanggal harus berada di atas kolom Nama Team."
        team_index = index
        vehicle_index = None
        if "nama team" in label:
            vehicle_label = subheader_labels.get(index + 1, "")
            if "kendaraan" in vehicle_label or "plat" in vehicle_label:
                vehicle_index = index + 1
        if date_key in team_indexes:
            return None, None, None, None, None, None, f"Tanggal {date_key[:10]} muncul lebih dari sekali."
        team_indexes[date_key] = team_index
        if vehicle_index is not None:
            vehicle_indexes[date_key] = vehicle_index

    has_team_subheaders = any("nama team" in label for label in subheader_labels.values())
    if not team_indexes or not has_team_subheaders:
        uploaded_file.seek(0)
        try:
            frame = pd.read_excel(uploaded_file)
        except Exception as exc:
            return None, None, None, None, None, None, f"File Excel tidak dapat dibaca: {exc}"
        frame.columns = [str(column).strip() for column in frame.columns]
        if not len(frame.columns) or any(not column for column in frame.columns):
            return None, None, None, None, None, None, "File harus memiliki nama kolom yang valid."
        if len(set(frame.columns)) != len(frame.columns):
            return None, None, None, None, None, None, "Nama kolom pada file tidak boleh duplikat."
        city_col = next((col for col in frame.columns if "kota" in col.lower()), None)
        district_col = next((col for col in frame.columns if "kecamatan" in col.lower() or "sektor" in col.lower()), None)
        if not city_col or not district_col or city_col == district_col:
            return None, None, None, None, None, None, "File harus memiliki kolom Kota dan Kecamatan."

        team_columns = {}
        vehicle_indexes = {}
        for col in frame.columns:
            if col in {city_col, district_col}:
                continue
            work_date, column_kind = parse_flat_schedule_header(col)
            if work_date is None:
                return None, None, None, None, None, None, (
                    f"Kolom '{col}' bukan tanggal jadwal atau kolom kendaraan bertanggal yang valid."
                )
            date_key = date_column(work_date)
            target_columns = vehicle_indexes if column_kind == "vehicle" else team_columns
            if date_key in target_columns:
                column_label = "kendaraan/plat" if column_kind == "vehicle" else "nama team"
                return None, None, None, None, None, None, (
                    f"Kolom {column_label} untuk tanggal {date_key[:10]} muncul lebih dari sekali."
                )
            target_columns[date_key] = col
        missing_team_dates = sorted(set(vehicle_indexes) - set(team_columns))
        if missing_team_dates:
            return None, None, None, None, None, None, (
                f"Kolom kendaraan tidak memiliki kolom Nama Team untuk tanggal {missing_team_dates[0][:10]}."
            )
        if not team_columns:
            return None, None, None, None, None, None, "File harus memiliki kolom tanggal dan Nama Team."

        team_indexes = team_columns
        raw = frame
        raw_city_col, raw_district_col = city_col, district_col
        frame = frame[[city_col, district_col, *team_columns.values()]].rename(
            columns={
                city_col: "Kota",
                district_col: "Kecamatan",
                **{column: date_key for date_key, column in team_columns.items()},
            }
        )
        city_col, district_col = "Kota", "Kecamatan"
        date_cols = [date_key for date_key in team_indexes]
        multi_header = bool(vehicle_indexes)
        raw_has_two_header_rows = False
    else:
        city_col, district_col = "Kota", "Kecamatan"
        date_cols = list(team_indexes)
        raw_city_col, raw_district_col = city_index, district_index
        multi_header = True
        rows = []
        for _, source_row in raw.iloc[2:].iterrows():
            row = {
                city_col: source_row.get(raw_city_col),
                district_col: source_row.get(raw_district_col),
            }
            for date_key, team_index in team_indexes.items():
                row[date_key] = source_row.get(team_index)
            rows.append(row)
        frame = pd.DataFrame(rows, columns=[city_col, district_col, *date_cols])

    seen_locations = set()
    for _, row in frame.iterrows():
        has_assignment = any(is_active(row.get(column)) for column in date_cols)
        city = str(row.get(city_col, "")).strip()
        district = str(row.get(district_col, "")).strip()
        if not has_assignment and not city and not district:
            continue
        if not city or city.casefold() in {"nan", "none"} or not district or district.casefold() in {"nan", "none"}:
            if not has_assignment:
                continue
            return None, None, None, None, None, None, "Setiap baris jadwal aktif harus memiliki Kota dan Kecamatan."
        location = (city.casefold(), district.casefold())
        if location in seen_locations:
            return None, None, None, None, None, None, f"Lokasi {city} / {district} muncul lebih dari sekali."
        seen_locations.add(location)

    uploaded_vehicles = {}
    if multi_header:
        source_rows = raw.iloc[2:].iterrows() if raw_has_two_header_rows else raw.iterrows()
        for _, source_row in source_rows:
            city = str(source_row.get(raw_city_col, "")).strip()
            district = str(source_row.get(raw_district_col, "")).strip()
            if not city or not district or city.casefold() == "nan" or district.casefold() == "nan":
                continue
            for date_key, team_column in team_indexes.items():
                if not is_active(source_row.get(team_column)):
                    continue
                vehicle_column = vehicle_indexes.get(date_key)
                if vehicle_column is None:
                    continue
                vehicle = source_row.get(vehicle_column)
                uploaded_vehicles[assignment_key(parse_schedule_date(date_key), city, district)] = (
                    "" if pd.isna(vehicle) else str(vehicle).strip()
                )

    return frame, city_col, district_col, date_cols, uploaded_vehicles, {"format": "matrix"}, None


def retain_matching_schedule_details(details, frame, city_col, district_col, date_cols):
    assignments = {}
    for _, row in frame.iterrows():
        city = str(row.get(city_col, "")).strip()
        district = str(row.get(district_col, "")).strip()
        if not city or not district:
            continue
        for date_col in date_cols:
            team = row.get(date_col)
            if not is_active(team):
                continue
            work_date = pd.to_datetime(date_col, errors="coerce")
            if not pd.isna(work_date):
                assignments[assignment_key(work_date.date(), city, district)] = str(team).strip()

    retained = {}
    for key, saved in details.items():
        team = assignments.get(key)
        if team is None:
            continue
        saved_team = saved.get("team") if isinstance(saved, dict) else None
        if saved_team and str(saved_team).strip().casefold() != team.casefold():
            continue
        retained[key] = saved
    return retained


@st.cache_data(show_spinner=False)
def _cached_build_schedule_excel(
    sched_mtime: float,
    details_mtime: float,
    city_col: str,
    district_col: str,
) -> bytes:
    schedule = load_schedule()
    details = load_details()
    date_cols = [
        column
        for column in schedule.columns
        if column not in {city_col, district_col} and parse_schedule_date(column) is not None
    ]
    export_rows = []
    for _, source_row in schedule.iterrows():
        city = str(source_row.get(city_col, "")).strip()
        district = str(source_row.get(district_col, "")).strip()
        for column in date_cols:
            team = source_row.get(column, "")
            if not is_active(team):
                continue
            work_date = parse_schedule_date(column)
            saved = details.get(assignment_key(work_date, city, district), {})
            saved = saved if isinstance(saved, dict) else {}
            export_rows.append({
                "Tanggal": pd.Timestamp(work_date),
                "Nama Team": str(team).strip(),
                "Nama SPG 1": saved.get("spg_1", ""),
                "Nama SPG 2": saved.get("spg_2", ""),
                "Nama Supervisi": saved.get("supervisi", ""),
                "Kendaraan / Plat Nomor": saved.get("vehicle", ""),
                "Kota": city,
                "Sektor": district,
            })

    cols = [
        "Tanggal", "Nama Team", "Nama SPG 1", "Nama SPG 2",
        "Nama Supervisi", "Kendaraan / Plat Nomor", "Kota", "Sektor",
    ]
    df_export = pd.DataFrame(export_rows, columns=cols)
    if not df_export.empty:
        df_export = df_export.sort_values(by=["Tanggal", "Kota", "Sektor"]).reset_index(drop=True)

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df_export.to_excel(writer, sheet_name="Sheet1", index=False)
        ws = writer.sheets["Sheet1"]
        for row_idx in range(2, len(df_export) + 2):
            ws.cell(row=row_idx, column=1).number_format = "yyyy-mm-dd"
    return buffer.getvalue()


def build_schedule_excel(schedule, details, city_col, district_col):
    """Mengekspor jadwal aktif dalam format tabel datar lengkap (Tanggal, Team, SPG 1, SPG 2, Supervisi, Plat, Kota, Sektor)."""
    return _cached_build_schedule_excel(
        _file_mtime(SCHEDULE_FILE),
        _file_mtime(SCHEDULE_DETAIL_FILE),
        city_col,
        district_col,
    )


@st.cache_data(show_spinner=False)
def _cached_build_schedule_template_excel(
    week_start_iso: str,
    teams_tuple: tuple,
    vehicles_tuple: tuple,
) -> bytes:
    week_start = date.fromisoformat(week_start_iso)
    workdays = [week_start + timedelta(days=offset) for offset in range(5)]
    teams = list(teams_tuple)
    vehicles = list(vehicles_tuple)

    sample_rows = []
    for workday in workdays:
        for team in teams[:4]:
            sample_rows.append({
                "Tanggal": pd.Timestamp(workday),
                "Nama Team": team,
                "Nama SPG 1": "",
                "Nama SPG 2": "",
                "Nama Supervisi": "",
                "Kendaraan / Plat Nomor": vehicles[0] if vehicles else "",
                "Kota": "Surabaya",
                "Sektor": "",
            })

    cols = [
        "Tanggal", "Nama Team", "Nama SPG 1", "Nama SPG 2",
        "Nama Supervisi", "Kendaraan / Plat Nomor", "Kota", "Sektor",
    ]
    df_tpl = pd.DataFrame(sample_rows, columns=cols)

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_tpl.to_excel(writer, sheet_name="Sheet1", index=False)
        workbook = writer.book
        master_sheet = workbook.create_sheet("Master")
        master_sheet["A1"] = "Nama Team"
        master_sheet["B1"] = "Plat Kendaraan"
        for row_number, team in enumerate(teams, start=2):
            master_sheet.cell(row=row_number, column=1, value=team)
        for row_number, vehicle in enumerate(vehicles, start=2):
            master_sheet.cell(row=row_number, column=2, value=vehicle)
        master_sheet.sheet_state = "hidden"

        ws = writer.sheets["Sheet1"]
        ws.freeze_panes = "A2"
        widths = [14, 22, 18, 18, 18, 22, 14, 20]
        for idx, width in enumerate(widths, start=1):
            ws.column_dimensions[openpyxl.utils.get_column_letter(idx)].width = width
        for row_idx in range(2, len(df_tpl) + 2):
            ws.cell(row=row_idx, column=1).number_format = "yyyy-mm-dd"

        last_row = max(50, len(df_tpl) + 1)
        team_last_row = max(2, len(teams) + 1)
        vehicle_last_row = max(2, len(vehicles) + 1)
        team_validation = openpyxl.worksheet.datavalidation.DataValidation(
            type="list",
            formula1=f'=INDIRECT("\'Master\'!$A$2:$A${team_last_row}")',
            allow_blank=True,
        )
        vehicle_validation = openpyxl.worksheet.datavalidation.DataValidation(
            type="list",
            formula1=f'=INDIRECT("\'Master\'!$B$2:$B${vehicle_last_row}")',
            allow_blank=True,
        )
        ws.add_data_validation(team_validation)
        ws.add_data_validation(vehicle_validation)
        team_validation.add(f"B2:B{last_row}")
        vehicle_validation.add(f"F2:F{last_row}")

    return output.getvalue()


def build_schedule_template_excel(week_anchor):
    """Membuat template Excel format baru lengkap dengan dropdown Master Team dan Plat Kendaraan."""
    week_start = week_anchor - timedelta(days=week_anchor.weekday())
    return _cached_build_schedule_template_excel(
        week_start.isoformat(),
        tuple(team_choices()),
        tuple(vehicle_choices()),
    )


def build_schedule_preview(frame, details, city_col, district_col, date_cols, uploaded_vehicles, extra_payload=None):
    if isinstance(extra_payload, dict) and extra_payload.get("format") == "flat_personnel":
        flat_details = extra_payload.get("details", {})
        preview_rows = []
        for _, item in flat_details.items():
            preview_rows.append({
                "Tanggal": item.get("tanggal", ""),
                "Nama Team": item.get("team", ""),
                "Nama SPG 1": item.get("spg_1", "") or "-",
                "Nama SPG 2": item.get("spg_2", "") or "-",
                "Nama Supervisi": item.get("supervisi", "") or "-",
                "Kendaraan / Plat Nomor": item.get("vehicle", "") or "-",
                "Kota": item.get("kota", ""),
                "Sektor": item.get("kecamatan", ""),
                "Rokok (Otomatis)": ", ".join(item.get("brands", [])),
            })
        df_prev = pd.DataFrame(preview_rows)
        if not df_prev.empty:
            df_prev = df_prev.sort_values(by=["Tanggal", "Kota", "Sektor"]).reset_index(drop=True)
        return df_prev

    preview_rows = []
    preview_columns = [city_col, district_col]
    for date_col in date_cols:
        work_date = parse_schedule_date(date_col)
        date_label = work_date.strftime("%Y-%m-%d") if work_date else str(date_col)
        preview_columns.extend(
            [f"{date_label} - Nama Team", f"{date_label} - Kendaraan / Plat Nomor"]
        )

    for _, source_row in frame.iterrows():
        city = source_row.get(city_col, "")
        district = source_row.get(district_col, "")
        preview_row = {city_col: city, district_col: district}
        for date_col in date_cols:
            work_date = parse_schedule_date(date_col)
            team = source_row.get(date_col, "")
            key = assignment_key(work_date, city, district) if work_date else None
            saved = details.get(key, {}) if key else {}
            vehicle = uploaded_vehicles.get(key) if key in uploaded_vehicles else (
                saved.get("vehicle", "") if isinstance(saved, dict) else ""
            )
            date_label = work_date.strftime("%Y-%m-%d") if work_date else str(date_col)
            preview_row[f"{date_label} - Nama Team"] = team
            preview_row[f"{date_label} - Kendaraan / Plat Nomor"] = vehicle
        preview_rows.append(preview_row)

    return pd.DataFrame(preview_rows, columns=preview_columns)


def week_info(value):
    iso = pd.Timestamp(value).isocalendar()
    return f"Minggu ke-{iso.week} · {iso.year}", (iso.year, iso.week)


def find_meta_columns(frame):
    city = next((col for col in frame.columns if "kota" in str(col).strip().lower()), "Kota")
    district = next((col for col in frame.columns if "kecamatan" in str(col).strip().lower()), "Kecamatan")
    if city not in frame.columns:
        frame[city] = ""
    if district not in frame.columns:
        frame[district] = ""
    return city, district


def add_assignments(frame, city_col, district_col, dates, city, districts, team):
    date_cols = [col for col in frame.columns if col not in {city_col, district_col}]
    conflicts = []
    for district in districts:
        matching = frame[
            frame[city_col].astype(str).str.strip().str.casefold().eq(city.strip().casefold())
            & frame[district_col].astype(str).str.strip().str.casefold().eq(district.strip().casefold())
        ]
        for workday in dates:
            column = date_column(workday)
            if not matching.empty and column in date_cols and is_active(frame.at[matching.index[0], column]):
                conflicts.append(f"{district} — {workday.strftime('%d-%m-%Y')}")
    if conflicts:
        return frame, conflicts

    for district in districts:
        for workday in dates:
            column = date_column(workday)
            if column not in frame.columns:
                frame[column] = "-"
            matching = frame[
                frame[city_col].astype(str).str.strip().str.casefold().eq(city.strip().casefold())
                & frame[district_col].astype(str).str.strip().str.casefold().eq(district.strip().casefold())
            ]
            if matching.empty:
                new_row = {col: "-" for col in frame.columns}
                new_row[city_col] = city
                new_row[district_col] = district
                new_row[column] = team
                frame = pd.concat([frame, pd.DataFrame([new_row])], ignore_index=True)
            else:
                frame.at[matching.index[0], column] = team
    return frame, []


def store_assignment_details(details, dates, city, districts, team, vehicle, brands, spg_1="", spg_2="", supervisi=""):
    for workday in dates:
        for district in districts:
            details[assignment_key(workday, city, district)] = {
                "tanggal": pd.Timestamp(workday).strftime("%Y-%m-%d"),
                "kota": city,
                "kecamatan": district,
                "team": team,
                "spg_1": str(spg_1 or "").strip(),
                "spg_2": str(spg_2 or "").strip(),
                "supervisi": str(supervisi or "").strip(),
                "vehicle": vehicle,
                "brands": list(brands),
            }
    return details


def render_schedule_entry():
    schedule = load_schedule()
    city_col, district_col = find_meta_columns(schedule)
    details = load_details()
    teams = team_choices()
    vehicles = vehicle_choices()

    districts_by_city = {c: get_geo_districts(c) for c in CITIES}
    team_brands_cache = {}
    for t in teams:
        if t not in team_brands_cache:
            team_brands_cache[t] = brands_for_team(t)

    def _get_brands(t_name):
        if t_name not in team_brands_cache:
            team_brands_cache[t_name] = brands_for_team(t_name)
        return team_brands_cache[t_name]

    tab_day, tab_week, tab_manage, tab_excel = st.tabs(
        [
            "➕ Tambah Hari Kerja",
            "🗓️ Tambah Minggu Kerja",
            "✏️ Kelola Jadwal Aktif",
            "📥 Download / Upload Excel",
        ]
    )

    with tab_day:
        st.markdown("#### Buat jadwal untuk satu hari")
        st.caption("Data team, personel SPG/Supervisi, merek rokok, dan kendaraan tersimpan otomatis.")
        with st.form("form_add_schedule_day"):
            col_date, col_city, col_team = st.columns(3)
            with col_date:
                work_date = st.date_input("Tanggal kerja", value=date.today(), key="new_workday_date")
            with col_city:
                city = st.selectbox("Kota / Kabupaten", CITIES, key="new_workday_city")
            with col_team:
                team = st.selectbox("Master Team SPG", teams, key="new_workday_team")

            col_spv, col_spg1, col_spg2 = st.columns(3)
            with col_spv:
                supervisi_name = st.text_input("Nama Supervisi", key="new_workday_spv")
            with col_spg1:
                spg1_name = st.text_input("Nama SPG 1", key="new_workday_spg1")
            with col_spg2:
                spg2_name = st.text_input("Nama SPG 2", key="new_workday_spg2")

            districts = st.multiselect("Sektor / Kecamatan yang dijadwalkan", districts_by_city.get(city, []), key="new_workday_districts")
            col_vehicle, col_brands = st.columns(2)
            with col_vehicle:
                vehicle = st.selectbox("Kendaraan / Plat Nomor", vehicles, key="new_workday_vehicle")
            with col_brands:
                day_brand_opts = _get_brands(team)
                brands = st.multiselect(
                    "Rokok yang dibawa",
                    day_brand_opts,
                    default=day_brand_opts,
                    key="new_workday_brands",
                    help="Pilihan merek mengikuti alokasi pada Master Team & Brand.",
                )
            submit_day = st.form_submit_button("💾 Simpan Jadwal Hari Ini", type="primary")
        if submit_day:
            if not districts:
                st.warning("Pilih minimal satu sektor/kecamatan terlebih dahulu.")
            elif not brands:
                st.warning("Pilih minimal satu merek rokok yang dibawa.")
            else:
                updated, conflicts = add_assignments(schedule.copy(), city_col, district_col, [work_date], city, districts, team)
                if conflicts:
                    st.error("Sudah ada jadwal pada lokasi dan tanggal berikut: " + ", ".join(conflicts))
                elif save_schedule(updated):
                    details = store_assignment_details(
                        details, [work_date], city, districts, team, vehicle, brands,
                        spg_1=spg1_name, spg_2=spg2_name, supervisi=supervisi_name,
                    )
                    if save_details(details):
                        st.success(f"Jadwal {team} tersimpan untuk {len(districts)} sektor, termasuk Supervisi, SPG & brand.")
                    st.rerun()

    with tab_week:
        st.markdown("#### Buat jadwal satu minggu")
        st.caption("Pilih hari kerja, sektor/kecamatan, team, personel, merek, dan kendaraan.")
        with st.form("form_add_schedule_week"):
            col_anchor, col_city, col_team = st.columns(3)
            with col_anchor:
                week_anchor = st.date_input("Tanggal dalam minggu tujuan", value=date.today(), key="new_week_anchor")
            week_start = week_anchor - timedelta(days=week_anchor.weekday())
            week_end = week_start + timedelta(days=6)
            with col_city:
                week_city = st.selectbox("Kota / Kabupaten", CITIES, key="new_week_city")
            with col_team:
                week_team = st.selectbox("Master Team SPG", teams, key="new_week_team")

            col_w_spv, col_w_spg1, col_w_spg2 = st.columns(3)
            with col_w_spv:
                week_spv = st.text_input("Nama Supervisi", key="new_week_spv")
            with col_w_spg1:
                week_spg1 = st.text_input("Nama SPG 1", key="new_week_spg1")
            with col_w_spg2:
                week_spg2 = st.text_input("Nama SPG 2", key="new_week_spg2")

            st.info(f"Periode minggu: {week_start.strftime('%d %b %Y')} – {week_end.strftime('%d %b %Y')}")
            workdays = st.multiselect("Hari kerja", WEEKDAYS, default=WEEKDAYS[:5], key="new_week_days")
            week_districts = st.multiselect("Sektor / Kecamatan yang dijadwalkan", districts_by_city.get(week_city, []), key="new_week_districts")
            col_vehicle_week, col_brands_week = st.columns(2)
            with col_vehicle_week:
                week_vehicle = st.selectbox("Kendaraan / Plat Nomor", vehicles, key="new_week_vehicle")
            with col_brands_week:
                week_brand_opts = _get_brands(week_team)
                week_brands = st.multiselect(
                    "Rokok yang dibawa", week_brand_opts, default=week_brand_opts,
                    key="new_week_brands", help="Pilihan merek mengikuti alokasi pada Master Team & Brand.",
                )
            submit_week = st.form_submit_button("🗓️ Buat Jadwal Mingguan", type="primary")
        if submit_week:
            if not workdays or not week_districts:
                st.warning("Pilih minimal satu hari kerja dan satu sektor/kecamatan.")
            elif not week_brands:
                st.warning("Pilih minimal satu merek rokok yang dibawa.")
            else:
                day_index = {label: index for index, label in enumerate(WEEKDAYS)}
                selected_dates = [week_start + timedelta(days=day_index[label]) for label in workdays]
                updated, conflicts = add_assignments(
                    schedule.copy(), city_col, district_col, selected_dates, week_city, week_districts, week_team
                )
                if conflicts:
                    st.error("Ada jadwal yang sudah terisi. Tidak ada perubahan yang disimpan: " + ", ".join(conflicts))
                elif save_schedule(updated):
                    details = store_assignment_details(
                        details, selected_dates, week_city, week_districts, week_team, week_vehicle, week_brands,
                        spg_1=week_spg1, spg_2=week_spg2, supervisi=week_spv,
                    )
                    if save_details(details):
                        st.success(f"Berhasil membuat {len(selected_dates) * len(week_districts)} penugasan untuk {week_team}.")
                    st.rerun()

    with tab_manage:
        st.markdown("#### Jadwal aktif")
        st.caption("Master team, personel Supervisi/SPG, alokasi merek, dan kendaraan ditampilkan pada setiap penugasan.")
        date_cols = [col for col in schedule.columns if col not in {city_col, district_col}]
        entries = []
        for row_index, row in schedule.iterrows():
            for date_col in date_cols:
                parsed_date = pd.to_datetime(date_col, errors="coerce")
                if pd.isna(parsed_date) or not is_active(row.get(date_col, "")):
                    continue
                label, sort_key = week_info(parsed_date)
                city_value = str(row.get(city_col, "") if pd.notna(row.get(city_col, "")) else "").strip()
                district_value = str(row.get(district_col, "") if pd.notna(row.get(district_col, "")) else "").strip()
                team_value = str(row.get(date_col, "")).strip()
                saved = assignment_details(details, parsed_date.date(), city_value, district_value, team_value)
                entries.append({
                    "row": row_index, "date_col": date_col, "date": parsed_date.date(),
                    "week": label, "week_sort": sort_key, "city": city_value,
                    "district": district_value, "team": team_value,
                    "spg_1": saved["spg_1"], "spg_2": saved["spg_2"], "supervisi": saved["supervisi"],
                    "vehicle": saved["vehicle"], "brands": saved["brands"],
                })

        if not entries:
            st.info("Belum ada jadwal aktif. Gunakan tab **Tambah Hari Kerja**, **Tambah Minggu Kerja**, atau **Upload Excel**.")
        else:
            weeks_by_sort = {entry["week_sort"]: entry["week"] for entry in entries}
            week_labels = [weeks_by_sort[key] for key in sorted(weeks_by_sort, reverse=True)]
            selected_weeks = st.multiselect(
                "Filter periode", week_labels, default=[week_labels[0]], key="schedule_entry_weeks"
            )
            visible_entries = sorted(
                [entry for entry in entries if entry["week"] in selected_weeks],
                key=lambda entry: (entry["date"], entry["city"], entry["district"], entry["team"]),
            )
            st.markdown(f"**{len(visible_entries)} jadwal aktif**")

            for entry in visible_entries:
                entry_id = f"{entry['row']}_{entry['date_col']}"
                team_widget_key = f"team_{entry_id}_{entry['team']}"
                vehicle_widget_key = f"vehicle_{entry_id}_{entry['vehicle']}"
                spg_caption = " & ".join([x for x in [entry["spg_1"], entry["spg_2"]] if x]) or "Belum diatur"
                heading = (
                    f"{entry['date'].strftime('%d-%m-%Y')} · "
                    f"{entry['district'] or 'Sektor belum diisi'} · {entry['team']} · "
                    f"SPV: {entry['supervisi'] or '-'} · SPG: {spg_caption}"
                )
                with st.expander(f"📍 {heading}", expanded=False):
                    brands_allowed = _get_brands(entry["team"])
                    default_brands = [brand for brand in entry["brands"] if brand in brands_allowed]
                    entry_teams = teams if entry["team"] in teams else [entry["team"], *teams]
                    entry_vehicles = vehicles if entry["vehicle"] in vehicles else [entry["vehicle"], *vehicles]
                    saved_vehicle = entry["vehicle"] or vehicles[0]
                    st.caption(
                        f"{entry['week']} · Supervisi: {entry['supervisi'] or '-'} · "
                        f"SPG 1: {entry['spg_1'] or '-'} · SPG 2: {entry['spg_2'] or '-'} · "
                        f"Plat: {entry['vehicle'] or '-'}"
                    )
                    with st.form(f"edit_schedule_{entry_id}"):
                        col_date_edit, col_city_edit = st.columns(2)
                        with col_date_edit:
                            edited_date = st.date_input("Tanggal kerja", value=entry["date"], key=f"date_{entry_id}")
                        with col_city_edit:
                            city_index = CITIES.index(entry["city"]) if entry["city"] in CITIES else 0
                            edited_city = st.selectbox("Kota / Kabupaten", CITIES, index=city_index, key=f"city_{entry_id}")
                        col_district_edit, col_team_edit = st.columns(2)
                        with col_district_edit:
                            district_options = districts_by_city.get(edited_city, [])
                            district_index = district_options.index(entry["district"]) if entry["district"] in district_options else None
                            if district_index is None:
                                edited_district = st.text_input("Sektor / Kecamatan", value=entry["district"], key=f"district_{entry_id}")
                            else:
                                edited_district = st.selectbox("Sektor / Kecamatan", district_options, index=district_index, key=f"district_{entry_id}")
                        with col_team_edit:
                            edited_team = st.selectbox(
                                "Master Team SPG", entry_teams,
                                index=entry_teams.index(entry["team"]), key=team_widget_key,
                            )

                        col_spv_e, col_spg1_e, col_spg2_e = st.columns(3)
                        with col_spv_e:
                            edited_spv = st.text_input("Nama Supervisi", value=entry["supervisi"], key=f"spv_{entry_id}")
                        with col_spg1_e:
                            edited_spg1 = st.text_input("Nama SPG 1", value=entry["spg_1"], key=f"spg1_{entry_id}")
                        with col_spg2_e:
                            edited_spg2 = st.text_input("Nama SPG 2", value=entry["spg_2"], key=f"spg2_{entry_id}")

                        col_vehicle_edit, col_brands_edit = st.columns(2)
                        with col_vehicle_edit:
                            edited_vehicle = st.selectbox(
                                "Kendaraan / Plat Nomor", entry_vehicles,
                                index=entry_vehicles.index(saved_vehicle), key=vehicle_widget_key,
                            )
                        with col_brands_edit:
                            edited_brands = st.multiselect(
                                "Rokok yang dibawa", _get_brands(edited_team), default=default_brands,
                                key=f"brands_{entry_id}", help="Pilihan merek mengikuti alokasi Master Team & Brand.",
                            )
                        save_col, delete_col = st.columns(2)
                        with save_col:
                            save_clicked = st.form_submit_button("💾 Simpan Perubahan", type="primary", use_container_width=True)
                        with delete_col:
                            delete_clicked = st.form_submit_button("🗑️ Hapus Jadwal Ini", use_container_width=True)

                    if save_clicked:
                        if not str(edited_district).strip():
                            st.warning("Sektor / Kecamatan wajib diisi.")
                        elif not edited_brands:
                            st.warning("Pilih minimal satu merek rokok.")
                        else:
                            destination_col = date_column(edited_date)
                            destination_rows = schedule[
                                schedule[city_col].astype(str).str.strip().str.casefold().eq(edited_city.strip().casefold())
                                & schedule[district_col].astype(str).str.strip().str.casefold().eq(edited_district.strip().casefold())
                            ].index
                            destination_row = destination_rows[0] if len(destination_rows) else entry["row"]
                            destination_value = schedule.at[destination_row, destination_col] if destination_col in schedule.columns else "-"
                            same_assignment = (
                                destination_col == entry["date_col"]
                                and destination_row == entry["row"]
                            )
                            if not same_assignment and is_active(destination_value):
                                st.error("Tanggal dan sektor tujuan sudah memiliki jadwal aktif. Pilih tujuan lain.")
                            else:
                                if destination_col not in schedule.columns:
                                    schedule[destination_col] = "-"
                                old_key = assignment_key(entry["date"], entry["city"], entry["district"])
                                new_key = assignment_key(edited_date, edited_city, edited_district)
                                if not same_assignment:
                                    schedule.at[entry["row"], entry["date_col"]] = "-"
                                    if len(destination_rows) == 0:
                                        new_row = {col: "-" for col in schedule.columns}
                                        new_row[city_col] = edited_city
                                        new_row[district_col] = edited_district.strip()
                                        schedule = pd.concat([schedule, pd.DataFrame([new_row])], ignore_index=True)
                                        destination_row = schedule.index[-1]
                                schedule.at[destination_row, city_col] = edited_city
                                schedule.at[destination_row, district_col] = edited_district.strip()
                                schedule.at[destination_row, destination_col] = edited_team
                                if old_key != new_key:
                                    details.pop(old_key, None)
                                details[new_key] = {
                                    "tanggal": pd.Timestamp(edited_date).strftime("%Y-%m-%d"),
                                    "kota": edited_city,
                                    "kecamatan": edited_district.strip(),
                                    "team": edited_team,
                                    "spg_1": str(edited_spg1).strip(),
                                    "spg_2": str(edited_spg2).strip(),
                                    "supervisi": str(edited_spv).strip(),
                                    "vehicle": edited_vehicle,
                                    "brands": list(edited_brands),
                                }
                                if save_schedule(schedule) and save_details(details):
                                    st.success("Jadwal, personel, kendaraan, dan brand berhasil diperbarui.")
                                    st.rerun()

                    if delete_clicked:
                        schedule.at[entry["row"], entry["date_col"]] = "-"
                        details.pop(assignment_key(entry["date"], entry["city"], entry["district"]), None)
                        if save_schedule(schedule) and save_details(details):
                            st.success("Jadwal berhasil dihapus.")
                            st.rerun()

    if st.button("🔄 Muat Ulang Jadwal", key="reload_schedule"):
        st.cache_data.clear()
        st.rerun()

    with tab_excel:
        st.markdown("#### Unduh dan unggah jadwal melalui Excel")
        st.caption(
            "Mendukung file format baru dengan kolom: Tanggal, Nama Team, Nama SPG 1, Nama SPG 2, "
            "Nama Supervisi, Kendaraan / Plat Nomor, Kota, dan Sektor. "
            "Nama Supervisi, SPG 1 & SPG 2 akan otomatis tampil di portal sesuai jadwal."
        )

        template_anchor = st.date_input(
            "Tanggal acuan minggu template",
            value=date.today(),
            key="schedule_template_week",
        )
        st.download_button(
            "📄 Download Template Jadwal SPG (Format Baru)",
            data=build_schedule_template_excel(template_anchor),
            file_name="Template Jadwal SPG.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key="download_schedule_template",
        )

        st.download_button(
            "⬇️ Download Jadwal SPG Saat Ini",
            data=build_schedule_excel(schedule, details, city_col, district_col),
            file_name="Jadwal SPG.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key="download_current_schedule",
        )

        uploaded_file = st.file_uploader(
            "Pilih file Excel jadwal untuk diunggah",
            type=["xlsx"],
            key="upload_schedule_excel",
        )
        if uploaded_file is not None:
            (
                upload_frame,
                upload_city_col,
                upload_district_col,
                upload_date_cols,
                uploaded_vehicles,
                extra_payload,
                upload_error,
            ) = validate_schedule_upload(uploaded_file)
            if upload_error:
                st.error(upload_error)
            else:
                st.markdown("##### Pratinjau jadwal yang akan diunggah")
                st.dataframe(
                    build_schedule_preview(
                        upload_frame,
                        load_details(),
                        upload_city_col,
                        upload_district_col,
                        upload_date_cols,
                        uploaded_vehicles,
                        extra_payload=extra_payload,
                    ),
                    use_container_width=True,
                    hide_index=True,
                )
                st.warning("Tindakan ini mengganti seluruh jadwal aktif dengan isi file di atas.")
                uploaded_team_names = schedule_team_names(upload_frame, upload_date_cols)
                if len(uploaded_team_names) > 20:
                    st.error("File jadwal berisi lebih dari 20 team; jumlah maksimum yang didukung adalah 20.")
                elif not uploaded_team_names:
                    st.error("File jadwal harus berisi minimal satu nama team aktif.")
                if st.button(
                    "Ganti Jadwal Aktif dengan File Excel Ini",
                    type="primary",
                    key="confirm_schedule_excel_upload",
                ) and 0 < len(uploaded_team_names) <= 20:
                    if isinstance(extra_payload, dict) and extra_payload.get("format") == "flat_personnel":
                        updated_details = extra_payload.get("details", {})
                        uploaded_spg_list = extra_payload.get("spgs", [])
                    else:
                        uploaded_spg_list = []
                        updated_details = retain_matching_schedule_details(
                            load_details(),
                            upload_frame,
                            upload_city_col,
                            upload_district_col,
                            upload_date_cols,
                        )
                        if uploaded_vehicles:
                            for _, row in upload_frame.iterrows():
                                city = str(row.get(upload_city_col, "")).strip()
                                district = str(row.get(upload_district_col, "")).strip()
                                if not city or not district:
                                    continue
                                for date_col in upload_date_cols:
                                    team = row.get(date_col)
                                    if not is_active(team):
                                        continue
                                    work_date = parse_schedule_date(date_col)
                                    key = assignment_key(work_date, city, district)
                                    if key not in uploaded_vehicles:
                                        continue
                                    saved = updated_details.get(key, {})
                                    saved = saved.copy() if isinstance(saved, dict) else {}
                                    saved["team"] = str(team).strip()
                                    saved["vehicle"] = uploaded_vehicles[key]
                                    if not saved.get("brands"):
                                        saved["brands"] = brands_for_team(saved["team"])
                                    updated_details[key] = saved

                    if save_schedule(upload_frame):
                        if save_details(updated_details):
                            sync_ok, sync_info = sync_masters_from_schedule_upload(
                                uploaded_team_names=uploaded_team_names,
                                uploaded_vehicles=uploaded_vehicles,
                                uploaded_spgs=uploaded_spg_list,
                                team_names_file=TEAM_NAMES_FILE,
                                team_brands_file=TEAM_BRANDS_FILE,
                                vehicles_file=VEHICLES_FILE,
                                brands_file=BRANDS_FILE,
                                spg_file=MASTER_SPG_FILE,
                            )
                            if sync_ok:
                                added_plats = sync_info.get("added_vehicles", [])
                                added_spgs = sync_info.get("added_spgs", [])
                                extra_msgs = []
                                if added_plats:
                                    extra_msgs.append(f"{len(added_plats)} plat kendaraan baru")
                                if added_spgs:
                                    extra_msgs.append(f"{len(added_spgs)} nama SPG baru")
                                extra_str = f" serta {', '.join(extra_msgs)} ditambahkan" if extra_msgs else ""
                                st.success(
                                    f"Jadwal berhasil diperbarui. {len(uploaded_team_names)} nama team "
                                    f"dan alokasi brand otomatis disinkronkan{extra_str}."
                                )
                                st.rerun()
                            st.error(
                                f"Jadwal berhasil diperbarui, tetapi sinkronisasi master gagal: {sync_info.get('error', '')}"
                            )
                        else:
                            st.error(
                                "Jadwal berhasil diperbarui, tetapi sinkronisasi detail jadwal gagal."
                            )
