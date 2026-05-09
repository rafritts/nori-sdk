import os

from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL: str = os.getenv("NORI_MODEL")
API_KEY: str | None = os.getenv("NORI_API_KEY")
BASE_URL: str | None = os.getenv("NORI_BASE_URL")
