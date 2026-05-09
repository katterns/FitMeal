from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from infra.db.database import get_db
from infra.db.models import PromoCodeModel, UserPromoActivationModel
from infra.web.security import get_current_user

router = APIRouter(prefix="/promo", tags=["promo"])


def as_utc(dt):
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def discounted_price_for_user(db, user_id, list_price):
    now = datetime.now(timezone.utc)
    for activation in (
        db.query(UserPromoActivationModel)
        .join(PromoCodeModel)
        .filter(
            UserPromoActivationModel.user_id == user_id,
            UserPromoActivationModel.uses_consumed < PromoCodeModel.max_uses_per_user,
            PromoCodeModel.is_active.is_(True),
        )
        .order_by(PromoCodeModel.discount_percent.desc(), UserPromoActivationModel.id)
    ):
        promo = activation.promo_code
        valid_until = as_utc(promo.valid_until)
        if valid_until and valid_until < now:
            continue
        price = int(round(list_price * (100 - promo.discount_percent) / 100))
        return max(1, price), activation.id
    return list_price, None


class ApplyPromoBody(BaseModel):
    code: str


class PromoMineRow(BaseModel):
    code: str
    discount_percent: int
    uses_left: int
    valid_until: datetime | None


@router.post("/apply")
def apply_promo(body: ApplyPromoBody, current_user=Depends(get_current_user), db=Depends(get_db)):
    code = body.code.strip().lower()
    promo = db.query(PromoCodeModel).filter(PromoCodeModel.code == code).first()
    if promo is None or not promo.is_active:
        raise HTTPException(404, "Промокод не найден")
    valid_until = as_utc(promo.valid_until)
    if valid_until and valid_until < datetime.now(timezone.utc):
        raise HTTPException(400, "Срок действия промокода истёк")

    activation = db.query(UserPromoActivationModel).filter_by(user_id=current_user.id, promo_code_id=promo.id).first()
    if activation:
        if activation.uses_consumed >= promo.max_uses_per_user:
            raise HTTPException(400, "Промокод уже использован полностью")
        return {"ok": True, "message": "Промокод уже активирован"}

    db.add(UserPromoActivationModel(user_id=current_user.id, promo_code_id=promo.id))
    db.commit()
    return {"ok": True, "message": "Промокод активирован"}


@router.get("/mine", response_model=list[PromoMineRow])
def my_promos(current_user=Depends(get_current_user), db=Depends(get_db)):
    now = datetime.now(timezone.utc)
    out = []
    for activation, promo in (
        db.query(UserPromoActivationModel, PromoCodeModel)
        .join(PromoCodeModel, UserPromoActivationModel.promo_code_id == PromoCodeModel.id)
        .filter(UserPromoActivationModel.user_id == current_user.id)
        .order_by(UserPromoActivationModel.id)
        .all()
    ):
        if not promo.is_active:
            continue
        valid_until = as_utc(promo.valid_until)
        if valid_until and valid_until < now:
            continue
        left = promo.max_uses_per_user - activation.uses_consumed
        if left <= 0:
            continue
        out.append(
            PromoMineRow(
                code=promo.code,
                discount_percent=promo.discount_percent,
                uses_left=left,
                valid_until=promo.valid_until,
            )
        )
    return out
