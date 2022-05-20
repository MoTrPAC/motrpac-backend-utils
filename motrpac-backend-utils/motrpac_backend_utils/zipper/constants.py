import os

from utils import get_env


# the fully qualified topic name (e.g. project/project_id/topics/topic_id)
IS_PROD = bool(int(os.getenv("PRODUCTION_DEPLOYMENT", "0")))

MAX_IN_PROGRESS = 2

ACK_DEADLINE = int(os.getenv("ACK_DEADLINE_SECONDS", 600))
SCRATCH_LOCATION = get_env("TMP_DIR_PATH", "/tmp")
INPUT_BUCKET = get_env("INPUT_BUCKET").rstrip("/")
OUTPUT_BUCKET = get_env("OUTPUT_BUCKET")
