"""
Bug Condition Exploration Tests — Tarea 1

Estos tests codifican el comportamiento ESPERADO (correcto).
DEBEN FALLAR en el código sin corregir, confirmando que el bug existe.

Bug 1: load_cobranza_tracking() almacena IDs con prefijo R{num}_ tal cual,
        por lo que buscar por cedula_conjunto falla.
Bug 2: days_until_notif2() retorna 10 - elapsed en vez de 9 - elapsed,
        mostrando 10 días restantes el mismo día del envío.

**Validates: Requirements 1.1, 1.3, 2.1, 2.2, 2.3**
"""
import re
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import pytest
from hypothesis import given, settings, note
from hypothesis import strategies as st

# Timezone Colombia
COL_TZ = timezone(timedelta(hours=-5))


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

def prefixed_id_strategy():
    """Genera IDs con prefijo R{num}_ seguido de cedula_conjunto."""
    row_num = st.integers(min_value=1, max_value=500)
    cedula = st.from_regex(r"[0-9]{7,10}", fullmatch=True)
    conjunto = st.sampled_from([
        "IGUAZU", "CANDIL", "MANATI", "MALIBU", "PORTAL", "BOSQUES",
    ])
    return st.tuples(row_num, cedula, conjunto).map(
        lambda t: (f"R{t[0]}_{t[1]}_{t[2]}", f"{t[1]}_{t[2]}")
    )


def elapsed_days_strategy():
    """Genera días transcurridos desde el envío de notif1 (0..15)."""
    return st.integers(min_value=0, max_value=15)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tracking_api_response(row_id: str):
    """Simula la respuesta de la API de Sheets para un registro de tracking."""
    now_str = datetime.now(COL_TZ).isoformat()
    return {
        "values": [
            [row_id, "PROPIETARIO_TEST", "CONJUNTO_TEST",
             now_str, "test@example.com", "", ""]
        ]
    }


def _invalidate_cache():
    """Invalida el cache de cobranza antes de cada test."""
    from services.cobranza_service import _cobranza_cache
    _cobranza_cache["data"] = None
    _cobranza_cache["time"] = 0


# ---------------------------------------------------------------------------
# Property 1: Bug Condition — ID Normalization
# ---------------------------------------------------------------------------

class TestBugConditionIDNormalization:
    """
    Property 1: Bug Condition - Normalización de IDs de Tracking

    Para cualquier ID con formato R{num}_{cedula}_{conjunto},
    load_cobranza_tracking() DEBE almacenar bajo la clave {cedula}_{conjunto}.

    **Validates: Requirements 2.1, 2.2**
    """

    @given(data=prefixed_id_strategy())
    @settings(max_examples=30, deadline=5000)
    def test_prefixed_ids_are_normalized(self, data):
        """
        IDs con prefijo R{num}_ deben normalizarse a cedula_conjunto.
        DEBE FALLAR en código sin corregir (el bug es que NO normaliza).
        """
        prefixed_id, expected_key = data
        note(f"prefixed_id={prefixed_id}, expected_key={expected_key}")

        _invalidate_cache()

        notif1_date = datetime.now(COL_TZ).isoformat()
        api_response = {
            "values": [
                [prefixed_id, "PROP_TEST", "CONJ_TEST",
                 notif1_date, "test@test.com", "", ""]
            ]
        }

        with patch("services.cobranza_service._api_request") as mock_api, \
             patch("services.cobranza_service._ensure_cobranza_sheet"):
            mock_api.return_value = api_response

            from services.cobranza_service import load_cobranza_tracking
            tracking = load_cobranza_tracking()

            # The tracking dict SHOULD contain the normalized key
            assert expected_key in tracking, (
                f"Expected key '{expected_key}' not found in tracking. "
                f"Keys present: {list(tracking.keys())}. "
                f"Bug: load_cobranza_tracking() stores prefixed ID as-is."
            )


    def test_specific_example_R2_1234567_IGUAZU(self):
        """
        Ejemplo concreto: R2_1234567_IGUAZU debe encontrarse como 1234567_IGUAZU.
        DEBE FALLAR en código sin corregir.
        """
        _invalidate_cache()

        notif1_date = datetime.now(COL_TZ).isoformat()
        api_response = {
            "values": [
                ["R2_1234567_IGUAZU", "CARLOS TEST", "IGUAZU",
                 notif1_date, "carlos@test.com", "", ""]
            ]
        }

        with patch("services.cobranza_service._api_request") as mock_api, \
             patch("services.cobranza_service._ensure_cobranza_sheet"):
            mock_api.return_value = api_response

            from services.cobranza_service import load_cobranza_tracking
            tracking = load_cobranza_tracking()

            assert "1234567_IGUAZU" in tracking, (
                f"Expected '1234567_IGUAZU' in tracking but got keys: "
                f"{list(tracking.keys())}. Bug confirmed: prefixed IDs not normalized."
            )
            info = tracking["1234567_IGUAZU"]
            assert info["notif1_date"] == notif1_date


