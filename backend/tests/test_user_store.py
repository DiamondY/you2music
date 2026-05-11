"""Tests for UserStore (user_store.py)."""

from __future__ import annotations

import pytest

from user_store import UserStore, InviteCodeRecord


class TestUserStore:
    """CRUD and invite-code tests for UserStore."""

    # -- invite codes ----------------------------------------------------------

    def test_create_invite_code(self, user_store: UserStore) -> None:
        """create_invite_code returns a valid record with unique code."""
        rec = user_store.create_invite_code(created_by=None)
        assert isinstance(rec, InviteCodeRecord)
        assert len(rec.code) > 0
        assert rec.used_by is None
        assert rec.used_at_ms is None
        assert rec.created_by is None
        assert rec.created_at_ms > 0

    def test_list_invite_codes(self, user_store: UserStore) -> None:
        """list_invite_codes returns all codes ordered by created_at DESC."""
        c1 = user_store.create_invite_code(created_by=None)
        c2 = user_store.create_invite_code(created_by=1)
        codes = user_store.list_invite_codes()
        # Verify returned codes are a subset of what this test created (no cross-test pollution)
        expected_codes = {c1.code, c2.code}
        returned_codes = {c.code for c in codes}
        assert returned_codes.issubset(expected_codes), (
            f"got unexpected codes from other tests: {returned_codes - expected_codes}"
        )

    # -- user creation ---------------------------------------------------------

    def test_create_user_success(self, user_store: UserStore) -> None:
        """create_user with valid invite code returns a UserRecord."""
        invite = user_store.create_invite_code(created_by=None)
        user = user_store.create_user(
            username="alice",
            password_hash="hash123",
            invite_code=invite.code,
            daily_quota=20,
        )
        assert user.id > 0
        assert user.username == "alice"
        assert user.role == "user"
        assert user.daily_quota == 20
        assert user.disabled is False
        assert user.must_change_password is False

        # Invite code is now used
        codes = user_store.list_invite_codes()
        used_code = next(c for c in codes if c.code == invite.code)
        assert used_code.used_by == user.id
        assert used_code.used_at_ms is not None

    def test_create_user_duplicate_username(self, user_store: UserStore) -> None:
        """create_user raises ValueError on duplicate username."""
        invite1 = user_store.create_invite_code(created_by=None)
        invite2 = user_store.create_invite_code(created_by=None)
        user_store.create_user(
            username="bob",
            password_hash="hash",
            invite_code=invite1.code,
            daily_quota=10,
        )
        with pytest.raises(ValueError, match="username already exists"):
            user_store.create_user(
                username="bob",
                password_hash="hash2",
                invite_code=invite2.code,
                daily_quota=10,
            )

    def test_create_user_invalid_invite_code(self, user_store: UserStore) -> None:
        """create_user raises ValueError for nonexistent invite code."""
        with pytest.raises(ValueError, match="invalid invite code"):
            user_store.create_user(
                username="eve",
                password_hash="hash",
                invite_code="nonexistent-code",
                daily_quota=10,
            )

    def test_create_user_used_invite_code(self, user_store: UserStore) -> None:
        """create_user raises ValueError when invite code is already used."""
        invite = user_store.create_invite_code(created_by=None)
        user_store.create_user(
            username="first",
            password_hash="hash",
            invite_code=invite.code,
            daily_quota=10,
        )
        with pytest.raises(ValueError, match="invite code has already been used"):
            user_store.create_user(
                username="second",
                password_hash="hash2",
                invite_code=invite.code,
                daily_quota=10,
            )

    def test_create_user_empty_fields(self, user_store: UserStore) -> None:
        """create_user raises ValueError for empty username/password/invite_code."""
        invite = user_store.create_invite_code(created_by=None)

        with pytest.raises(ValueError, match="username is required"):
            user_store.create_user(
                username="",
                password_hash="hash",
                invite_code=invite.code,
                daily_quota=10,
            )
        with pytest.raises(ValueError, match="password hash is required"):
            user_store.create_user(
                username="test",
                password_hash="",
                invite_code=invite.code,
                daily_quota=10,
            )
        with pytest.raises(ValueError, match="invite code is required"):
            user_store.create_user(
                username="test",
                password_hash="hash",
                invite_code="",
                daily_quota=10,
            )

    # -- lookup ----------------------------------------------------------------

    def test_get_by_id(self, user_store: UserStore) -> None:
        """get_by_id returns correct user or None."""
        invite = user_store.create_invite_code(created_by=None)
        created = user_store.create_user(
            username="lookup",
            password_hash="h",
            invite_code=invite.code,
            daily_quota=5,
        )
        found = user_store.get_by_id(created.id)
        assert found is not None
        assert found.username == "lookup"

        assert user_store.get_by_id(99999) is None

    def test_get_by_username(self, user_store: UserStore) -> None:
        """get_by_username returns correct user or None."""
        invite = user_store.create_invite_code(created_by=None)
        user_store.create_user(
            username="namecheck",
            password_hash="h",
            invite_code=invite.code,
            daily_quota=5,
        )
        found = user_store.get_by_username("namecheck")
        assert found is not None
        assert found.username == "namecheck"

        assert user_store.get_by_username("nobody") is None

    def test_list_users(self, user_store: UserStore) -> None:
        """list_users returns all users ordered by created_at DESC."""
        assert user_store.list_users() == []

        invite1 = user_store.create_invite_code(created_by=None)
        invite2 = user_store.create_invite_code(created_by=None)
        u1 = user_store.create_user(username="u1", password_hash="h", invite_code=invite1.code, daily_quota=10)
        u2 = user_store.create_user(username="u2", password_hash="h", invite_code=invite2.code, daily_quota=10)

        users = user_store.list_users()
        assert len(users) == 2
        # Verify correct set returned (ordering is stable but not order-critical)
        assert {u.id for u in users} == {u1.id, u2.id}

    # -- ensure_admin ----------------------------------------------------------

    def test_ensure_admin_creates_first_admin(self, user_store: UserStore) -> None:
        """ensure_admin creates an admin user when no admin exists."""
        admin = user_store.ensure_admin(
            username="admin1",
            password_hash="adminhash",
            daily_quota=999,
        )
        assert admin is not None
        assert admin.username == "admin1"
        assert admin.role == "admin"
        assert admin.daily_quota == 999

    def test_ensure_admin_idempotent(self, user_store: UserStore) -> None:
        """ensure_admin returns existing admin without creating a second."""
        first = user_store.ensure_admin(
            username="admin_a",
            password_hash="h1",
            daily_quota=100,
        )
        second = user_store.ensure_admin(
            username="admin_b",
            password_hash="h2",
            daily_quota=200,
        )
        assert first is not None
        assert second is not None
        assert first.id == second.id
        assert second.username == "admin_a"  # unchanged
        assert second.daily_quota == 100  # unchanged

    # -- update_user -----------------------------------------------------------

    def test_update_user_role_and_quota(self, user_store: UserStore) -> None:
        """update_user changes role and daily_quota."""
        invite = user_store.create_invite_code(created_by=None)
        user = user_store.create_user(
            username="update_me", password_hash="h", invite_code=invite.code, daily_quota=10
        )
        updated = user_store.update_user(user.id, role="admin", daily_quota=50)
        assert updated is not None
        assert updated.role == "admin"
        assert updated.daily_quota == 50

    def test_update_user_disabled(self, user_store: UserStore) -> None:
        """update_user toggles disabled flag."""
        invite = user_store.create_invite_code(created_by=None)
        user = user_store.create_user(
            username="toggle", password_hash="h", invite_code=invite.code, daily_quota=10
        )
        assert user.disabled is False

        updated = user_store.update_user(user.id, disabled=True)
        assert updated is not None
        assert updated.disabled is True

        updated2 = user_store.update_user(user.id, disabled=False)
        assert updated2 is not None
        assert updated2.disabled is False

    def test_update_user_nonexistent(self, user_store: UserStore) -> None:
        """update_user returns None for unknown user_id."""
        assert user_store.update_user(99999, role="admin") is None

    def test_update_user_invalid_role(self, user_store: UserStore) -> None:
        """update_user raises ValueError for invalid role."""
        invite = user_store.create_invite_code(created_by=None)
        user = user_store.create_user(
            username="badrole", password_hash="h", invite_code=invite.code, daily_quota=10
        )
        with pytest.raises(ValueError, match="role must be admin or user"):
            user_store.update_user(user.id, role="superadmin")  # type: ignore[arg-type]

    # -- password / must_change_password ---------------------------------------

    def test_update_password(self, user_store: UserStore) -> None:
        """update_password changes the hash and clears must_change_password."""
        invite = user_store.create_invite_code(created_by=None)
        user = user_store.create_user(
            username="pw", password_hash="oldhash", invite_code=invite.code, daily_quota=10
        )
        user_store.set_must_change_password(user.id, True)
        assert user_store.update_password(user.id, password_hash="newhash") is True

        updated = user_store.get_by_id(user.id)
        assert updated is not None
        assert updated.password_hash == "newhash"
        assert updated.must_change_password is False

    def test_update_password_nonexistent(self, user_store: UserStore) -> None:
        """update_password returns False for unknown user_id."""
        assert user_store.update_password(99999, password_hash="h") is False

    def test_set_must_change_password(self, user_store: UserStore) -> None:
        """set_must_change_password toggles the flag."""
        invite = user_store.create_invite_code(created_by=None)
        user = user_store.create_user(
            username="mustchange", password_hash="h", invite_code=invite.code, daily_quota=10
        )
        assert user_store.set_must_change_password(user.id, True) is True
        assert user_store.get_by_id(user.id).must_change_password is True  # type: ignore[union-attr]

        assert user_store.set_must_change_password(user.id, False) is True
        assert user_store.get_by_id(user.id).must_change_password is False  # type: ignore[union-attr]

    # -- delete_user -----------------------------------------------------------

    def test_delete_user(self, user_store: UserStore) -> None:
        """delete_user removes the user and returns True."""
        invite = user_store.create_invite_code(created_by=None)
        user = user_store.create_user(
            username="deleteme", password_hash="h", invite_code=invite.code, daily_quota=10
        )
        assert user_store.delete_user(user.id) is True
        assert user_store.get_by_id(user.id) is None

    def test_delete_user_nonexistent(self, user_store: UserStore) -> None:
        """delete_user returns False for unknown user_id."""
        assert user_store.delete_user(99999) is False

    def test_delete_user_cannot_delete_last_admin(self, user_store: UserStore) -> None:
        """delete_user raises ValueError when trying to delete the last admin."""
        admin = user_store.ensure_admin(username="admin", password_hash="h", daily_quota=100)
        assert admin is not None
        with pytest.raises(ValueError, match="cannot delete the last admin"):
            user_store.delete_user(admin.id)

    # -- quota -----------------------------------------------------------------

    def test_quota_status_new_user(self, user_store: UserStore) -> None:
        """quota_status returns zero usage for a new user."""
        invite = user_store.create_invite_code(created_by=None)
        user = user_store.create_user(
            username="qt", password_hash="h", invite_code=invite.code, daily_quota=15
        )
        status = user_store.quota_status(user_id=user.id, daily_quota=user.daily_quota)
        assert status["used"] == 0
        assert status["limit"] == 15
        assert status["remaining"] == 15

    def test_consume_quota_normal(self, user_store: UserStore) -> None:
        """consume_quota deducts from remaining quota."""
        invite = user_store.create_invite_code(created_by=None)
        user = user_store.create_user(
            username="consumer", password_hash="h", invite_code=invite.code, daily_quota=10
        )
        result = user_store.consume_quota(user_id=user.id, amount=3, daily_quota=user.daily_quota)
        assert result["used"] == 3
        assert result["remaining"] == 7

        # Second consumption
        result2 = user_store.consume_quota(user_id=user.id, amount=2, daily_quota=user.daily_quota)
        assert result2["used"] == 5
        assert result2["remaining"] == 5

    def test_consume_quota_exhausted(self, user_store: UserStore) -> None:
        """consume_quota raises ValueError when quota is exhausted."""
        invite = user_store.create_invite_code(created_by=None)
        user = user_store.create_user(
            username="exhaust", password_hash="h", invite_code=invite.code, daily_quota=3
        )
        user_store.consume_quota(user_id=user.id, amount=3, daily_quota=user.daily_quota)
        with pytest.raises(ValueError, match="daily quota exhausted"):
            user_store.consume_quota(user_id=user.id, amount=1, daily_quota=user.daily_quota)

    def test_consume_quota_exact_limit(self, user_store: UserStore) -> None:
        """consume_quota allows using exactly the remaining quota."""
        invite = user_store.create_invite_code(created_by=None)
        user = user_store.create_user(
            username="exact", password_hash="h", invite_code=invite.code, daily_quota=5
        )
        result = user_store.consume_quota(user_id=user.id, amount=5, daily_quota=user.daily_quota)
        assert result["used"] == 5
        assert result["remaining"] == 0
