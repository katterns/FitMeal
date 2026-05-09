from pathlib import Path

import pandas as pd

from core.domain import ActivityLevel, BiologicalSex, NutritionGoal, NutritionProfile
from infra.ml.nutrition_predictor import NutritionPredictor
from infra.ml.train_models import build_preprocessor, calculate_calories, generate_synthetic_dataset


def test_calories_formula():
    kcal = calculate_calories(25, "female", 170, 65, "medium", "maintenance")
    assert 1900 <= kcal <= 2300


def test_preprocessor():
    prep = build_preprocessor()
    row = pd.DataFrame(
        [{"age": 30, "height_cm": 175, "weight_kg": 75, "sex": "male", "activity_level": "medium", "goal": "maintenance"}]
    )
    matrix = prep.fit_transform(row)
    assert matrix.shape[0] == 1


def test_synthetic_csv(tmp_path):
    path = tmp_path / "nutrition_profiles.csv"
    df = generate_synthetic_dataset(rows=30, output_path=path)
    assert len(df) == 30 and path.is_file()


def test_predictor():
    models_dir = Path(__file__).resolve().parents[1] / "models"
    predictor = NutritionPredictor(str(models_dir))
    profile = NutritionProfile(
        1,
        32,
        BiologicalSex.FEMALE,
        165,
        62,
        ActivityLevel.MEDIUM,
        NutritionGoal.MAINTENANCE,
        ["nuts"],
        [],
        ["огурцы"],
    )
    assert predictor.predict(profile) > 1000
