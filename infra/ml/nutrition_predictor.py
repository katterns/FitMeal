from pathlib import Path

import joblib
import pandas as pd


class NutritionPredictor:
    def __init__(self, models_dir):
        self.models_dir = Path(models_dir)
        self.calorie_model = joblib.load(self.models_dir / "calorie_model.joblib")

    def predict(self, profile):
        features = self._profile_to_features(profile)

        raw = int(round(float(self.calorie_model.predict(features)[0])))
        return max(1200, min(raw, 4500))

    def _profile_to_features(self, profile):
        row = {
            "age": profile["age"],
            "sex": profile["sex"],
            "height_cm": profile["height_cm"],
            "weight_kg": profile["weight_kg"],
            "activity_level": profile["activity_level"],
            "goal": profile["goal"],
        }
        return pd.DataFrame([row], columns=["age", "sex", "height_cm", "weight_kg", "activity_level", "goal"])
