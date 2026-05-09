import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = ROOT / "data" / "nutrition_profiles.csv"
MODELS_DIR = ROOT / "models"


def calculate_calories(age, sex, height_cm, weight_kg, activity_level, goal):
    if sex == "male":
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + 5
    else:
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age - 161

    act = {"low": 1.2, "medium": 1.55, "high": 1.725}[activity_level]
    gf = {"weight_loss": 0.85, "maintenance": 1.0, "muscle_gain": 1.10}[goal]
    return int(round(bmr * act * gf))


def generate_synthetic_dataset(rows=1500, output_path=DATA_PATH):
    rng = np.random.default_rng(42)
    rows_out = []

    for _ in range(rows):
        age = int(rng.integers(18, 65))
        sex = str(rng.choice(["female", "male"]))
        h = float(np.clip(rng.normal(170 if sex == "female" else 178, 8), 145, 205))
        w = float(np.clip(rng.normal(67 if sex == "female" else 80, 14), 42, 140))
        h, w = round(h, 1), round(w, 1)

        act = str(rng.choice(["low", "medium", "high"], p=[0.45, 0.4, 0.15]))
        goal = str(rng.choice(["weight_loss", "maintenance", "muscle_gain"], p=[0.4, 0.4, 0.2]))

        kcal = calculate_calories(age, sex, h, w, act, goal)
        kcal = int(kcal + rng.normal(0, 80))

        rows_out.append(
            {
                "age": age,
                "sex": sex,
                "height_cm": h,
                "weight_kg": w,
                "activity_level": act,
                "goal": goal,
                "target_calories": kcal,
            }
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows_out)
    df.to_csv(output_path, index=False)
    return df


def build_preprocessor():
    return ColumnTransformer(
        [
            ("num", StandardScaler(), ["age", "height_cm", "weight_kg"]),
            ("cat", OneHotEncoder(handle_unknown="ignore"), ["sex", "activity_level", "goal"]),
        ]
    )


def train_models(dataset, models_dir=MODELS_DIR):
    cols = ["age", "sex", "height_cm", "weight_kg", "activity_level", "goal"]
    X = dataset[cols]
    y = dataset["target_calories"]

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    pipe = Pipeline([("prep", build_preprocessor()), ("rf", RandomForestRegressor(n_estimators=100, random_state=42))])
    pipe.fit(X_train, y_train)
    pred = pipe.predict(X_test)

    metrics = {"calorie_mae": round(float(mean_absolute_error(y_test, pred)), 2), "calorie_r2": round(float(r2_score(y_test, pred)), 3)}

    models_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipe, models_dir / "calorie_model.joblib")

    (models_dir / "model_metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")

    return metrics


def main():
    df = generate_synthetic_dataset()
    print(json.dumps(train_models(df), ensure_ascii=False, indent=2))
    print("csv:", DATA_PATH)
    print("models:", MODELS_DIR)


if __name__ == "__main__":
    main()
