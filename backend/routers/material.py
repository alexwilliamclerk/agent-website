"""Learner evidence upload and parsing endpoints used by the review workspace."""

from __future__ import annotations

import re
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from models.material import UserMaterial
from models.user import User
from routers.auth import get_current_user

router = APIRouter()

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_FILE_BYTES = 15 * 1024 * 1024
TEXT_EXTENSIONS = {".txt", ".md", ".json", ".csv", ".py", ".js", ".ts", ".java", ".go", ".sql", ".yaml", ".yml"}
DOCUMENT_EXTENSIONS = {".pdf", ".docx"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
ALLOWED_EXTENSIONS = TEXT_EXTENSIONS | DOCUMENT_EXTENSIONS | IMAGE_EXTENSIONS


class MaterialResponse(BaseModel):
    id: str
    job_id: str | None = None
    assessment_id: str | None = None
    original_name: str
    content_type: str | None = None
    size_bytes: int
    status: str
    extracted_text: str | None = None
    source_url: str | None = None
    error_message: str | None = None
    created_at: str


class CreateTextMaterialRequest(BaseModel):
    content: str = Field(min_length=1, max_length=30_000)
    title: str = Field(default="补充说明", min_length=1, max_length=120)
    job_id: str | None = None


def _safe_name(name: str) -> str:
    cleaned = re.sub(r"[^\w.\-()\[\]\u4e00-\u9fff ]", "_", name or "material")
    return cleaned[:160] or "material"


def _parse_file(path: Path, extension: str) -> tuple[str, str, str | None]:
    """Return status, extracted text, error. Image OCR is deliberately not faked."""
    if extension in TEXT_EXTENSIONS:
        for encoding in ("utf-8", "utf-8-sig", "gb18030"):
            try:
                return "parsed", path.read_text(encoding=encoding), None
            except UnicodeDecodeError:
                continue
        return "failed", "", "文件编码无法识别"

    if extension == ".pdf":
        try:
            from pypdf import PdfReader

            text = "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
            return ("parsed", text, None) if text.strip() else ("needs_ocr", "", "PDF 未提取到文本，需要 OCR")
        except ImportError:
            return "uploaded", "", "服务器未安装 PDF 解析组件"
        except Exception as exc:
            return "failed", "", f"PDF 解析失败：{exc}"

    if extension == ".docx":
        try:
            from docx import Document

            document = Document(str(path))
            text = "\n".join(paragraph.text for paragraph in document.paragraphs)
            return "parsed", text, None
        except ImportError:
            return "uploaded", "", "服务器未安装 Word 解析组件"
        except Exception as exc:
            return "failed", "", f"Word 解析失败：{exc}"

    if extension in IMAGE_EXTENSIONS:
        return "needs_ocr", "", "图片已保存，等待 OCR 解析"
    return "failed", "", "不支持的文件类型"


def _serialize(material: UserMaterial) -> dict:
    return {
        "id": material.id,
        "job_id": material.job_id,
        "assessment_id": material.assessment_id,
        "original_name": material.original_name,
        "content_type": material.content_type,
        "size_bytes": material.size_bytes or 0,
        "status": material.status,
        "extracted_text": material.extracted_text,
        "source_url": material.source_url,
        "error_message": material.error_message,
        "created_at": material.created_at.isoformat(),
    }


@router.get("/list", response_model=list[MaterialResponse])
def list_materials(
    job_id: str | None = None,
    assessment_id: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(UserMaterial).filter(UserMaterial.user_id == current_user.id)
    if assessment_id:
        query = query.filter(UserMaterial.assessment_id == assessment_id)
    elif job_id:
        query = query.filter(UserMaterial.job_id == job_id)
    return [_serialize(item) for item in query.order_by(UserMaterial.created_at.desc()).all()]


@router.post("/upload", response_model=MaterialResponse, status_code=201)
def upload_material(
    file: UploadFile = File(...),
    job_id: str | None = Form(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    original_name = _safe_name(file.filename or "material")
    extension = Path(original_name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="仅支持 PDF、DOCX、TXT、代码文件和常见图片")

    storage_name = f"{uuid.uuid4().hex}{extension}"
    destination = UPLOAD_DIR / storage_name
    with destination.open("wb") as output:
        shutil.copyfileobj(file.file, output)
    size_bytes = destination.stat().st_size
    if size_bytes > MAX_FILE_BYTES:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=413, detail="单个文件不能超过 15MB")

    status, extracted_text, error_message = _parse_file(destination, extension)
    material = UserMaterial(
        user_id=current_user.id,
        job_id=job_id,
        original_name=original_name,
        storage_name=storage_name,
        content_type=file.content_type or "application/octet-stream",
        size_bytes=size_bytes,
        status=status,
        extracted_text=extracted_text[:50_000] if extracted_text else "",
        error_message=error_message,
    )
    db.add(material)
    db.commit()
    db.refresh(material)
    return _serialize(material)


@router.post("/text", response_model=MaterialResponse, status_code=201)
def create_text_material(
    request: CreateTextMaterialRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    material = UserMaterial(
        user_id=current_user.id,
        job_id=request.job_id,
        original_name=request.title.strip(),
        content_type="text/plain",
        size_bytes=len(request.content.encode("utf-8")),
        status="parsed",
        extracted_text=request.content.strip(),
    )
    db.add(material)
    db.commit()
    db.refresh(material)
    return _serialize(material)


@router.get("/{material_id}/download")
def download_material(
    material_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    material = db.query(UserMaterial).filter(
        UserMaterial.id == material_id,
        UserMaterial.user_id == current_user.id,
    ).first()
    if not material or not material.storage_name:
        raise HTTPException(status_code=404, detail="资料不存在或不提供下载")
    path = UPLOAD_DIR / material.storage_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="原始文件不存在")
    return FileResponse(path, filename=material.original_name, media_type=material.content_type)


@router.delete("/{material_id}")
def delete_material(
    material_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    material = db.query(UserMaterial).filter(
        UserMaterial.id == material_id,
        UserMaterial.user_id == current_user.id,
    ).first()
    if not material:
        raise HTTPException(status_code=404, detail="资料不存在")
    if material.storage_name:
        (UPLOAD_DIR / material.storage_name).unlink(missing_ok=True)
    db.delete(material)
    db.commit()
    return {"message": "已删除"}
