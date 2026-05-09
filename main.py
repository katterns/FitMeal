from pathlib import Path

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from sqlalchemy import inspect, text

from config.settings import get_settings
from infra.db.database import SessionLocal, engine
from infra.db.models import Base, PromoCodeModel, UserModel
from infra.ml.train_models import generate_synthetic_dataset, train_models
from infra.web.controllers.admin_controller import router as admin_router
from infra.web.controllers.analysis_controller import router as analysis_router
from infra.web.controllers.billing_controller import router as billing_router
from infra.web.controllers.promo_controller import router as promo_router
from infra.web.controllers.user_controller import auth_router, user_router
from infra.web.security import hash_password


settings = get_settings()


def create_tables():
    Base.metadata.create_all(bind=engine)


def ensure_schema():
    # create_all не дописывает колонки в уже существующие таблицы (старый том Postgres и т.п.).
    insp = inspect(engine)
    if not insp.has_table("analysis_tasks"):
        return
    cols = {c["name"] for c in insp.get_columns("analysis_tasks")}
    if "promo_activation_id" in cols:
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE analysis_tasks ADD COLUMN promo_activation_id INTEGER"))


def seed_promo_codes():
    with SessionLocal() as db:
        for code, pct, n in (("sale20three", 20, 3), ("sale50", 50, 1)):
            if db.query(PromoCodeModel).filter(PromoCodeModel.code == code).first() is None:
                db.add(PromoCodeModel(code=code, discount_percent=pct, max_uses_per_user=n, is_active=True))
        db.commit()


def seed_admin_user():
    with SessionLocal() as db:
        if db.query(UserModel).filter(UserModel.email == "admin@fitmeal.ai").first():
            return
        db.add(
            UserModel(
                email="admin@fitmeal.ai",
                hashed_password=hash_password("admin_fitmeal"),
                role="admin",
            )
        )
        db.commit()


def ensure_ml_models():
    root = Path(settings.models_dir)
    if (root / "calorie_model.joblib").exists():
        return
    train_models(generate_synthetic_dataset(), root)


def create_app():
    ensure_ml_models()
    create_tables()
    ensure_schema()
    seed_promo_codes()
    seed_admin_user()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="ML-сервис для анализа пищевого профиля",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/")
    def root():
        return {"name": settings.app_name, "docs": "/docs"}

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/metrics")
    def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(user_router, prefix="/api/v1")
    app.include_router(billing_router, prefix="/api/v1")
    app.include_router(promo_router, prefix="/api/v1")
    app.include_router(analysis_router, prefix="/api/v1")
    app.include_router(admin_router, prefix="/api/v1")

    return app


app = create_app()
