"""Servicio para conectarse a Google Sheets y obtener datos de cartera."""
import csv
import io
import urllib.request
from typing import Optional


SHEET_ID = "1nVUwtQeNyNTdXyUuy2qvn_Nlt6UHJda-c2xf__ETqpo"
EXPORT_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"

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
    """Descarga y parsea el Google Sheet completo."""
    req = urllib.request.Request(EXPORT_URL, headers={"User-Agent": "Mozilla/5.0"})
    resp = urllib.request.urlopen(req, timeout=30)
    data = resp.read().decode("utf-8")
    reader = list(csv.reader(io.StringIO(data)))
    rows = []
    for idx, row in enumerate(reader[1:], start=2):
        if len(row) > COL_ESTADO:
            # Unique row ID based on row number in sheet
            row_id = f"R{idx}_{row[COL_CEDULA].strip()}_{row[COL_CONJUNTO].strip()}"
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


def get_juridica_clients() -> list[dict]:
    """Retorna clientes en estado JURIDICA, deduplicados por cédula+conjunto.
    Para duplicados, toma la fila con mora más alta (periodo más reciente).
    """
    all_data = fetch_sheet_data()
    juridica = [r for r in all_data if r["estado"].upper() == "JURIDICA"]

    # Deduplicate by (cedula+conjunto) or (propietario+conjunto) if no cedula
    best: dict[str, dict] = {}
    for r in juridica:
        key = f"{r['cedula']}_{r['conjunto']}" if r["cedula"] else f"{r['propietario']}_{r['conjunto']}"
        if key not in best or _parse_mora(r["mora"]) > _parse_mora(best[key]["mora"]):
            best[key] = r

    # Format mora to Colombian pesos and sort by highest mora
    result = list(best.values())
    for r in result:
        r["mora_raw"] = _parse_mora(r["mora"])
        r["mora"] = _format_mora(r["mora"])
    result.sort(key=lambda x: x["mora_raw"], reverse=True)
    return result
