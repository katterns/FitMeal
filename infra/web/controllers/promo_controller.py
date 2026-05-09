from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

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
    for act in (
        db.query(UserPromoActivationModel)
        .join(PromoCodeModel)
        .filter(
            UserPromoActivationModel.user_id == user_id,
            UserPromoActivationModel.uses_consumed < PromoCodeModel.max_uses_per_user,
            PromoCodeModel.is_active.is_(True),
        )
        .order_by(PromoCodeModel.discount_percent.desc(), UserPromoActivationModel.id)
    ):
        vu = as_utc(act.promo_code.valid_until)
        if vu and vu < now:
            continue
        p = act.promo_code
        return max(1, int(round(list_price * (100 - p.discount_percent) / 100))), act.id
    return list_price, None


class ApplyPromoBody(BaseModel):
    code: str


class PromoMineRow(BaseModel):
    model_config = ConfigDict(from_attributes=False)

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
    vu = as_utc(promo.valid_until)
    if vu and vu < datetime.now(timezone.utc):
        raise HTTPException(400, "Срок действия промокода истёк")
    ex = db.query(UserPromoActivationModel).filter_by(user_id=current_user.id, promo_code_id=promo.id).first()
    if ex:
        if ex.uses_consumed >= promo.max_uses_per_user:
            raise HTTPException(400, "Промокод уже использован полностью")
        return {"ok": True, "message": "Промокод уже активирован"}
    db.add(UserPromoActivationModel(user_id=current_user.id, promo_code_id=promo.id))
    db.commit()
    return {"ok": True, "message": "Промокод активирован"}


@router.get("/mine", response_model=list[PromoMineRow])
def my_promos(current_user=Depends(get_current_user), db=Depends(get_db)):
    now = datetime.now(timezone.utc)
    out = []
    for act, p in (
        db.query(UserPromoActivationModel, PromoCodeModel)
        .join(PromoCodeModel, UserPromoActivationModel.promo_code_id == PromoCodeModel.id)
        .filter(UserPromoActivationModel.user_id == current_user.id)
        .order_by(UserPromoActivationModel.id)
        .all()
    ):
        if not p.is_active:
            continue
        if (t := as_utc(p.valid_until)) and t < now:
            continue
        left = p.max_uses_per_user - act.uses_consumed
        if left <= 0:
            continue
        out.append(
            PromoMineRow(
                code=p.code, discount_percent=p.discount_percent, uses_left=left, valid_until=p.valid_until
            )
        )
    return out
