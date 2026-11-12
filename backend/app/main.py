
"""FastAPI application entry point."""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from mysql.connector import Error

from .config import CORS_ORIGINS, SECRET_KEY
from .database import get_connection
from .routes import auth, atm, admin


# Ensure that the JWT secret is strong enough.
if not SECRET_KEY or len(SECRET_KEY) < 32:
    raise RuntimeError(
        "SECRET_KEY must contain at least 32 characters. "
        "Set it in backend/.env"
    )


# Create the FastAPI application.
app = FastAPI(
    title="ATM Banking Simulator API",
    description="Educational simulator using fictional accounts and balances only.",
    version="2.0.0",
)


# Allow the React frontend to communicate with this backend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


# Home endpoint.
@app.get("/")
def home():
    return {
        "message": "ATM Banking Simulator API is running",
        "simulation_only": True
    }


# Health-check endpoint.
@app.get("/api/v1/health")
def health():
    """Check API and MySQL connectivity."""

    connection = None

    try:
        connection = get_connection()

        cursor = connection.cursor()
        try:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        finally:
            cursor.close()

        return {
            "api": "ok",
            "database": "connected",
            "simulation_only": True
        }

    except Error:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable; check MySQL and backend/.env"
        )

    finally:
        if connection and connection.is_connected():
            connection.close()


# Register authentication routes.
app.include_router(auth.router, prefix="/api/v1")

# Register customer ATM routes.
app.include_router(atm.router, prefix="/api/v1")

# Register administration routes.
app.include_router(admin.router, prefix="/api/v1")
