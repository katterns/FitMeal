from fastapi.testclient import TestClient

from infra.db.database import SessionLocal
from infra.db.models import UserModel
from main import app

client = TestClient(app)
PWD = "qwerty1234"


def login(email, password=PWD):
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return r.json()["access_token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def sample_profile():
    return {
        "age": 24,
        "sex": "female",
        "height_cm": 168,
        "weight_kg": 62,
        "activity_level": "medium",
        "goal": "maintenance",
        "dietary_restrictions": ["lactose_free"],
        "disliked_foods": ["fish"],
        "preferred_foods": ["chicken", "rice", "vegetables"],
    }


def test_health_and_root():
    assert client.get("/").status_code == 200
    assert client.get("/health").json()["status"] == "ok"


def test_register_and_login():
    body = {"email": "test_2@fitmeal.ai", "password": PWD}
    assert client.post("/api/v1/auth/register", json=body).status_code == 200
    r = client.post("/api/v1/auth/login", json=body)
    assert r.status_code == 200 and "access_token" in r.json()


def test_duplicate_user():
    body = {"email": "test_3@fitmeal.ai", "password": PWD}
    assert client.post("/api/v1/auth/register", json=body).status_code == 200
    assert client.post("/api/v1/auth/register", json=body).status_code == 400


def test_login_bad_password():
    body = {"email": "test_4@fitmeal.ai", "password": PWD}
    client.post("/api/v1/auth/register", json=body)
    r = client.post("/api/v1/auth/login", json={**body, "password": "wrongpass"})
    assert r.status_code == 401


def test_profile_needs_token():
    assert client.get("/api/v1/users/me").status_code == 401


def test_topup_and_transactions():
    h = auth(login("test_6@fitmeal.ai"))
    client.post("/api/v1/billing/topup", headers=h, json={"amount": 25})
    rows = client.get("/api/v1/billing/transactions", headers=h).json()
    assert any(row["amount"] == 25 for row in rows)


def test_basic_analysis():
    h = auth(login("test_7@fitmeal.ai"))
    r = client.post(
        "/api/v1/analysis",
        headers=h,
        json={"tariff": "basic", "profile": sample_profile()},
    )
    d = r.json()
    assert r.status_code == 200
    assert d["status"] == "completed" and d["predicted_calories"] > 0
    assert d["your_number"] == 1


def test_pro_analysis_fails_without_mistral_key():
    h = auth(login("test_8@fitmeal.ai"))
    d = client.post(
        "/api/v1/analysis",
        headers=h,
        json={"tariff": "pro", "profile": sample_profile()},
    ).json()
    assert d["status"] == "failed" and "повторите" in d["error_message"]


def test_analysis_not_found():
    r = client.get(
        "/api/v1/analysis/999999",
        headers=auth(login("test_9@fitmeal.ai")),
    )
    assert r.status_code == 404


def test_not_enough_credits():
    token = login("test_10@fitmeal.ai")
    with SessionLocal() as db:
        user = db.query(UserModel).filter(UserModel.email == "test_10@fitmeal.ai").one()
        user.balance = 1
        db.commit()
    r = client.post(
        "/api/v1/analysis",
        headers=auth(token),
        json={"tariff": "basic", "profile": sample_profile()},
    )
    assert r.status_code == 400


def test_admin_stats_forbidden(monkeypatch):
    monkeypatch.delenv("ADMIN_EMAILS", raising=False)
    from config.settings import get_settings

    get_settings.cache_clear()
    h = auth(login("test_admin_forbidden@fitmeal.ai"))
    r = client.get("/api/v1/admin/stats", headers=h)
    assert r.status_code == 403


def test_admin_stats_ok(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "test_admin_stats_admin@fitmeal.ai")
    from config.settings import get_settings

    get_settings.cache_clear()
    admin_tok = login("test_admin_stats_admin@fitmeal.ai")
    monkeypatch.delenv("ADMIN_EMAILS", raising=False)
    get_settings.cache_clear()
    user_tok = login("test_admin_stats_user@fitmeal.ai")
    client.post(
        "/api/v1/analysis",
        headers=auth(user_tok),
        json={"tariff": "basic", "profile": sample_profile()},
    )
    r = client.get("/api/v1/admin/stats", headers=auth(admin_tok))
    assert r.status_code == 200
    row = next(x for x in r.json() if x["email"] == "test_admin_stats_user@fitmeal.ai")
    assert row["requests"] == 1
    assert row["spent_credits"] == 5


def test_promo_sale50_discount_basic():
    tok = login("promo50_u@fitmeal.ai")
    assert client.post("/api/v1/promo/apply", headers=auth(tok), json={"code": "sale50"}).status_code == 200
    r = client.post(
        "/api/v1/analysis",
        headers=auth(tok),
        json={"tariff": "basic", "profile": sample_profile()},
    )
    assert r.status_code == 200
    assert r.json()["cost"] == 2


def test_promo_sale20_three_requests():
    tok = login("promo20_u@fitmeal.ai")
    assert client.post("/api/v1/promo/apply", headers=auth(tok), json={"code": "sale20three"}).status_code == 200
    for _ in range(3):
        r = client.post(
            "/api/v1/analysis",
            headers=auth(tok),
            json={"tariff": "basic", "profile": sample_profile()},
        )
        assert r.status_code == 200
        assert r.json()["cost"] == 4
    r4 = client.post(
        "/api/v1/analysis",
        headers=auth(tok),
        json={"tariff": "basic", "profile": sample_profile()},
    )
    assert r4.status_code == 200
    assert r4.json()["cost"] == 5


def test_promo_expired_cannot_apply():
    from datetime import datetime, timedelta, timezone

    from infra.db.models import PromoCodeModel

    with SessionLocal() as db:
        p = db.query(PromoCodeModel).filter(PromoCodeModel.code == "sale50").one()
        saved = p.valid_until
        p.valid_until = datetime.now(timezone.utc) - timedelta(days=1)
        db.commit()
    try:
        tok = login("promo_exp@fitmeal.ai")
        r = client.post("/api/v1/promo/apply", headers=auth(tok), json={"code": "sale50"})
        assert r.status_code == 400
    finally:
        with SessionLocal() as db:
            p = db.query(PromoCodeModel).filter(PromoCodeModel.code == "sale50").one()
            p.valid_until = saved
            db.commit()


def test_promo_still_available_after_failed_pro():
    tok = login("promo_refund_pro@fitmeal.ai")
    assert client.post("/api/v1/promo/apply", headers=auth(tok), json={"code": "sale50"}).status_code == 200
    d = client.post(
        "/api/v1/analysis",
        headers=auth(tok),
        json={"tariff": "pro", "profile": sample_profile()},
    ).json()
    assert d["status"] == "failed"
    mine = client.get("/api/v1/promo/mine", headers=auth(tok)).json()
    assert len(mine) == 1 and mine[0]["uses_left"] == 1


def test_promo_unknown_code():
    tok = login("promo_bad@fitmeal.ai")
    assert client.post("/api/v1/promo/apply", headers=auth(tok), json={"code": "nope"}).status_code == 404
