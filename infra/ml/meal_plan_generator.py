import httpx

from core.domain import MealPlan

_MENU_FAIL = "Не удалось подготовить меню. Пожалуйста, повторите запрос позже."


class MealPlanGenerator:
    def __init__(self, api_key=None, base_url="https://api.mistral.ai/v1", model="mistral-medium-latest"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def generate(self, profile, predicted_calories, days):
        if not self.api_key:
            raise RuntimeError(_MENU_FAIL)

        kcal = int(predicted_calories)
        lo, hi = max(1, int(round(kcal * 0.9))), int(round(kcal * 1.1))
        restrictions = ", ".join(profile.dietary_restrictions) or "без ограничений"
        disliked = ", ".join(profile.disliked_foods) or "нет"
        preferred = ", ".join(profile.preferred_foods[:4]) or "простые продукты"
        block = (
            f"ТВОЯ ЕДИНСТВЕННАЯ СУТОЧНАЯ ЦЕЛЬ: ровно {kcal} ккал в день.\n"
            f"Сумма ккал за КАЖДЫЙ день (завтрак+обед+перекус+ужин) должна быть в диапазоне {lo}–{hi} ккал, не ниже {lo} и не выше {hi}.\n"
            f"Запрещено писать «Итого: 1300–1500 ккал» если цель {kcal} — увеличивай порции граммами, добавляй гарниры или второй перекус, пока дневная сумма не попадёт в [{lo}; {hi}].\n"
            f"Меню на {days} дней, русский язык.\n"
            f"Цель питания: {profile.goal.value}.\n"
            f"Исключить: {restrictions}. Не включать нелюбимое: {disliked}. Предпочтения: {preferred}.\n"
            "Формат: День N, приёмы с ккал, в конце строка «Итого: N ккал». Без примечаний «добавьте ещё» в конце."
        )
        try:
            async with httpx.AsyncClient(timeout=60) as http:
                r = await http.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": block}],
                        "temperature": 0.25,
                    },
                )
                r.raise_for_status()
                menu = r.json()["choices"][0]["message"]["content"].strip()
        except (httpx.HTTPError, KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(_MENU_FAIL) from exc

        return MealPlan(days=days, menu_text=menu, explanation="")
