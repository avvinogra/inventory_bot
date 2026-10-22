from .admin import router as admin_router
from .audit import router as audit_router
from .common import router as common_router
from .editing import router as editing_router
from .errors import router as errors_router
from .import_xlsx import router as import_router
from .inventory import router as inventory_router

__all__ = [
    "common_router",
    "inventory_router",
    "editing_router",
    "import_router",
    "audit_router",
    "admin_router",
    "errors_router",
]
