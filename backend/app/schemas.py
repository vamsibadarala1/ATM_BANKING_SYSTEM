
"""Pydantic request models: validate incoming JSON before route logic runs."""

import re
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, EmailStr, field_validator


class CustomerLogin(BaseModel):
    account_number: str = Field(min_length=6, max_length=20)
    pin: str = Field(min_length=4, max_length=8, pattern=r"^\d+$")


class AdminLogin(BaseModel):
    # Accept normal email addresses and fictional demo domains such as .local.
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_admin_email(cls, value):
        value = value.strip().lower()

        # Basic email structure validation, intentionally allowing .local.
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("Enter a valid administrator email address")

        return value


class AmountRequest(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    idempotency_key: str = Field(min_length=8, max_length=100)


class TransferRequest(AmountRequest):
    beneficiary_account_number: str = Field(min_length=6, max_length=20)


class ChangePinRequest(BaseModel):
    current_pin: str = Field(min_length=4, max_length=8, pattern=r"^\d+$")
    new_pin: str = Field(min_length=4, max_length=8, pattern=r"^\d+$")


class CustomerCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    phone: str = Field(default="", max_length=20)
    account_number: str = Field(min_length=6, max_length=20, pattern=r"^\d+$")
    initial_balance: Decimal = Field(
        default=Decimal("0.00"), ge=0, max_digits=12, decimal_places=2
    )
    pin: str = Field(min_length=4, max_length=8, pattern=r"^\d+$")
    daily_limit: Decimal = Field(
        default=Decimal("20000.00"), gt=0, max_digits=12, decimal_places=2
    )
    transaction_limit: Decimal = Field(
        default=Decimal("10000.00"), gt=0, max_digits=12, decimal_places=2
    )


class AccountUpdate(BaseModel):
    status: Optional[str] = None
    daily_limit: Optional[Decimal] = Field(default=None, gt=0)
    transaction_limit: Optional[Decimal] = Field(default=None, gt=0)

    @field_validator("status")
    @classmethod
    def valid_status(cls, value):
        if value is not None and value not in {
            "active", "inactive", "blocked", "closed"
        }:
            raise ValueError(
                "Status must be active, inactive, blocked or closed"
            )
        return value
