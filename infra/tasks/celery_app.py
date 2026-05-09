import os
from datetime import timedelta

from celery import Celery
from celery.signals import worker_ready
from sqlalchemy import and_, or_, update

from config.settings import get_settings
from core.domain import nutrition_profile_from_saved
from infra.db.database import SessionLocal
from infra.db.models import (
    AnalysisResultModel,
    AnalysisTaskModel,
    NutritionProfileModel,
    TransactionModel,
    UserModel,
    UserPromoActivationModel,
    utcnow,
)
from infra.ml.meal_plan_generator import generate_meal_plan
from infra.ml.nutrition_predictor import NutritionPredictor
from infra.prometheus_metrics import ANALYSIS_FINISHED

settings = get_settings()
celery_app = Celery("fitmeal", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_always_eager=settings.celery_task_always_eager,
    task_eager_propagates=True,
)


@worker_ready.connect
def _expose_prometheus_on_worker(**_kwargs):
    from prometheus_client import start_http_server

    port = int(os.environ.get("PROMETHEUS_METRICS_PORT", "9464"))
    try:
        start_http_server(port)
    except OSError:
        pass


@celery_app.task(
    name="process_analysis",
    soft_time_limit=settings.celery_analysis_soft_time_limit,
    time_limit=settings.celery_analysis_time_limit,
)
def process_analysis(analysis_id):
    db = SessionLocal()
    try:
        now = utcnow()
        stale_cutoff = now - timedelta(seconds=settings.analysis_stale_reclaim_seconds)
        claimed = db.execute(
            update(AnalysisTaskModel)
            .where(
                AnalysisTaskModel.id == analysis_id,
                or_(
                    AnalysisTaskModel.status == "pending",
                    and_(
                        AnalysisTaskModel.status == "processing",
                        AnalysisTaskModel.updated_at < stale_cutoff,
                    ),
                ),
            )
            .values(status="processing", updated_at=now)
        )
        db.commit()

        task = db.get(AnalysisTaskModel, analysis_id)
        if task is None:
            return {"analysis_id": analysis_id, "status": "not_found"}

        if claimed.rowcount == 0:
            if task.status == "completed":
                return {"analysis_id": analysis_id, "status": "already_completed"}
            if task.status == "failed":
                return {"analysis_id": analysis_id, "status": "already_failed"}
            return {"analysis_id": analysis_id, "status": "skipped_in_progress"}

        user = db.get(UserModel, task.user_id)
        saved = db.query(NutritionProfileModel).filter(NutritionProfileModel.analysis_id == analysis_id).first()
        if user is None or saved is None:
            raise ValueError("Нет пользователя или анкеты для этой задачи")
        if user.balance < task.cost:
            raise ValueError("Недостаточно кредитов")

        anketa = nutrition_profile_from_saved(saved)
        kcal = NutritionPredictor(settings.models_dir).predict(anketa)
        meal_plan_text = None
        if task.tariff == "pro":
            meal_plan_text = generate_meal_plan(
                anketa,
                kcal,
                days=3,
                api_key=settings.mistral_api_key,
                base_url=settings.mistral_base_url,
                model=settings.mistral_model,
            )

        db.add(
            AnalysisResultModel(
                analysis_id=task.id,
                user_id=user.id,
                predicted_calories=kcal,
                meal_plan_text=meal_plan_text,
                explanation=None,
            )
        )
        user.balance -= task.cost
        db.add(
            TransactionModel(
                user_id=user.id,
                amount=-task.cost,
                type="analysis_charge",
                description="Анализ питания (базовый)"
                if task.tariff == "basic"
                else "Анализ питания с меню (Pro)",
                analysis_id=task.id,
            )
        )
        task.status, task.error_message = "completed", None
        task.updated_at = utcnow()
        if task.promo_activation_id:
            promo_activation = db.get(UserPromoActivationModel, task.promo_activation_id)
            if promo_activation:
                promo_activation.uses_consumed += 1
        db.commit()
        ANALYSIS_FINISHED.labels(tier=task.tariff, status="completed").inc()
        return {"analysis_id": analysis_id, "status": "completed"}
    except Exception as exc:
        db.rollback()
        failed_task = db.get(AnalysisTaskModel, analysis_id)
        if failed_task and failed_task.status == "processing":
            failed_task.status = "failed"
            failed_task.error_message = str(exc)
            failed_task.updated_at = utcnow()
            db.commit()
            ANALYSIS_FINISHED.labels(tier=failed_task.tariff, status="failed").inc()
        return {"analysis_id": analysis_id, "status": "failed"}
    finally:
        db.close()
