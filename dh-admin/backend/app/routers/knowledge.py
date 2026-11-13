from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import KnowledgeBase, KnowledgeDocument, Persona
from app.schemas import KnowledgeBaseIn
from app.serialize import document_dict, knowledge_base_dict
from app.services.personas import get_or_404
from app.services.retrieval import extract_text
from app.services.storage import data_root, delete_storage, save_upload

router = APIRouter(prefix="/knowledge-bases", tags=["knowledge"], dependencies=[Depends(get_current_user)])

DOC_EXT = {".txt", ".md", ".pdf"}


def _with_count(db: Session, row: KnowledgeBase) -> dict:
    count = db.query(KnowledgeDocument).filter(KnowledgeDocument.knowledge_base_id == row.id).count()
    return knowledge_base_dict(row, count)


@router.get("")
def list_bases(db: Session = Depends(get_db)):
    rows = db.query(KnowledgeBase).order_by(KnowledgeBase.id.desc()).all()
    return [_with_count(db, row) for row in rows]


@router.post("")
def create_base(body: KnowledgeBaseIn, db: Session = Depends(get_db)):
    row = KnowledgeBase(name=body.name.strip(), description=body.description.strip())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _with_count(db, row)


@router.put("/{base_id}")
def update_base(base_id: int, body: KnowledgeBaseIn, db: Session = Depends(get_db)):
    row = get_or_404(db, KnowledgeBase, base_id, "知识库")
    row.name = body.name.strip()
    row.description = body.description.strip()
    db.commit()
    db.refresh(row)
    return _with_count(db, row)


@router.delete("/{base_id}")
def delete_base(base_id: int, db: Session = Depends(get_db)):
    row = get_or_404(db, KnowledgeBase, base_id, "知识库")
    db.query(Persona).filter(Persona.knowledge_base_id == row.id).update(
        {Persona.knowledge_base_id: None}, synchronize_session=False
    )
    docs = db.query(KnowledgeDocument).filter(KnowledgeDocument.knowledge_base_id == row.id).all()
    for doc in docs:
        delete_storage(doc.storage_path)
        db.delete(doc)
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.get("/{base_id}/documents")
def list_documents(base_id: int, db: Session = Depends(get_db)):
    get_or_404(db, KnowledgeBase, base_id, "知识库")
    rows = (
        db.query(KnowledgeDocument)
        .filter(KnowledgeDocument.knowledge_base_id == base_id)
        .order_by(KnowledgeDocument.id.desc())
        .all()
    )
    return [document_dict(row) for row in rows]


@router.post("/{base_id}/documents")
def upload_document(
    base_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    get_or_404(db, KnowledgeBase, base_id, "知识库")
    relative, original, size = save_upload(file, f"knowledge/{base_id}", DOC_EXT)
    path = data_root() / relative
    text = ""
    try:
        text = extract_text(Path(path), Path(original).suffix)
    except Exception:
        text = ""
    row = KnowledgeDocument(
        knowledge_base_id=base_id,
        original_name=original,
        storage_path=relative,
        content_type=file.content_type or "",
        size_bytes=size,
        text_content=text,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return document_dict(row)


@router.delete("/{base_id}/documents/{document_id}")
def delete_document(base_id: int, document_id: int, db: Session = Depends(get_db)):
    row = db.get(KnowledgeDocument, document_id)
    if row is None or row.knowledge_base_id != base_id:
        raise HTTPException(status_code=404, detail="文档不存在")
    delete_storage(row.storage_path)
    db.delete(row)
    db.commit()
    return {"ok": True}
