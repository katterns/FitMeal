import httpx

_MENU_FAIL = "Не удалось подготовить меню. Пожалуйста, повторите запрос позже."


def _csv(items):
    if not items:
        return "нет"
    parts = [str(x).strip() for x in items if x is not None and str(x).strip()]
    return ", ".join(parts) if parts else "нет"


def generate_meal_plan(profile, predicted_calories, days, api_key, base_url, model):
    if not api_key:
        raise RuntimeError(_MENU_FAIL)

    base_url = base_url.rstrip("/")
    kcal = int(predicted_calories)
    lo = max(1, int(round(kcal * 0.9)))
    hi = int(round(kcal * 1.1))
    restrictions = _csv(profile.get("dietary_restrictions") or [])
    disliked = _csv(profile.get("disliked_foods") or [])
    preferred = _csv((profile.get("preferred_foods") or [])[:5])
    if preferred == "нет":
        preferred = "без предпочтений"

    prompt = (
        f"Составь примерное меню на {days} дня по-русски.\n"
        f"Норма около {kcal} ккал в день (ориентир для каждого дня {lo}–{hi} ккал).\n"
        f"Цель: {profile['goal']}. Учти ограничения: {restrictions}. "
        f"Не добавляй нелюбимое: {disliked}. Что-то из любимого: {preferred}.\n"
        "Формат: день 1..N, приёмы пищи с примерными калориями, в конце дня одна строка «Итого: … ккал»."
    )

    try:
        with httpx.Client(timeout=90) as http:
            r = http.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                },
            )
            r.raise_for_status()
            data = r.json()
            choices = data.get("choices") if isinstance(data, dict) else None
            if not choices:
                raise ValueError("mistral: empty choices")
            msg = choices[0].get("message") if isinstance(choices[0], dict) else None
            if not isinstance(msg, dict):
                raise ValueError("mistral: bad message shape")
            menu = (msg.get("content") or "").strip()
            if not menu:
                raise ValueError("mistral: empty content")
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise RuntimeError(_MENU_FAIL) from exc

    return menu
