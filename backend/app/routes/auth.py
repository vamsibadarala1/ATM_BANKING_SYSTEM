
"""Customer/admin login and logout endpoints."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

from ..database import get_db
from ..schemas import CustomerLogin, AdminLogin
from ..security import verify_secret, create_token
from ..dependencies import current_user

router = APIRouter(tags=["Authentication"])


@router.post("/atm/login")
def customer_login(body: CustomerLogin, conn=Depends(get_db)):
    cur = conn.cursor(dictionary=True)

    try:
        # Lock the credential row to protect failed-attempt updates.
        cur.execute(
            """
            SELECT
                a.id AS account_id,
                a.account_number,
                a.status AS account_status,
                c.full_name,
                c.status AS customer_status,
                d.pin_hash,
                d.failed_attempts,
                d.locked_until
            FROM accounts a
            JOIN customers c ON c.id = a.customer_id
            JOIN demo_credentials d ON d.account_id = a.id
            WHERE a.account_number = %s
            FOR UPDATE
            """,
            (body.account_number,)
        )

        row = cur.fetchone()

        if (
            not row
            or row["account_status"] != "active"
            or row["customer_status"] != "active"
        ):
            conn.rollback()
            raise HTTPException(
                status_code=401,
                detail="Invalid credentials or inactive account"
            )

        now = datetime.now()

        if row["locked_until"] and row["locked_until"] > now:
            conn.rollback()
            raise HTTPException(
                status_code=423,
                detail="Account temporarily locked. Try again later."
            )

        if not verify_secret(body.pin, row["pin_hash"]):
            attempts = row["failed_attempts"] + 1
            lock_until = (
                now + timedelta(minutes=5)
                if attempts >= 3 else None
            )

            cur.execute(
                """
                UPDATE demo_credentials
                SET failed_attempts = %s, locked_until = %s
                WHERE account_id = %s
                """,
                (
                    0 if lock_until else attempts,
                    lock_until,
                    row["account_id"]
                )
            )

            conn.commit()

            raise HTTPException(
                status_code=401,
                detail="Invalid credentials"
            )

        cur.execute(
            """
            UPDATE demo_credentials
            SET failed_attempts = 0, locked_until = NULL
            WHERE account_id = %s
            """,
            (row["account_id"],)
        )

        conn.commit()

        token = create_token(
            str(row["account_id"]),
            "customer",
            row["account_id"]
        )

        return {
            "access_token": token,
            "token_type": "bearer",
            "profile": {
                "name": row["full_name"],
                "account_number": row["account_number"],
                "role": "customer"
            }
        }

    finally:
        cur.close()


@router.post("/admin/login")
def admin_login(body: AdminLogin, conn=Depends(get_db)):
    cur = conn.cursor(dictionary=True)

    try:
        email = body.email.strip().lower()

        cur.execute(
            """
            SELECT
                id,
                full_name,
                email,
                password_hash,
                role,
                is_active
            FROM admin_users
            WHERE LOWER(email) = %s
            """,
            (email,)
        )

        row = cur.fetchone()

    finally:
        cur.close()

    if (
        not row
        or not row["is_active"]
        or not verify_secret(body.password, row["password_hash"])
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid administrator credentials"
        )

    token = create_token(
        str(row["id"]),
        row["role"]
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "profile": {
            "name": row["full_name"],
            "email": row["email"],
            "role": row["role"]
        }
    }


@router.post("/atm/logout")
def logout(user=Depends(current_user), conn=Depends(get_db)):
    expires = datetime.fromtimestamp(
        user["exp"], timezone.utc
    ).replace(tzinfo=None)

    cur = conn.cursor()

    try:
        cur.execute(
            """
            INSERT IGNORE INTO revoked_tokens (jti, expires_at)
            VALUES (%s, %s)
            """,
            (user["jti"], expires)
        )

        conn.commit()

    finally:
        cur.close()

    return {"message": "Session ended"}
