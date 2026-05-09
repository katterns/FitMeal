from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import joinedload

from config.settings import get_settings
from infra.db.database import get_db
from infra.db.models import AnalysisTaskModel, NutritionProfileModel
from infra.prometheus_metrics import ANALYSIS_CREATED, ANALYSIS_REJECTED
from infra.tasks.celery_app import process_analysis
from infra.web.controllers.promo_controller import discounted_price_for_user
from infra.web.security import get_current_user


router = APIRouter(prefix="/analysis", tags=["analysis"])
settings = get_settings()


class NutritionProfileRequest(BaseModel):
    age: int = Field(ge=14, le=90)
    sex: str = Field(pattern="^(female|male)$")
    height_cm: float = Field(ge=120, le=230)
    weight_kg: float = Field(ge=35, le=250)
    activity_level: str = Field(pattern="^(low|medium|high)$")
    goal: str = Field(pattern="^(weight_loss|maintenance|muscle_gain)$")
    dietary_restrictions: list = Field(default_factory=list)
    disliked_foods: list = Field(default_factory=list)
    preferred_foods: list = Field(default_factory=list)


class CreateAnalysisRequest(BaseModel):
    tariff: str = Field(pattern="^(basic|pro)$")
    profile: NutritionProfileRequest


class AnalysisResponse(BaseModel):
    id: int
    tariff: str
    status: str
    cost: int
    error_message: str | None = None
    created_at: datetime
    predicted_calories: int | None = None
    meal_plan_text: str | None = None
    meal_plan_explanation: str | None = None
    your_number: int | None = Field(
        default=None,
        description="Порядковый номер анализа у пользователя по времени создания (1 = самый первый)",
    )


class LastProfileResponse(NutritionProfileRequest):
    tariff: str = Field(default="basic", pattern="^(basic|pro)$")


def analysis_serial_numbers_by_user(db, user_id):
    rows = (
        db.query(AnalysisTaskModel.id)
        .filter(AnalysisTaskModel.user_id == user_id)
        .order_by(AnalysisTaskModel.created_at.asc(), AnalysisTaskModel.id.asc())
        .all()
    )
    return {row[0]: i + 1 for i, row in enumerate(rows)}


def analysis_response(task, serial_by_id=None):
    result = task.result
    your_number = serial_by_id.get(task.id) if serial_by_id is not None else None
    return AnalysisResponse(
        id=task.id,
        tariff=task.tariff,
        status=task.status,
        cost=task.cost,
        error_message=task.error_message,
        created_at=task.created_at,
        predicted_calories=result.predicted_calories if result else None,
        meal_plan_text=result.meal_plan_text if result else None,
        meal_plan_explanation=(result.explanation or None) if result and result.meal_plan_text else None,
        your_number=your_number,
    )


@router.post("", response_model=AnalysisResponse)
def create_analysis(
    request: CreateAnalysisRequest,
    current_user=Depends(get_current_user),
    db=Depends(get_db),
):
    price = settings.basic_tariff_price if request.tariff == "basic" else settings.pro_tariff_price
    final_price, promo_activation_id = discounted_price_for_user(db, current_user.id, price)
    if current_user.balance < final_price:
        ANALYSIS_REJECTED.labels(tier=request.tariff, reason="insufficient_credits").inc()
        raise HTTPException(status_code=400, detail="Недостаточно кредитов")

    task = AnalysisTaskModel(
        user_id=current_user.id,
        tariff=request.tariff,
        status="pending",
        cost=final_price,
        promo_activation_id=promo_activation_id,
    )
    db.add(task)
    db.flush()

    profile_model = NutritionProfileModel(
        analysis_id=task.id,
        user_id=current_user.id,
        age=request.profile.age,
        sex=request.profile.sex,
        height_cm=request.profile.height_cm,
        weight_kg=request.profile.weight_kg,
        activity_level=request.profile.activity_level,
        goal=request.profile.goal,
        dietary_restrictions=request.profile.dietary_restrictions,
        disliked_foods=request.profile.disliked_foods,
        preferred_foods=request.profile.preferred_foods,
    )
    db.add(profile_model)
    db.commit()
    db.refresh(task)

    process_analysis.delay(task.id)
    ANALYSIS_CREATED.labels(tier=request.tariff).inc()
    db.refresh(task)
    serial = analysis_serial_numbers_by_user(db, current_user.id)
    return analysis_response(task, serial)


@router.get("/history", response_model=list[AnalysisResponse])
def list_history(
    current_user=Depends(get_current_user),
    db=Depends(get_db),
):
    tasks = (
        db.query(AnalysisTaskModel)
        .options(joinedload(AnalysisTaskModel.result))
        .filter(AnalysisTaskModel.user_id == current_user.id)
        .order_by(AnalysisTaskModel.created_at.desc())
        .all()
    )
    serial = analysis_serial_numbers_by_user(db, current_user.id)
    return [analysis_response(task, serial) for task in tasks]


@router.get("/profile/last", response_model=LastProfileResponse | None)
def get_last_profile(
    current_user=Depends(get_current_user),
    db=Depends(get_db),
):
    profile = (
        db.query(NutritionProfileModel)
        .filter(NutritionProfileModel.user_id == current_user.id)
        .order_by(NutritionProfileModel.id.desc())
        .first()
    )
    if profile is None:
        return None

    tariff = "basic"
    if profile.analysis and profile.analysis.tariff == "pro":
        tariff = "pro"

    return LastProfileResponse(
        tariff=tariff,
        age=profile.age,
        sex=profile.sex,
        height_cm=profile.height_cm,
        weight_kg=profile.weight_kg,
        activity_level=profile.activity_level,
        goal=profile.goal,
        dietary_restrictions=profile.dietary_restrictions,
        disliked_foods=profile.disliked_foods,
        preferred_foods=profile.preferred_foods,
    )


@router.get("/{analysis_id}", response_model=AnalysisResponse)
def get_analysis(
    analysis_id: int,
    current_user=Depends(get_current_user),
    db=Depends(get_db),
):
    task = (
        db.query(AnalysisTaskModel)
        .options(joinedload(AnalysisTaskModel.result))
        .filter(AnalysisTaskModel.id == analysis_id, AnalysisTaskModel.user_id == current_user.id)
        .first()
    )
    if task is None:
        raise HTTPException(status_code=404, detail="Анализ не найден")
    serial = analysis_serial_numbers_by_user(db, current_user.id)
    return analysis_response(task, serial)
