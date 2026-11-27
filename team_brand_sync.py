import json
import os
import re

TEAM_NAMES_FILE = "master_nama_team.json"
TEAM_BRANDS_FILE = "master_team_brand.json"
BRANDS_FILE = "master_brand_rokok.json"
VEHICLES_FILE = "master_plat_kendaraan.json"
MASTER_SPG_FILE = "master_nama_spg.json"

DEFAULT_TEAM_BRANDS_FALLBACK = [
    "D.Super 12",
    "D.76 Apel",
    "D.76 Apel Royal",
    "Black Matcha K12",
    "Djarum 76 Aksara",
    "Black Matcha Siro",
    "Black Matcha Kuro",
    "D.Super Kretek",
]

# Kata non-varian pada nama team yang diabaikan saat mencocokkan brand otomatis
TEAM_KEYWORD_STOPWORDS = {
    "team",
    "tim",
    "spg",
    "yc1",
    "yc2",
    "yc3",
    "yc4",
    "yc5",
    "kretek",
    "k12",
    "siro",
    "kuro",
    "royal",
    "djarum",
}


def normalize_team_label(value) -> str:
    return " ".join(str(value or "").strip().split()).casefold()


def _read_json_safe(path: str, fallback):
    if not os.path.exists(path):
        return fallback
    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return fallback


def _write_json_atomic(path: str, payload) -> bool:
    tmp_path = f"{path}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
        return True
    except Exception:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        return False


def load_active_brands(brands_file: str = BRANDS_FILE, fallback: list[str] | None = None) -> list[str]:
    base = list(fallback) if fallback else list(DEFAULT_TEAM_BRANDS_FALLBACK)
    raw = _read_json_safe(brands_file, base)
    if not isinstance(raw, list):
        return base
    cleaned = []
    seen = set()
    for item in raw:
        label = str(item or "").strip()
        if label and label.casefold() not in seen:
            seen.add(label.casefold())
            cleaned.append(label)
    return cleaned or base


def extract_team_brand_keywords(team_name: str) -> list[str]:
    raw_tokens = re.split(r"[\s\-_./|]+", str(team_name or "").strip())
    keywords = []
    seen = set()
    for token in raw_tokens:
        cleaned = re.sub(r"[^a-zA-Z0-9]", "", token).casefold()
        if len(cleaned) < 3 or cleaned.isdigit() or cleaned in TEAM_KEYWORD_STOPWORDS:
            continue
        if cleaned not in seen:
            seen.add(cleaned)
            keywords.append(cleaned)
    return keywords


def match_brands_by_team_name(team_name: str, all_brands: list[str]) -> list[str]:
    clean_brands = [str(b).strip() for b in all_brands if str(b).strip()]
    if not clean_brands:
        return []

    keywords = extract_team_brand_keywords(team_name)
    if not keywords:
        return clean_brands

    matched = [
        brand
        for brand in clean_brands
        if any(kw in brand.casefold() for kw in keywords)
    ]
    return matched if matched else clean_brands


def resolve_team_allowed_brands(
    team_name: str,
    all_brands: list[str] | None = None,
    team_brands_map: dict | None = None,
    team_names_map: dict | None = None,
    prefer_keyword_match: bool = True,
) -> list[str]:
    """
    Menentukan daftar brand yang boleh dibawa oleh `team_name`:
    1. Jika `prefer_keyword_match=True` dan nama team mengandung kata kunci varian
       (mis. Matcha, Super, Apel, Aksara), langsung filter brand yang mengandung kata kunci tsb.
    2. Jika ada konfigurasi manual di `master_team_brand.json` untuk team tsb, gunakan daftar tsb.
    3. Fallback ke seluruh brand aktif agar dropdown SPG tidak pernah kosong.
    """
    brands_pool = load_active_brands() if all_brands is None else [
        str(b).strip() for b in all_brands if str(b).strip()
    ]
    if not brands_pool:
        return []

    keywords = extract_team_brand_keywords(team_name)
    if prefer_keyword_match and keywords:
        keyword_matched = [
            brand
            for brand in brands_pool
            if any(kw in brand.casefold() for kw in keywords)
        ]
        if keyword_matched:
            return keyword_matched

    allocations = (
        _read_json_safe(TEAM_BRANDS_FILE, {})
        if team_brands_map is None
        else team_brands_map
    )
    if isinstance(allocations, dict) and allocations:
        norm_target = normalize_team_label(team_name)
        candidate_keys = {norm_target}
        names_dict = (
            _read_json_safe(TEAM_NAMES_FILE, {})
            if team_names_map is None
            else team_names_map
        )
        if isinstance(names_dict, dict):
            for slot_key, alias_val in names_dict.items():
                if normalize_team_label(alias_val) == norm_target:
                    candidate_keys.add(normalize_team_label(slot_key))
                elif normalize_team_label(slot_key) == norm_target and str(alias_val or "").strip():
                    candidate_keys.add(normalize_team_label(alias_val))

        allowed_lookup = {b.casefold(): b for b in brands_pool}
        for raw_key, assigned_list in allocations.items():
            if normalize_team_label(raw_key) in candidate_keys and isinstance(assigned_list, list):
                resolved = [
                    allowed_lookup[str(b).strip().casefold()]
                    for b in assigned_list
                    if str(b).strip().casefold() in allowed_lookup
                ]
                if resolved:
                    return resolved

    return match_brands_by_team_name(team_name, brands_pool)


