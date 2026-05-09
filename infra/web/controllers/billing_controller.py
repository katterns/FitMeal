from datetime import datetime

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel, ConfigDict

from infra.db.database import get_db
from infra.db.models import TransactionModel
from infra.web.security import get_current_user


router = APIRouter(prefix="/billing", tags=["billing"])


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    amount: int
    type: str
    description: str
    analysis_id: int | None = None
    created_at: datetime


@router.post("/topup", response_model=TransactionResponse)
def top_up(
    amount: int = Body(..., gt=0, le=10_000, embed=True),
    current_user=Depends(get_current_user),
    db=Depends(get_db),
):
    current_user.balance += amount
    transaction = TransactionModel(
        user_id=current_user.id,
        amount=amount,
        type="topup",
        description="Пополнение баланса",
    )
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return transaction


@router.get("/transactions", response_model=list[TransactionResponse])
def list_transactions(
    current_user=Depends(get_current_user),
    db=Depends(get_db),
):
    return db.query(TransactionModel).filter(TransactionModel.user_id == current_user.id).order_by(
        TransactionModel.created_at.desc()
    ).all()
