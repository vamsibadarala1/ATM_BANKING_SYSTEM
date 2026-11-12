"""Read environment configuration once when the application starts."""
import os
from pathlib import Path
from dotenv import load_dotenv

# .env is stored in backend/, two levels above this file.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "Vamsi@143"),
    "database": os.getenv("DB_NAME", "atm_practice"),
    "connection_timeout": 8,
}
SECRET_KEY = os.getenv("SECRET_KEY", "")
ACCESS_TOKEN_MINUTES = int(os.getenv("ACCESS_TOKEN_MINUTES", "30"))
CORS_ORIGINS = [x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if x.strip()]
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@atm-demo.local").lower()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Admin@12345")
