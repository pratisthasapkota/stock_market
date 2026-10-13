from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_role
from ..models import Article, ArticleTag, Company, CorrectionLog, User
from ..schemas import ArticleOut, RecategorizeIn

router = APIRouter()


@router.get("", response_model=list[ArticleOut])
def list_news(
    company_id: int | None = None,
    source: str | None = None,
    q: str | None = None,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    query = db.query(Article)
    if company_id:
        query = query.join(ArticleTag, ArticleTag.article_id == Article.id).filter(
            ArticleTag.company_id == company_id
        )
    if source:
        query = query.filter(Article.source == source)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Article.title.ilike(like), Article.body.ilike(like)))
    return (
        query.order_by(Article.published_at.desc())
        .limit(limit)
        .all()
    )


@router.post("/{article_id}/recategorize", response_model=ArticleOut)
def recategorize(
    article_id: int,
    payload: RecategorizeIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("analyst")),
):
    """Analyst correction. Adds or removes the company tag and records the
    decision in correction_log, ready to be consumed as retraining data."""

    article = db.get(Article, article_id)
    if not article:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "article not found")
    company = db.get(Company, payload.company_id)
    if not company:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "company not found")

    tag = (
        db.query(ArticleTag)
        .filter_by(article_id=article_id, company_id=payload.company_id)
        .first()
    )
    if payload.action == "add":
        if not tag:
            db.add(
                ArticleTag(
                    article_id=article_id,
                    company_id=payload.company_id,
                    confidence=1.0,
                    method="manual",
                    corrected=True,
                    corrected_by_id=user.id,
                )
            )
        log_row = CorrectionLog(
            article_id=article_id,
            to_company_id=payload.company_id,
            action="add",
            user_id=user.id,
        )
    elif payload.action == "remove":
        if tag:
            db.delete(tag)
        log_row = CorrectionLog(
            article_id=article_id,
            from_company_id=payload.company_id,
            action="remove",
            user_id=user.id,
        )
    else:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "action must be add|remove")

    db.add(log_row)
    db.commit()
    db.refresh(article)
    return article