import asyncio

from celery import Celery

from config.settings import get_settings
from core.domain import ActivityLevel, BiologicalSex, NutritionGoal, NutritionProfile, TariffCode
from infra.db.database import SessionLocal
from infra.db.models import AnalysisResultModel, AnalysisTaskModel, NutritionProfileModel, TransactionModel, UserModel, UserPromoActivationModel
from infra.ml.meal_plan_generator import MealPlanGenerator
from infra.ml.nutrition_predictor import NutritionPredictor

settings = get_settings()
celery_app = Celery("fitmeal", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_always_eager=settings.celery_task_always_eager,
    task_eager_propagates=True,
)


@celery_app.task(name="process_analysis")
def process_analysis(analysis_id):
    db = SessionLocal()
    try:
        task = db.get(AnalysisTaskModel, analysis_id)
        if task is None:
            return {"analysis_id": analysis_id, "status": "not_found"}
        if task.status == "completed":
            return {"analysis_id": analysis_id, "status": "already_completed"}
        task.status = "processing"
        db.commit()

        user = db.get(UserModel, task.user_id)
        saved = db.query(NutritionProfileModel).filter(NutritionProfileModel.analysis_id == analysis_id).first()
        if user is None or saved is None:
            raise ValueError("Нет пользователя или анкеты для этой задачи")
        if user.balance < task.cost:
            raise ValueError("Недостаточно кредитов")

        anketa = NutritionProfile(
            saved.user_id,
            saved.age,
            BiologicalSex(saved.sex),
            saved.height_cm,
            saved.weight_kg,
            ActivityLevel(saved.activity_level),
            NutritionGoal(saved.goal),
            saved.dietary_restrictions,
            saved.disliked_foods,
            saved.preferred_foods,
        )
        kcal = NutritionPredictor(settings.models_dir).predict(anketa)
        meal_plan_text = explanation = None
        if task.tariff == TariffCode.PRO.value:
            gen = MealPlanGenerator(settings.mistral_api_key, settings.mistral_base_url, settings.mistral_model)
            mp = asyncio.run(gen.generate(anketa, kcal, days=3))
            meal_plan_text, explanation = mp.menu_text, mp.explanation

        db.add(
            AnalysisResultModel(
                analysis_id=task.id,
                user_id=user.id,
                predicted_calories=kcal,
                meal_plan_text=meal_plan_text,
                explanation=explanation,
            )
        )
        user.balance -= task.cost
        db.add(
            TransactionModel(
                user_id=user.id,
                amount=-task.cost,
                type="analysis_charge",
                description="Анализ питания (базовый)"
                if task.tariff == TariffCode.BASIC.value
                else "Анализ питания с меню (Pro)",
                analysis_id=task.id,
            )
        )
        task.status, task.error_message = "completed", None
        if task.promo_activation_id and (pa := db.get(UserPromoActivationModel, task.promo_activation_id)):
            pa.uses_consumed += 1
        db.commit()
        return {"analysis_id": analysis_id, "status": "completed"}
    except Exception as exc:
        db.rollback()
        if t := db.get(AnalysisTaskModel, analysis_id):
            t.status, t.error_message = "failed", str(exc)
            db.commit()
        return {"analysis_id": analysis_id, "status": "failed"}
    finally:
        db.close()
