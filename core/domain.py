from enum import Enum


class TariffCode(str, Enum):
    BASIC = "basic"
    PRO = "pro"


class ActivityLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class BiologicalSex(str, Enum):
    FEMALE = "female"
    MALE = "male"


class NutritionGoal(str, Enum):
    WEIGHT_LOSS = "weight_loss"
    MAINTENANCE = "maintenance"
    MUSCLE_GAIN = "muscle_gain"


class NutritionProfile:
    def __init__(
        self,
        user_id,
        age,
        sex,
        height_cm,
        weight_kg,
        activity_level,
        goal,
        dietary_restrictions,
        disliked_foods,
        preferred_foods,
    ):
        self.user_id = user_id
        self.age = age
        self.sex = sex
        self.height_cm = height_cm
        self.weight_kg = weight_kg
        self.activity_level = activity_level
        self.goal = goal
        self.dietary_restrictions = dietary_restrictions
        self.disliked_foods = disliked_foods
        self.preferred_foods = preferred_foods


class MealPlan:
    def __init__(self, days, menu_text, explanation):
        self.days = days
        self.menu_text = menu_text
        self.explanation = explanation
