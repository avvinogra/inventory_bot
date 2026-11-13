"""Экспорт базы в Excel: временный файл + гарантированная очистка.

Раньше: export_to_excel() складывал файл в data/ и НЕ удалял его —
после сотни выгрузок в volume копились сотни xlsx.
Теперь: пишем во временный файл и удаляем сразу после отдачи клиенту
(BackgroundTask выполняется ПОСЛЕ отправки ответа).
"""

import os
import tempfile
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

import config
from excel_export import export_to_excel
from web.security import require_auth

router = APIRouter()

EXPORT_MAX_AGE_SECONDS = 24 * 60 * 60  # чистить старые экспорты старше суток


def _safe_unlink(path: str):
    """Удаляет файл, игнорируя ошибки (файл уже удалён/недоступен)."""
    try:
        os.unlink(path)
    except OSError:
        pass


def _cleanup_old_exports():
    """Разовая зачистка legacy-файлов: старые версии /export оставляли
    xlsx в каталоге БД и никогда их не удаляли."""
    data_dir = os.path.dirname(config.DB_PATH) or "."
    now = time.time()
    try:
        names = os.listdir(data_dir)
    except OSError:
        return
    for name in names:
        if not (name.startswith("inventory_export_") and name.endswith(".xlsx")):
            continue
        file_path = os.path.join(data_dir, name)
        try:
            if now - os.path.getmtime(file_path) > EXPORT_MAX_AGE_SECONDS:
                os.unlink(file_path)
        except OSError:
            continue


_cleanup_old_exports()


@router.get("/export")
def export(request: Request):
    require_auth(request)
    # mkstemp — безопасное создание (O_CREAT|O_EXCL, права 0600).
    fd, tmp_path = tempfile.mkstemp(suffix=".xlsx")
    os.close(fd)  # закрываем дескриптор: openpyxl откроет файл сам
    try:
        path = export_to_excel(tmp_path)
        if not path:
            raise HTTPException(status_code=400, detail="База пуста")
    except HTTPException:
        _safe_unlink(tmp_path)
        raise
    except Exception as e:
        _safe_unlink(tmp_path)  # о любой ошибке генерации xlsx,
        raise HTTPException(status_code=500, detail=f"Ошибка экспорта: {e}") from e
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="inventory.xlsx",
        background=BackgroundTask(_safe_unlink, path),  # удаление после отдачи
    )
