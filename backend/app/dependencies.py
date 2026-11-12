
"""Reusable authentication and role checks shared by route modules."""

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError

from .database import get_db
from .security import decode_token


# Creates the HTTP Bearer authentication scheme.
# FastAPI uses this to display the Authorize button in Swagger.
bearer_scheme = HTTPBearer(auto_error=False)


def current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    conn=Depends(get_db)
):
    """Validate the JWT and return the authenticated user's information."""

    # Check whether the user supplied an access token.
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # Make sure the authentication scheme is Bearer.
    if credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Bearer authentication required",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # Extract the actual token string.
    token = credentials.credentials

    try:
        # Decode and verify the JWT signature and expiry.
        payload = decode_token(token)
    except JWTError:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired session",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # Check whether this token has been revoked by logout.
    jti = payload.get("jti")

    if not jti:
        raise HTTPException(
            status_code=401,
            detail="Invalid session token"
        )

    cur = conn.cursor()

    try:
        cur.execute(
            "SELECT jti FROM revoked_tokens WHERE jti=%s",
            (jti,)
        )
        revoked = cur.fetchone()
    finally:
        cur.close()

    if revoked:
        raise HTTPException(
            status_code=401,
            detail="Session has ended"
        )

    return payload


def customer_user(user=Depends(current_user)):
    """Allow access only to authenticated customers."""

    if user.get("role") != "customer":
        raise HTTPException(
            status_code=403,
            detail="Customer access required"
        )

    return user


def admin_user(user=Depends(current_user)):
    """Allow access to administrators and auditors."""

    if user.get("role") not in ("admin", "auditor"):
        raise HTTPException(
            status_code=403,
            detail="Administrator access required"
        )

    return user


def require_admin(user=Depends(current_user)):
    """Allow access only to administrators."""

    if user.get("role") != "admin":
        raise HTTPException(
            status_code=403,
            detail="Administrator permission required"
        )

    return user
