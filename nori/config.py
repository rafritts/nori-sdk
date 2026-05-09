import os

from dotenv import load_dotenv

load_dotenv()

API_KEY: str | None = os.getenv("NORI_API_KEY")
