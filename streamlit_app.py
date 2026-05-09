import os
import time

import pandas as pd
import requests
import streamlit as st


API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

TARIFF_OPTIONS = {
    "Базовый - расчёт калорий": "basic",
    "Продвинутый - рекомендация меню": "pro",
}
SEX_OPTIONS = {
    "Женский": "female",
    "Мужской": "male",
}
ACTIVITY_OPTIONS = {
    "Низкая": "low",
    "Средняя": "medium",
    "Высокая": "high",
}
GOAL_OPTIONS = {
    "Снижение веса": "weight_loss",
    "Поддержание веса": "maintenance",
    "Набор массы": "muscle_gain",
}

FORM_KEYS = [
    "form_tariff_label",
    "form_age",
    "form_sex_label",
    "form_height_cm",
    "form_weight_kg",
    "form_activity_label",
    "form_goal_label",
    "form_restrictions",
    "form_disliked",
    "form_preferred",
]


def split_csv(text):
    return [x.strip() for x in text.split(",") if x.strip()]


def load_form(uid, defaults):
    def pick(options, value, default):
        for label, option_value in options.items():
            if option_value == value:
                return label
        return default

    if st.session_state.get("profile_form_user_id") == uid:
        return

    for key in FORM_KEYS:
        st.session_state.pop(key, None)

    st.session_state["profile_form_user_id"] = uid
    st.session_state["form_tariff_label"] = pick(
        TARIFF_OPTIONS, defaults.get("tariff", "basic"), "Базовый - расчёт калорий"
    )
    st.session_state["form_age"] = int(defaults.get("age", 25))
    st.session_state["form_sex_label"] = pick(SEX_OPTIONS, defaults.get("sex", "female"), "Женский")
    st.session_state["form_height_cm"] = float(defaults.get("height_cm", 170.0))
    st.session_state["form_weight_kg"] = float(defaults.get("weight_kg", 65.0))
    st.session_state["form_activity_label"] = pick(
        ACTIVITY_OPTIONS, defaults.get("activity_level", "medium"), "Средняя"
    )
    st.session_state["form_goal_label"] = pick(
        GOAL_OPTIONS, defaults.get("goal", "maintenance"), "Поддержание веса"
    )
    st.session_state["form_restrictions"] = ", ".join(defaults.get("dietary_restrictions", []))
    st.session_state["form_disliked"] = ", ".join(defaults.get("disliked_foods", []))
    st.session_state["form_preferred"] = ", ".join(defaults.get("preferred_foods", ["курица", "рис", "овощи"]))


