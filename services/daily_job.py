"""Job diario: detecta cambios en JURIDICA y envía resumen por correo."""
import json
import urllib.parse
from datetime import datetime, timezone, timedelta
from services.sheets_service import get_juridica_clients
from services.sheets_tracking import _api_request, _ensure_tracking_sheet, load_tracking
from services.email_service import send_daily_report

COL_TZ = timezone(timedelta(hours=-5))
SNAPSHOT_SHEET = "SNAPSHOT"


def _ensure_snapshot_sheet():
    """Crea la hoja SNAPSHOT si no existe."""
    result = _api_request("GET", "?fields=sheets.properties.title")
    if not result:
        return
    sheets = [s["properties"]["title"] for s in result.get("sheets", [])]
    if SNAPSHOT_SHEET not in sheets:
        _api_request("POST", ":batchUpdate", {
            "requests": [{"addSheet": {"properties": {"title": SNAPSHOT_SHEET}}}]
        })


def _load_snapshot() -> set:
    """Carga el snapshot anterior (set de row_ids)."""
    _ensure_snapshot_sheet()
    rng = urllib.parse.quote(f"{SNAPSHOT_SHEET}!A2:A5000")
    result = _api_request("GET", f"values/{rng}")
    if not result:
        return set()
    rows = result.get("values", [])
    return {r[0] for r in rows if r}


def _save_snapshot(clients: list):
    """Guarda el snapshot actual."""
    _ensure_snapshot_sheet()
    rng = urllib.parse.quote(f"{SNAPSHOT_SHEET}!A:D")
    _api_request("POST", f"values/{rng}:clear", {})
    header = [["ROW_ID", "PROPIETARIO", "CEDULA", "CONJUNTO"]]
    rows = [[c["row_id"], c["propietario"], c["cedula"], c["conjunto"]] for c in clients]
    _api_request("PUT",
        f"values/{urllib.parse.quote(f'{SNAPSHOT_SHEET}!A1')}?valueInputOption=RAW",
        {"values": header + rows})


def run_daily_report():
    """Ejecuta el reporte diario."""
    print("Running daily report...")
    clients = get_juridica_clients()
    current_ids = {c["row_id"] for c in clients}
    client_map = {c["row_id"]: c for c in clients}

    prev_ids = _load_snapshot()

    # Detect changes
    nuevos_ids = current_ids - prev_ids
    salieron_ids = prev_ids - current_ids

    nuevos = [client_map[rid] for rid in nuevos_ids if rid in client_map]
    salieron = [{"propietario": rid, "cedula": "", "conjunto": "", "nuevo_estado": "Salió"} for rid in salieron_ids]

    # Demandas generated today
    tracking = load_tracking()
    today = datetime.now(COL_TZ).strftime("%Y-%m-%d")
    demandas_hoy = []
    for row_id, info in tracking.items():
        gen_date = info.get("generated_at", "")[:10]
        if gen_date == today:
            demandas_hoy.append({
                "propietario": info.get("propietario", ""),
                "cedula": row_id,
                "conjunto": info.get("conjunto", ""),
                "mora": info.get("mora", ""),
            })

    generated = len(tracking)
    data = {
        "total": len(clients),
        "generadas": generated,
        "pendientes": len(clients) - generated,
        "nuevos": nuevos,
        "salieron": salieron,
        "demandas_hoy": demandas_hoy,
    }

    send_daily_report(data)
    _save_snapshot(clients)
    print("Daily report complete.")


if __name__ == "__main__":
    run_daily_report()
