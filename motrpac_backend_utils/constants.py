import os

from utils import get_env


# the fully qualified topic name (e.g. project/project_id/topics/topic_id)
IS_PROD = bool(int(os.getenv("PRODUCTION_DEPLOYMENT", "0")))
NOTIFIER_CF_URL = get_env("NOTIFIER_CF_URL")
