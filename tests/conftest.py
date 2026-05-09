import os
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_fitmeal.db")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("CELERY_TASK_ALWAYS_EAGER", "true")
os.environ.setdefault("MISTRAL_API_KEY", "")

Path("test_fitmeal.db").unlink(missing_ok=True)

from infra.db.database import engine
from infra.db.models import Base


Base.metadata.create_all(bind=engine)