def sync_masters_from_schedule_upload(
    uploaded_team_names: list[str],
    uploaded_vehicles: dict[str, str] | None = None,
    uploaded_spgs: list[str] | None = None,
    team_names_file: str = TEAM_NAMES_FILE,
    team_brands_file: str = TEAM_BRANDS_FILE,
    vehicles_file: str = VEHICLES_FILE,
    brands_file: str = BRANDS_FILE,
    spg_file: str = MASTER_SPG_FILE,
) -> tuple[bool, dict]:
    """
    Sinkronisasi otomatis saat admin mengunggah file Excel jadwal:
    - Mengisi master_nama_team.json berdasarkan urutan nama team aktif di Excel.
    - Menggabungkan plat kendaraan baru dari Excel ke master_plat_kendaraan.json.
    - Menggabungkan nama SPG 1 & SPG 2 baru dari Excel ke master_nama_spg.json.
    - Menyelaraskan master_team_brand.json berdasarkan kata kunci nama team.
    """
    clean_teams = []
    seen_teams = set()
    for name in uploaded_team_names:
        label = str(name or "").strip()
        if label and label.casefold() not in seen_teams:
            seen_teams.add(label.casefold())
            clean_teams.append(label)

    if not clean_teams or len(clean_teams) > 20:
        return False, {"error": "Jumlah team aktif harus antara 1 sampai 20."}

    team_names_payload = {
        f"Team SPG {idx}": clean_teams[idx - 1] if idx <= len(clean_teams) else ""
        for idx in range(1, 21)
    }
    if not _write_json_atomic(team_names_file, team_names_payload):
        return False, {"error": f"Gagal menulis {team_names_file}"}

    # Sinkronisasi plat kendaraan dari jadwal Excel ke master_plat_kendaraan.json
    added_vehicles = []
    if uploaded_vehicles:
        existing_raw = _read_json_safe(vehicles_file, [])
        if isinstance(existing_raw, dict):
            existing_list = list(existing_raw.values())
        elif isinstance(existing_raw, list):
            existing_list = existing_raw
        else:
            existing_list = []

        merged_vehicles = []
        seen_vehicles = set()
        for item in existing_list:
            plate = str(item or "").strip().upper()
            if plate and plate.casefold() not in seen_vehicles:
                seen_vehicles.add(plate.casefold())
                merged_vehicles.append(plate)

        for raw_plate in uploaded_vehicles.values():
            plate = str(raw_plate or "").strip().upper()
            if plate and plate not in {"-", "NAN", "NONE"} and plate.casefold() not in seen_vehicles:
                seen_vehicles.add(plate.casefold())
                merged_vehicles.append(plate)
                added_vehicles.append(plate)

        if added_vehicles:
            _write_json_atomic(vehicles_file, merged_vehicles)

    # Sinkronisasi nama SPG 1 & SPG 2 dari jadwal Excel ke master_nama_spg.json
    added_spgs = []
    if uploaded_spgs:
        existing_spg_raw = _read_json_safe(spg_file, [])
        existing_spgs = existing_spg_raw if isinstance(existing_spg_raw, list) else []
        merged_spgs = []
        seen_spgs = set()
        for item in existing_spgs:
            spg_name = str(item or "").strip()
            if spg_name and spg_name.casefold() not in seen_spgs:
                seen_spgs.add(spg_name.casefold())
                merged_spgs.append(spg_name)

        for raw_spg in uploaded_spgs:
            spg_name = str(raw_spg or "").strip()
            if spg_name and spg_name.casefold() not in {"-", "nan", "none"} and spg_name.casefold() not in seen_spgs:
                seen_spgs.add(spg_name.casefold())
                merged_spgs.append(spg_name)
                added_spgs.append(spg_name)

        if added_spgs:
            _write_json_atomic(spg_file, sorted(merged_spgs, key=str.casefold))

    # Sinkronisasi alokasi brand per team sesuai kata kunci nama team dari Excel
    all_brands = load_active_brands(brands_file)
    synced_team_brands = {
        team_label: match_brands_by_team_name(team_label, all_brands)
        for team_label in clean_teams
    }
    if not _write_json_atomic(team_brands_file, synced_team_brands):
        return False, {"error": f"Gagal menulis {team_brands_file}"}

    return True, {
        "teams": clean_teams,
        "added_vehicles": added_vehicles,
        "added_spgs": added_spgs,
        "team_brands": synced_team_brands,
    }