# ---------------------------------------------------------------------------
# Property 2: Bug Condition — Days Calculation
# ---------------------------------------------------------------------------

class TestBugConditionDaysCalculation:
    """
    Property 2: Bug Condition - Cálculo Correcto de Días Restantes

    Para cualquier consulta donde notif1 fue enviada hace `elapsed` días,
    days_until_notif2() DEBE retornar max(0, 9 - elapsed).

    **Validates: Requirements 2.3, 2.4**
    """

    @given(elapsed=elapsed_days_strategy())
    @settings(max_examples=30, deadline=5000)
    def test_days_until_notif2_formula(self, elapsed):
        """
        days_until_notif2() debe retornar max(0, 9 - elapsed).
        DEBE FALLAR en código sin corregir (retorna 10 - elapsed).
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

        expected = max(0, 9 - elapsed)

        # Mock get_notification_status to return the notif1_date
        with patch("services.cobranza_service.get_notification_status") as mock_status:
            mock_status.return_value = {
                "notif1_date": notif1_str,
                "notif1_email": "test@test.com",
                "notif2_date": "",
                "notif2_email": "",
            }

            from services.cobranza_service import days_until_notif2
            result = days_until_notif2(row_id)

            assert result == expected, (
                f"days_until_notif2() returned {result} but expected {expected} "
                f"(elapsed={elapsed}). Bug: uses 10-elapsed instead of 9-elapsed."
            )


    def test_same_day_returns_9_not_10(self):
        """
        El mismo día del envío, days_until_notif2() debe retornar 9, no 10.
        DEBE FALLAR en código sin corregir.
        """
        _invalidate_cache()

        row_id = "1234567_IGUAZU"
        today = datetime.now(COL_TZ)
        notif1_str = today.isoformat()

        with patch("services.cobranza_service.get_notification_status") as mock_status:
            mock_status.return_value = {
                "notif1_date": notif1_str,
                "notif1_email": "test@test.com",
                "notif2_date": "",
                "notif2_email": "",
            }

            from services.cobranza_service import days_until_notif2
            result = days_until_notif2(row_id)

            assert result == 9, (
                f"Same-day: days_until_notif2() returned {result}, expected 9. "
                f"Bug: formula uses 10-elapsed instead of 9-elapsed."
            )

    def test_day_9_returns_0_not_1(self):
        """
        Después de 9 días, days_until_notif2() debe retornar 0 (ya se puede enviar).
        DEBE FALLAR en código sin corregir (retorna 1).
        """
        _invalidate_cache()

        row_id = "1234567_IGUAZU"
        today = datetime.now(COL_TZ)
        notif1_date = today - timedelta(days=9)
        notif1_str = notif1_date.isoformat()

        with patch("services.cobranza_service.get_notification_status") as mock_status:
            mock_status.return_value = {
                "notif1_date": notif1_str,
                "notif1_email": "test@test.com",
                "notif2_date": "",
                "notif2_email": "",
            }

            from services.cobranza_service import days_until_notif2
            result = days_until_notif2(row_id)

            assert result == 0, (
                f"Day 9: days_until_notif2() returned {result}, expected 0. "
                f"Bug: formula uses 10-elapsed instead of 9-elapsed."
            )
