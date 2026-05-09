def nutrition_profile_from_saved(saved):
    return {
        "user_id": saved.user_id,
        "age": saved.age,
        "sex": saved.sex,
        "height_cm": saved.height_cm,
        "weight_kg": saved.weight_kg,
        "activity_level": saved.activity_level,
        "goal": saved.goal,
        "dietary_restrictions": saved.dietary_restrictions or [],
        "disliked_foods": saved.disliked_foods or [],
        "preferred_foods": saved.preferred_foods or [],
    }
