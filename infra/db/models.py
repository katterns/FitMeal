from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, mapped_column, relationship


def utcnow():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class UserModel(Base):
    __tablename__ = "users"

    id = mapped_column(Integer, primary_key=True, index=True)
    email = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password = mapped_column(String(255), nullable=False)
    role = mapped_column(String(50), default="user", nullable=False)
    balance = mapped_column(Integer, default=100, nullable=False)
    is_active = mapped_column(Boolean, default=True, nullable=False)
    created_at = mapped_column(DateTime(timezone=True), default=utcnow)

    transactions = relationship("TransactionModel", back_populates="user")
    analyses = relationship("AnalysisTaskModel", back_populates="user")
    promo_activations = relationship("UserPromoActivationModel", back_populates="user")


class PromoCodeModel(Base):
    __tablename__ = "promo_codes"

    id = mapped_column(Integer, primary_key=True, index=True)
    code = mapped_column(String(64), unique=True, nullable=False, index=True)
    discount_percent = mapped_column(Integer, nullable=False)
    max_uses_per_user = mapped_column(Integer, nullable=False)
    valid_until = mapped_column(DateTime(timezone=True), nullable=True)
    is_active = mapped_column(Boolean, default=True, nullable=False)

    activations = relationship("UserPromoActivationModel", back_populates="promo_code")


class UserPromoActivationModel(Base):
    __tablename__ = "user_promo_activations"

    id = mapped_column(Integer, primary_key=True, index=True)
    user_id = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    promo_code_id = mapped_column(ForeignKey("promo_codes.id"), index=True, nullable=False)
    uses_consumed = mapped_column(Integer, default=0, nullable=False)
    created_at = mapped_column(DateTime(timezone=True), default=utcnow)

    user = relationship("UserModel", back_populates="promo_activations")
    promo_code = relationship("PromoCodeModel", back_populates="activations")

    __table_args__ = (UniqueConstraint("user_id", "promo_code_id", name="uq_user_promo"),)


class TransactionModel(Base):
    __tablename__ = "transactions"

    id = mapped_column(Integer, primary_key=True, index=True)
    user_id = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    amount = mapped_column(Integer, nullable=False)
    type = mapped_column(String(50), nullable=False)
    description = mapped_column(String(255), nullable=False)
    analysis_id = mapped_column(Integer, nullable=True)
    created_at = mapped_column(DateTime(timezone=True), default=utcnow)

    user = relationship("UserModel", back_populates="transactions")


class NutritionProfileModel(Base):
    __tablename__ = "nutrition_profiles"

    id = mapped_column(Integer, primary_key=True, index=True)
    analysis_id = mapped_column(ForeignKey("analysis_tasks.id"), index=True)
    user_id = mapped_column(ForeignKey("users.id"), index=True)
    age = mapped_column(Integer)
    sex = mapped_column(String(20))
    height_cm = mapped_column(Float)
    weight_kg = mapped_column(Float)
    activity_level = mapped_column(String(20))
    goal = mapped_column(String(30))
    dietary_restrictions = mapped_column(JSON, default=list)
    disliked_foods = mapped_column(JSON, default=list)
    preferred_foods = mapped_column(JSON, default=list)

    analysis = relationship("AnalysisTaskModel", back_populates="profile")


class AnalysisTaskModel(Base):
    __tablename__ = "analysis_tasks"

    id = mapped_column(Integer, primary_key=True, index=True)
    user_id = mapped_column(ForeignKey("users.id"), index=True)
    tariff = mapped_column(String(50), nullable=False)
    status = mapped_column(String(50), default="pending", nullable=False)
    cost = mapped_column(Integer, nullable=False)
    promo_activation_id = mapped_column(Integer, ForeignKey("user_promo_activations.id"), nullable=True)
    error_message = mapped_column(Text, nullable=True)
    created_at = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at = mapped_column(DateTime(timezone=True), default=utcnow)

    user = relationship("UserModel", back_populates="analyses")
    profile = relationship("NutritionProfileModel", back_populates="analysis", uselist=False)
    result = relationship("AnalysisResultModel", back_populates="analysis", uselist=False)


class AnalysisResultModel(Base):
    __tablename__ = "analysis_results"

    id = mapped_column(Integer, primary_key=True, index=True)
    analysis_id = mapped_column(ForeignKey("analysis_tasks.id"), index=True)
    user_id = mapped_column(ForeignKey("users.id"), index=True)
    predicted_calories = mapped_column(Integer)
    meal_plan_text = mapped_column(Text, nullable=True)
    explanation = mapped_column(Text, nullable=True)
    created_at = mapped_column(DateTime(timezone=True), default=utcnow)

    analysis = relationship("AnalysisTaskModel", back_populates="result")
