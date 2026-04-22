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
            })
    return rows


def get_juridica_clients() -> list[dict]:
    """Retorna todas las filas en estado JURIDICA, sin deduplicar."""
    all_data = fetch_sheet_data()
    return [r for r in all_data if r["estado"].upper() == "JURIDICA"]
