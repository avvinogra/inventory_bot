from .admin import router as admin_router
from .common import router as common_router
from .errors import router as errors_router
from .inventory import router as inventory_router
from .printing import router as printing_router

__all__ = ["common_router", "inventory_router", "printing_router", "admin_router", "errors_router"]