HARGA_KONSUMEN_FILE = "master_harga_konsumen.json"

DEFAULT_HARGA_KONSUMEN_FALLBACK = {
    "Black Matcha K12": 22000,
    "D.Super 12": 24000,
    "D.Super Kretek": 16000,
    "D.76 Apel Royal": 18000,
    "D.76 Apel": 16000,
    "Djarum 76 Aksara": 16000,
    "Black Matcha Siro": 23000,
    "Black Matcha Kuro": 23000,
}


def normalize_brand_label(brand: str) -> str:
    return "".join(str(brand or "").casefold().split())


def load_consumer_prices(harga_file: str = HARGA_KONSUMEN_FILE) -> dict[str, int]:
    raw = _read_json_safe(harga_file, DEFAULT_HARGA_KONSUMEN_FALLBACK)
    if not isinstance(raw, dict):
        return dict(DEFAULT_HARGA_KONSUMEN_FALLBACK)
    cleaned: dict[str, int] = {}
    for k, v in raw.items():
        label = str(k or "").strip()
        if not label:
            continue
        try:
            cleaned[label] = max(0, int(float(v)))
        except (ValueError, TypeError):
            cleaned[label] = 0
    return cleaned if cleaned else dict(DEFAULT_HARGA_KONSUMEN_FALLBACK)


def save_consumer_prices(harga_map: dict, harga_file: str = HARGA_KONSUMEN_FILE) -> bool:
    cleaned: dict[str, int] = {}
    for k, v in (harga_map or {}).items():
        label = str(k or "").strip()
        if not label:
            continue
        try:
            cleaned[label] = max(0, int(float(v)))
        except (ValueError, TypeError):
            cleaned[label] = 0
    return _write_json_atomic(harga_file, cleaned)


def get_consumer_price_for_brand(brand: str, harga_map: dict | None = None) -> int:
    hmap = load_consumer_prices() if harga_map is None else harga_map
    b_norm = normalize_brand_label(brand)
    if not b_norm:
        return 0
    for k, v in hmap.items():
        if normalize_brand_label(k) == b_norm:
            try:
                return max(0, int(float(v)))
            except (ValueError, TypeError):
                return 0
    return 0


def sync_brand_price_entry(
    brand_name: str,
    price_per_pack: int,
    brands_file: str = BRANDS_FILE,
    harga_file: str = HARGA_KONSUMEN_FILE,
) -> tuple[bool, dict]:
    """Menyimpan merk baru (jika belum ada di daftar merk) dan memperbarui harga konsumen per bungkus."""
    b_clean = str(brand_name or "").strip()
    if not b_clean:
        return False, {"error": "Nama merk tidak boleh kosong."}

    try:
        price_val = max(0, int(float(price_per_pack)))
    except (ValueError, TypeError):
        price_val = 0

    brands = load_active_brands(brands_file)
    if not any(normalize_brand_label(b) == normalize_brand_label(b_clean) for b in brands):
        brands.append(b_clean)
        if not _write_json_atomic(brands_file, brands):
            return False, {"error": f"Gagal memperbarui {brands_file}"}

    harga_map = load_consumer_prices(harga_file)
    replaced_key = None
    for existing_k in list(harga_map.keys()):
        if normalize_brand_label(existing_k) == normalize_brand_label(b_clean):
            replaced_key = existing_k
            break
    if replaced_key and replaced_key != b_clean:
        del harga_map[replaced_key]
    harga_map[b_clean] = price_val

    if not save_consumer_prices(harga_map, harga_file):
        return False, {"error": f"Gagal memperbarui {harga_file}"}

    return True, {
        "brand": b_clean,
        "price": price_val,
        "brands": brands,
        "prices": harga_map,
    }
