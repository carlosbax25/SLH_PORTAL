"""Servicio para conectarse a Google Sheets y obtener datos de cartera."""
import csv
import io
import time
import urllib.request
from typing import Optional


SHEET_ID = "1nVUwtQeNyNTdXyUuy2qvn_Nlt6UHJda-c2xf__ETqpo"
EXPORT_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"

# Cache: data + timestamp
_cache = {"data": None, "time": 0}
CACHE_TTL = 300  # 5 minutes

# Column mapping (0-indexed)
COL_CEDULA = 0
COL_CONJUNTO = 1
COL_FECHA_CORTE = 2
COL_TORRE = 3
COL_APTO = 4
COL_PROPIETARIO = 5
COL_CORREO = 6
COL_TELEFONO = 7
COL_MORA = 8
COL_ESTADO = 9
COL_CIUDAD = 10
COL_UBICACION = 11


def fetch_sheet_data() -> list[dict]:
    """Descarga y parsea el Google Sheet completo. Usa caché de 5 min."""
    now = time.time()
    if _cache["data"] is not None and (now - _cache["time"]) < CACHE_TTL:
        return _cache["data"]

    req = urllib.request.Request(EXPORT_URL, headers={"User-Agent": "Mozilla/5.0"})
    resp = urllib.request.urlopen(req, timeout=30)
    data = resp.read().decode("utf-8")
    reader = list(csv.reader(io.StringIO(data)))
    rows = []
    for idx, row in enumerate(reader[1:], start=2):
        if len(row) > COL_ESTADO:
            # Stable row ID based on cedula+conjunto (not row number)
            ced = row[COL_CEDULA].strip()
            conj = row[COL_CONJUNTO].strip()
            prop = row[COL_PROPIETARIO].strip()
            row_id = f"{ced}_{conj}" if ced else f"{prop}_{conj}"
            rows.append({
                "row_id": row_id,
                "cedula": row[COL_CEDULA].strip(),
                "conjunto": row[COL_CONJUNTO].strip(),
                "fecha_corte": row[COL_FECHA_CORTE].strip(),
                "torre": row[COL_TORRE].strip(),
                "apto": row[COL_APTO].strip(),
                "propietario": row[COL_PROPIETARIO].strip(),
                "correo": row[COL_CORREO].strip(),
                "telefono": row[COL_TELEFONO].strip(),
                "mora": row[COL_MORA].strip(),
                "estado": row[COL_ESTADO].strip(),
                "ciudad": row[COL_CIUDAD].strip() if len(row) > COL_CIUDAD else "",
                "ubicacion": row[COL_UBICACION].strip() if len(row) > COL_UBICACION else "",
            })
    _cache["data"] = rows
    _cache["time"] = now
    return rows


def _parse_mora(mora_str: str) -> float:
    """Convierte string de mora a float. Formato: $13,318,962"""
    try:
        clean = mora_str.replace("$", "").replace(",", "").strip()
        return float(clean) if clean else 0.0
    except (ValueError, TypeError):
        return 0.0


def _format_mora(mora_str: str) -> str:
    """Formatea mora a pesos colombianos: $X.XXX.XXX"""
    value = _parse_mora(mora_str)
    if value == 0:
        return "$0"
    formatted = f"{int(value):,}".replace(",", ".")
    return f"${formatted}"


def _parse_fecha_corte(fecha_str: str):
    """Parsea fecha de corte a date. Intenta varios formatos comunes."""
    from datetime import datetime as _dt
    fecha_str = fecha_str.strip()
    if not fecha_str:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%m/%d/%Y", "%d-%m-%Y"):
        try:
            return _dt.strptime(fecha_str, fmt).date()
        except ValueError:
            continue
    return None


def get_juridica_clients() -> list[dict]:
    """Retorna clientes en estado JURIDICA, deduplicados por cédula+conjunto.
    Para duplicados, toma la fila con fecha de corte más reciente.
    """
    all_data = fetch_sheet_data()
    juridica = [r for r in all_data if r["estado"].upper() == "JURIDICA"]

    best: dict[str, dict] = {}
    for r in juridica:
        key = f"{r['cedula']}_{r['conjunto']}" if r["cedula"] else f"{r['propietario']}_{r['conjunto']}"
        if key not in best:
            best[key] = r
        else:
            new_date = _parse_fecha_corte(r["fecha_corte"])
            old_date = _parse_fecha_corte(best[key]["fecha_corte"])
            if new_date and (not old_date or new_date > old_date):
                best[key] = r

    # Format mora to Colombian pesos and sort by highest mora
    result = list(best.values())
    for r in result:
        r["mora_raw"] = _parse_mora(r["mora"])
        r["mora"] = _format_mora(r["mora"])
    result.sort(key=lambda x: x["mora_raw"], reverse=True)
    return result


def get_prejuridica_clients() -> list[dict]:
    """Retorna clientes en estado PRE JURIDICA, deduplicados por cédula+conjunto."""
    all_data = fetch_sheet_data()
    pre = [r for r in all_data if r["estado"].upper() == "PRE JURIDICA"]

    best: dict[str, dict] = {}
    for r in pre:
        key = f"{r['cedula']}_{r['conjunto']}" if r["cedula"] else f"{r['propietario']}_{r['conjunto']}"
        if key not in best:
            best[key] = r
        else:
            # Keep the one with the most recent fecha_corte
            new_date = _parse_fecha_corte(r["fecha_corte"])
            old_date = _parse_fecha_corte(best[key]["fecha_corte"])
            if new_date and (not old_date or new_date > old_date):
                best[key] = r

    result = list(best.values())
    for r in result:
        r["mora_raw"] = _parse_mora(r["mora"])
        r["mora"] = _format_mora(r["mora"])
        r["tiene_correo"] = bool(r.get("correo", "").strip())
    result.sort(key=lambda x: x["mora_raw"], reverse=True)
    return result
