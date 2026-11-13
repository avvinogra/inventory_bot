from .admin import router as admin_router
from .audit import router as audit_router
from .common import router as common_router
from .editing import router as editing_router
from .errors import router as errors_router
from .import_xlsx import router as import_router
from .inventory import router as inventory_router

__all__ = [
    "admin_router",
    "audit_router",
    "common_router",
    "editing_router",
    "errors_router",
    "import_router",
    "inventory_router",
]
