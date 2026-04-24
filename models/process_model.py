"""Modelo de datos para procesos de automatización."""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from datetime import datetime


class ProcessStatus(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"
    MAINTENANCE = "maintenance"
    COMING_SOON = "coming_soon"


@dataclass
class AutomationProcess:
    id: int
    name: str
    slug: str
    description: str
    icon: str
    status: ProcessStatus
    category: str
    color_accent: str = "#966e1e"

    def get_status_color(self) -> str:
        colors = {
            ProcessStatus.ACTIVE: "#28a745",
            ProcessStatus.INACTIVE: "#6c757d",
            ProcessStatus.ERROR: "#dc3545",
            ProcessStatus.MAINTENANCE: "#ffc107",
            ProcessStatus.COMING_SOON: "#6c757d",
        }
        return colors.get(self.status, "#6c757d")

    def get_status_label(self) -> str:
        labels = {
            ProcessStatus.ACTIVE: "Activo",
            ProcessStatus.INACTIVE: "Inactivo",
            ProcessStatus.ERROR: "Error",
            ProcessStatus.MAINTENANCE: "Mantenimiento",
            ProcessStatus.COMING_SOON: "En Construcción",
        }
        return labels.get(self.status, "Desconocido")


def get_all_processes() -> list[AutomationProcess]:
    """Retorna todos los procesos de automatización."""
    return [
        AutomationProcess(
            id=1,
            name="COBRANZA",
            slug="cobranza",
            description="Gestión de cobro pre-jurídico y notificaciones a propietarios en mora",
            icon="fa-money-bill-wave",
            status=ProcessStatus.ACTIVE,
            category="Finanzas",
            color_accent="#966e1e",
        ),
        AutomationProcess(
            id=2,
            name="INMOBILIARIA",
            slug="inmobiliaria",
            description="Automatización de procesos inmobiliarios y gestión de propiedades",
            icon="fa-building",
            status=ProcessStatus.COMING_SOON,
            category="Bienes Raíces",
            color_accent="#af8e4b",
        ),
        AutomationProcess(
            id=3,
            name="JURÍDICA",
            slug="juridica",
            description="Automatización de procesos legales y gestión jurídica corporativa",
            icon="fa-gavel",
            status=ProcessStatus.ACTIVE,
            category="Legal",
            color_accent="#966e1e",
        ),
    ]


def get_process_by_slug(slug: str) -> Optional[AutomationProcess]:
    for p in get_all_processes():
        if p.slug == slug:
            return p
    return None
