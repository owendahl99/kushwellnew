# app/utils/uploads.py
from __future__ import annotations

import os
from datetime import datetime
from typing import Optional, Iterable

from flask import current_app
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import UploadedFile


DEFAULT_ALLOWED_EXTS = {"png", "jpg", "jpeg", "webp", "gif", "svg"}


def _has_allowed_ext(filename: str, allowed_exts: Iterable[str]) -> bool:
    if "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in set(allowed_exts)


def save_dev_static(
    file_storage,
    subdir: Optional[str] = None,
    uploaded_by_id: Optional[int] = None,
    allowed_exts: Optional[Iterable[str]] = None,
) -> UploadedFile:
    """
    Save an uploaded file under app/static/<subdir>/ and create an UploadedFile row.

    - Stores only the path *relative* to /static (e.g., "output/my_logo.png") in UploadedFile.filepath.
    - Returns the persisted UploadedFile instance (with id after flush).

    Parameters
    ----------
    file_storage : werkzeug.datastructures.FileStorage
        Incoming file from `request.files[...]`.
    subdir : str | None
        Folder under /static/ (default: current_app.config["STATIC_UPLOAD_SUBDIR"] or "output").
    uploaded_by_id : int | None
        Optional user id to attribute the upload to.
    allowed_exts : Iterable[str] | None
        Whitelist of allowed extensions (default: DEFAULT_ALLOWED_EXTS).

    Raises
    ------
    ValueError
        If no file is provided, no filename, or extension not allowed.
    """
    if not file_storage or not getattr(file_storage, "filename", ""):
        raise ValueError("No file provided")

    filename = secure_filename(file_storage.filename)
    if not filename:
        raise ValueError("Invalid filename")

    exts = allowed_exts or DEFAULT_ALLOWED_EXTS
    if not _has_allowed_ext(filename, exts):
        allowed_list = ", ".join(sorted(exts))
        raise ValueError(f"Unsupported file type. Allowed: {allowed_list}")

    # Resolve subdir and disk path
    static_subdir = subdir or current_app.config.get("STATIC_UPLOAD_SUBDIR", "output")
    disk_dir = os.path.join(current_app.root_path, "static", static_subdir)
    os.makedirs(disk_dir, exist_ok=True)

    disk_path = os.path.join(disk_dir, filename)
    file_storage.save(disk_path)

    # Store path relative to /static for easy url_for("static", filename=...)
    rel_path = f"{static_subdir}/{filename}"

    uf = UploadedFile(
        filename=filename,
        filepath=rel_path,
        uploaded_by_id=uploaded_by_id,
        uploaded_at=datetime.utcnow(),
    )
    db.session.add(uf)
    db.session.flush()  # assign uf.id

    return uf



