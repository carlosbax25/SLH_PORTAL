"""
Preservation Tests — Tarea 2

Estos tests capturan el comportamiento CORRECTO existente que NO debe cambiar
después de aplicar la corrección de bugs.

DEBEN PASAR en el código sin corregir (confirman el comportamiento base).
DEBEN SEGUIR PASANDO después de la corrección (confirman que no hay regresiones).

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6**
"""
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest
from hypothesis import given, settings, note, assume
from hypothesis import strategies as st

# Timezone Colombia
COL_TZ = timezone(timedelta(hours=-5))


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

def clean_id_strategy():
    """Genera IDs SIN prefijo R{num}_ — formato estable cedula_conjunto."""
    cedula = st.from_regex(r"[0-9]{7,10}", fullmatch=True)
    conjunto = st.sampled_from([
        "IGUAZU", "CANDIL", "MANATI", "MALIBU", "PORTAL", "BOSQUES",
    ])
    return st.tuples(cedula, conjunto).map(lambda t: f"{t[0]}_{t[1]}")


def elapsed_days_strategy():
    """Genera días transcurridos desde el envío de notif1 (0..30)."""
    return st.integers(min_value=0, max_value=30)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _invalidate_cache():
    """Invalida el cache de cobranza antes de cada test."""
    from services.cobranza_service import _cobranza_cache
    _cobranza_cache["data"] = None
    _cobranza_cache["time"] = 0


# ---------------------------------------------------------------------------
# Property 3: Preservation — IDs sin prefijo cargan correctamente
# ---------------------------------------------------------------------------

class TestPreservationCleanIDs:
    """
    Property 3: Preservation - IDs sin prefijo se cargan correctamente.

    Para todo ID con formato estable cedula_conjunto (sin prefijo R{num}_),
    load_cobranza_tracking() DEBE almacenar bajo esa misma clave.

    **Validates: Requirements 3.1, 3.2**
    """

    @given(row_id=clean_id_strategy())
    @settings(max_examples=30, deadline=5000)
    def test_clean_ids_load_correctly(self, row_id):
        """
        IDs sin prefijo R{num}_ deben cargarse bajo su misma clave.
        DEBE PASAR en código sin corregir (este comportamiento ya funciona).
        """
        note(f"row_id={row_id}")
        _invalidate_cache()

        notif1_date = datetime.now(COL_TZ).isoformat()
        api_response = {
            "values": [
                [row_id, "PROP_TEST", "CONJ_TEST",
                 notif1_date, "test@test.com", "", ""]
            ]
        }

        with patch("services.cobranza_service._api_request") as mock_api, \
             patch("services.cobranza_service._ensure_cobranza_sheet"):
            mock_api.return_value = api_response

            from services.cobranza_service import load_cobranza_tracking
            tracking = load_cobranza_tracking()

            assert row_id in tracking, (
                f"Expected key '{row_id}' in tracking but got: {list(tracking.keys())}"
            )
            assert tracking[row_id]["notif1_date"] == notif1_date
            assert tracking[row_id]["propietario"] == "PROP_TEST"
            assert tracking[row_id]["conjunto"] == "CONJ_TEST"


# ---------------------------------------------------------------------------
# Property 3: Preservation — can_send_notif2 con IDs sin prefijo
# ---------------------------------------------------------------------------

class TestPreservationCanSendNotif2:
    """
    Property 3: Preservation - can_send_notif2() funciona correctamente
    para IDs sin prefijo.

    En el código actual (sin corregir), can_send_notif2() retorna False
    cuando elapsed < 10 y True cuando elapsed >= 10.

    **Validates: Requirements 3.5, 3.6**
    """

    @given(elapsed=elapsed_days_strategy())
    @settings(max_examples=30, deadline=5000)
    def test_can_send_notif2_threshold(self, elapsed):
        """
        can_send_notif2() retorna False si elapsed < 10, True si elapsed >= 10.
        DEBE PASAR en código sin corregir.
        """
        _invalidate_cache()

        row_id = "9999999_TESTCONJ"
        today = datetime.now(COL_TZ).date()
        notif1_date = datetime(
            today.year, today.month, today.day,
            tzinfo=COL_TZ
        ) - timedelta(days=elapsed)
        notif1_str = notif1_date.isoformat()

        note(f"elapsed={elapsed}, notif1_date={notif1_str}")

        expected = elapsed >= 10

        with patch("services.cobranza_service.get_notification_status") as mock_status:
            mock_status.return_value = {
                "notif1_date": notif1_str,
                "notif1_email": "test@test.com",
                "notif2_date": "",
                "notif2_email": "",
            }

            from services.cobranza_service import can_send_notif2
            result = can_send_notif2(row_id)

            assert result == expected, (
                f"can_send_notif2() returned {result} but expected {expected} "
                f"(elapsed={elapsed})"
            )


# ---------------------------------------------------------------------------
# Property 3: Preservation — Sin notif1, no hay Aviso 2
# ---------------------------------------------------------------------------

class TestPreservationNoNotif1:
    """
    Property 3: Preservation - Propietarios sin Notificación 1 no obtienen
    Aviso 2.

    can_send_notif2() retorna False y days_until_notif2() retorna -1
    cuando no hay notif1_date.

    **Validates: Requirements 3.2, 3.3**
    """

    @given(row_id=clean_id_strategy())
    @settings(max_examples=20, deadline=5000)
    def test_can_send_notif2_no_notif1_returns_false(self, row_id):
        """
        Sin notif1_date, can_send_notif2() debe retornar False.
        DEBE PASAR en código sin corregir.
        """
        _invalidate_cache()

        with patch("services.cobranza_service.get_notification_status") as mock_status:
            mock_status.return_value = {
                "notif1_date": "",
                "notif1_email": "",
                "notif2_date": "",
                "notif2_email": "",
            }

            from services.cobranza_service import can_send_notif2
            result = can_send_notif2(row_id)

            assert result is False, (
                f"can_send_notif2('{row_id}') returned {result} without notif1, "
                f"expected False"
            )

    @given(row_id=clean_id_strategy())
    @settings(max_examples=20, deadline=5000)
    def test_days_until_notif2_no_notif1_returns_minus1(self, row_id):
        """
        Sin notif1_date, days_until_notif2() debe retornar -1.
        DEBE PASAR en código sin corregir.
        """
        _invalidate_cache()

        with patch("services.cobranza_service.get_notification_status") as mock_status:
            mock_status.return_value = {
                "notif1_date": "",
                "notif1_email": "",
                "notif2_date": "",
                "notif2_email": "",
            }

            from services.cobranza_service import days_until_notif2
            result = days_until_notif2(row_id)

            assert result == -1, (
                f"days_until_notif2('{row_id}') returned {result} without notif1, "
                f"expected -1"
            )

    def test_empty_tracking_returns_false(self):
        """
        Con tracking vacío, can_send_notif2() retorna False.
        DEBE PASAR en código sin corregir.
        """
        _invalidate_cache()

        with patch("services.cobranza_service.get_notification_status") as mock_status:
            mock_status.return_value = {}

            from services.cobranza_service import can_send_notif2
            result = can_send_notif2("1234567_IGUAZU")

            assert result is False

    def test_empty_tracking_days_returns_minus1(self):
        """
        Con tracking vacío, days_until_notif2() retorna -1.
        DEBE PASAR en código sin corregir.
        """
        _invalidate_cache()

        with patch("services.cobranza_service.get_notification_status") as mock_status:
            mock_status.return_value = {}

            from services.cobranza_service import days_until_notif2
            result = days_until_notif2("1234567_IGUAZU")

            assert result == -1
