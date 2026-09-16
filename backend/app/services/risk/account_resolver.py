"""Canonical account authority and tenant resolution helper.

Enforces AUD-P1-004 and BATCHA-P1-002:
- Name vs UUID alias unification.
- Prevents cross-tenant name collisions (names scoped to owner user_id).
- Rejects ambiguous ADMIN / system / userless account name lookups across tenants.
- Returns authoritative (Account, canonical_account_id_str).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError, NotFoundError, ValidationError
from app.models import Account, Role, User


async def resolve_canonical_account(
    session: AsyncSession,
    account_ref: str,
    user: User | None = None,
    user_id: str | None = None,
    is_admin: bool = False,
) -> tuple[Account, str]:
    """Resolves an account reference (UUID or name alias) to its canonical Account record
    and canonical UUID string.

    Guarantees:
    1. If UUID -> resolved by Account.id == parsed_uuid.
    2. If string name -> scoped by user ownership (Account.name == account_ref AND Account.user_id == resolved_user_id),
       unless is_admin is True or user_id is "system".
    3. Rejects ambiguous ADMIN and system/userless name lookups matching >1 account across tenants (BATCHA-P1-002).
    4. Enforces authorization: raises ForbiddenError if caller does not own the account and is not Admin.
    5. Returns (acc_row, str(acc_row.id)) where canonical_account_id is strictly a UUID string.
    """
    effective_user_id = str(user.id) if user is not None else user_id
    admin_caller = is_admin or (user is not None and user.role == Role.ADMIN)

    # 1. Direct UUID resolution
    try:
        parsed_uuid = uuid.UUID(account_ref)
        acc_row = await session.scalar(select(Account).where(Account.id == parsed_uuid))
        if acc_row is None:
            raise NotFoundError(f"Account '{account_ref}' not found")
        if not admin_caller and effective_user_id is not None and effective_user_id != "system":
            if str(acc_row.user_id) != effective_user_id:
                raise ForbiddenError("User is not authorized to access this account")
        return acc_row, str(acc_row.id)
    except (ValueError, TypeError):
        pass

    # 2. Name alias resolution
    if not admin_caller and effective_user_id is not None and effective_user_id != "system":
        try:
            user_uuid = uuid.UUID(effective_user_id)
            stmt = select(Account).where(Account.name == account_ref, Account.user_id == user_uuid)
        except (ValueError, TypeError):
            raise NotFoundError(f"Account '{account_ref}' not found") from None
        matches = (await session.scalars(stmt)).all()
        if not matches:
            raise NotFoundError(f"Account '{account_ref}' not found for user")
        if len(matches) > 1:
            raise ValidationError(
                f"Ambiguous account name '{account_ref}' matches multiple accounts for user; canonical UUID required"
            )
        return matches[0], str(matches[0].id)

    if admin_caller:
        matches = (await session.scalars(select(Account).where(Account.name == account_ref))).all()
        if not matches:
            raise NotFoundError(f"Account '{account_ref}' not found")
        if len(matches) > 1:
            raise ValidationError(
                f"Ambiguous account name '{account_ref}' matches {len(matches)} accounts across tenants; "
                f"state-changing or administrative operations require canonical UUID"
            )
        return matches[0], str(matches[0].id)

    # System / userless caller
    matches = (await session.scalars(select(Account).where(Account.name == account_ref))).all()
    if not matches:
        raise NotFoundError(f"Account '{account_ref}' not found")
    if len(matches) > 1:
        raise ValidationError(
            f"Ambiguous account name '{account_ref}' matches {len(matches)} accounts; "
            f"system/userless resolution requires canonical UUID"
        )
    return matches[0], str(matches[0].id)
