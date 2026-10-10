"""Worker configuration"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "postgresql://earlysignals:earlysignals_dev@localhost:5432/earlysignals",
    )
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    MEILI_URL = os.getenv("MEILI_URL", "http://localhost:7700")
    MEILI_MASTER_KEY = os.getenv("MEILI_MASTER_KEY", "masterKey_dev_change_in_prod")
    # Nombre de snapshots traités par batch (1 transaction PostgreSQL par batch).
    WORKER_BATCH_SIZE = int(os.getenv("WORKER_BATCH_SIZE", "10"))
    WORKER_SCORE_THRESHOLD_INSTANT_NOTIF = int(
        os.getenv("WORKER_SCORE_THRESHOLD_INSTANT_NOTIF", "70")
    )
    LLM_API_KEY = os.getenv("LLM_API_KEY", "")
    LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")


config = Config()
