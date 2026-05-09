from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func

from infra.db.database import get_db
from infra.db.models import AnalysisTaskModel, TransactionModel, UserModel
from infra.web.security import get_current_admin

router = APIRouter(prefix="/admin", tags=["admin"])


class UserStatRow(BaseModel):
    email: str
    requests: int
    spent_credits: int


@router.get("/stats", response_model=list[UserStatRow])
def list_user_stats(db=Depends(get_db), _admin=Depends(get_current_admin)):
    users = db.query(UserModel).filter(UserModel.role == "user").order_by(UserModel.email)
    rows = []
    for u in users:
        requests = (
            db.query(func.count(AnalysisTaskModel.id)).filter(AnalysisTaskModel.user_id == u.id).scalar() or 0
        )
        spent = (
            db.query(func.coalesce(func.sum(-TransactionModel.amount), 0))
            .filter(
                TransactionModel.user_id == u.id,
                TransactionModel.type == "analysis_charge",
            )
            .scalar()
            or 0
        )
        rows.append(UserStatRow(email=u.email, requests=int(requests), spent_credits=int(spent)))
    return rows