def call_api(method, path, token=None, **kwargs):
    headers = kwargs.pop("headers", {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = requests.request(method, f"{API_BASE_URL}{path}", headers=headers, timeout=30, **kwargs)
    if r.status_code >= 400:
        detail = r.json().get("detail", r.text)
        st.error("Проверьте корректность заполнения формы." if isinstance(detail, list) else detail)
        return None
    return r.json()


def get_analysis_status_raw(analysis_id, token):
    """GET статуса без st.error — для частого опроса."""
    try:
        r = requests.get(
            f"{API_BASE_URL}/api/v1/analysis/{analysis_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=(5, 25),
        )
        if r.status_code == 200:
            return r.json()
    except requests.RequestException:
        pass
    return None


def login_form():
    st.subheader("Вход")
    email = st.text_input("Email")
    password = st.text_input("Пароль", type="password")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Зарегистрироваться"):
            if not email or "@" not in email or len(password) < 6:
                st.error("Введите корректный email и пароль минимум из 6 символов.")
                return
            user = call_api(
                "POST",
                "/api/v1/auth/register",
                json={"email": email, "password": password},
            )
            if user:
                st.success("Пользователь создан, теперь войдите")

    with col2:
        if st.button("Войти"):
            if not email or not password:
                st.error("Введите email и пароль.")
                return
            token = call_api(
                "POST",
                "/api/v1/auth/login",
                json={"email": email, "password": password},
            )
            if token:
                st.session_state["token"] = token["access_token"]
                st.rerun()


def user_dashboard(token, me):
    me = call_api("GET", "/api/v1/users/me", token=token) or me
    st.write(f"Пользователь: `{me['email']}`")
    st.metric("Баланс", f"{me['balance']} кредитов")

    with st.expander("Пополнить тестовый баланс"):
        amount = st.number_input("Сумма", min_value=1, max_value=10_000, value=100)
        if st.button("Пополнить"):
            call_api("POST", "/api/v1/billing/topup", token=token, json={"amount": amount})
            st.rerun()

    with st.expander("Промокод"):
        code = st.text_input("Код", key="promo_code_field")
        if st.button("Активировать") and code.strip():
            if res := call_api("POST", "/api/v1/promo/apply", token=token, json={"code": code.strip()}):
                st.success(res.get("message", "Готово"))
                st.rerun()
        if promos := call_api("GET", "/api/v1/promo/mine", token=token):
            for p in promos:
                st.caption(f"{p['code']}: −{p['discount_percent']}% · осталось: {p['uses_left']}")

    st.subheader("Анализ питания")
    last_profile = call_api("GET", "/api/v1/analysis/profile/last", token=token)
    defaults = last_profile or {}
    load_form(me["id"], defaults)

    with st.form("analysis_form"):
        tariff_label = st.selectbox(
            "Тариф",
            list(TARIFF_OPTIONS),
            key="form_tariff_label",
        )
        age = st.number_input(
            "Возраст",
            min_value=14,
            max_value=90,
            key="form_age",
        )
        sex_label = st.selectbox(
            "Пол для формулы калорий",
            list(SEX_OPTIONS),
            key="form_sex_label",
        )
        height_cm = st.number_input(
            "Рост, см",
            min_value=120.0,
            max_value=230.0,
            key="form_height_cm",
        )
        weight_kg = st.number_input(
            "Вес, кг",
            min_value=35.0,
            max_value=250.0,
            key="form_weight_kg",
        )
        activity_label = st.selectbox(
            "Активность",
            list(ACTIVITY_OPTIONS),
            key="form_activity_label",
        )
        goal_label = st.selectbox(
            "Цель",
            list(GOAL_OPTIONS),
            key="form_goal_label",
        )
        restrictions = st.text_input(
            "Ограничения через запятую",
            key="form_restrictions",
        )
        disliked = st.text_input(
            "Нелюбимые продукты через запятую",
            key="form_disliked",
        )
        preferred = st.text_input(
            "Любимые продукты через запятую",
            key="form_preferred",
        )
        submitted = st.form_submit_button("Запустить анализ")

    if submitted:
        payload = {
            "tariff": TARIFF_OPTIONS[tariff_label],
            "profile": {
                "age": age,
                "sex": SEX_OPTIONS[sex_label],
                "height_cm": height_cm,
                "weight_kg": weight_kg,
                "activity_level": ACTIVITY_OPTIONS[activity_label],
                "goal": GOAL_OPTIONS[goal_label],
                "dietary_restrictions": split_csv(restrictions),
                "disliked_foods": split_csv(disliked),
                "preferred_foods": split_csv(preferred),
            },
        }
        result = call_api("POST", "/api/v1/analysis", token=token, json=payload)
        if result:
            poll_hint = st.empty()
            with st.spinner("Анализ обрабатывается…"):
                result = poll_analysis(result["id"], token, progress_placeholder=poll_hint)
            poll_hint.empty()
            num = result.get("your_number")
            human = f"Ваш анализ №{num}" if num is not None else "Анализ"
            if result.get("status") == "completed":
                st.success(f"{human} успешно выполнен.")
            elif result.get("status") == "failed":
                st.error(f"{human} завершился ошибкой.")
            else:
                st.info(
                    f"{human} ещё обрабатывается на сервере (ожидание в интерфейсе уже закончилось). "
                    "Обновите страницу или разверните первый пункт в истории ниже через минуту."
                )
            show_one(result)
            st.rerun()
    if st.button("Обновить историю"):
        st.rerun()
    history = call_api("GET", "/api/v1/analysis/history", token=token)
    if history:
        for idx, item in enumerate(history[:10]):
            yn = item.get("your_number")
            title = (
                f"Ваш анализ №{yn} · {item['tariff']} · {item['status']}"
                if yn is not None
                else f"Анализ · {item['tariff']} · {item['status']}"
            )
            with st.expander(title, expanded=(idx == 0)):
                show_one(item)


def admin_stats_tab(token):
    st.subheader("Пользователи")
    stats = call_api("GET", "/api/v1/admin/stats", token=token)
    if not stats:
        return
    df = pd.DataFrame(stats)
    if df.empty:
        st.info("Пока нет пользователей.")
        return
    df = df.rename(
        columns={
            "email": "Email",
            "requests": "Запросов",
            "spent_credits": "Потрачено кредитов",
        }
    )
    st.dataframe(df, use_container_width=True, hide_index=True)


def poll_analysis(analysis_id, token, *, max_wait_seconds=320, interval=1.5, progress_placeholder=None):
    """Ждём completed/failed с учётом Pro+Mistral и лимитов Celery"""
    result = {"id": analysis_id, "status": "pending"}
    t0 = time.monotonic()
    deadline = t0 + max_wait_seconds
    while time.monotonic() < deadline:
        if progress_placeholder is not None:
            progress_placeholder.caption(f"Запрос статуса… прошло ~{int(time.monotonic() - t0)} с")
        loaded = get_analysis_status_raw(analysis_id, token)
        if loaded:
            result = loaded
            if loaded.get("status") in {"completed", "failed"}:
                return loaded
        time.sleep(interval)
    return result


def show_one(result):
    if result.get("status") in {"pending", "processing"}:
        st.info("Ещё считается на сервере.")
        return
    if result.get("status") == "failed":
        st.error(result.get("error_message") or "Анализ завершился ошибкой")
        return
    kcal = result.get("predicted_calories")
    if kcal is not None:
        st.metric("Рекомендуемая дневная калорийность", f"{kcal} ккал")
    if result.get("meal_plan_text"):
        st.subheader("Рекомендация меню на 3 дня")
        st.write(result["meal_plan_text"])
        if result.get("meal_plan_explanation"):
            st.info(result["meal_plan_explanation"])


def main():
    st.set_page_config(page_title="FitMeal AI")
    st.title("FitMeal AI")

    token = st.session_state.get("token")
    if not token:
        login_form()
    else:
        if st.button("Выйти"):
            st.session_state.pop("token", None)
            st.session_state.pop("profile_form_user_id", None)
            for key in FORM_KEYS:
                st.session_state.pop(key, None)
            st.rerun()
        me = call_api("GET", "/api/v1/users/me", token=token)
        if not me:
            return
        if me.get("role") == "admin":
            st.caption(f"Админ: `{me['email']}`")
            admin_stats_tab(token)
        else:
            user_dashboard(token, me)


if __name__ == "__main__":
    main()
