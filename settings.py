"""Infrastructure configuration shared by the five local applications."""

import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
# This self-contained learning project's .env is the source of local settings.
# It also avoids accidentally picking up an unrelated global OLLAMA_API_KEY.
load_dotenv(ROOT / ".env", override=True)


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default)
