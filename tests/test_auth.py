"""Tests for nexus/auth — JWT and RBAC."""

import time

import pytest

from nexus.auth.jwt import JWTAuth, JWTError, create_token, decode_token
from nexus.auth.rbac import RBACPolicy


class TestJWT:
    def test_create_and_decode(self):
        token = create_token({"sub": "user_1", "role": "admin"}, secret="s3cr3t")
        claims = decode_token(token, secret="s3cr3t")
        assert claims["sub"] == "user_1"
        assert claims["role"] == "admin"

    def test_wrong_secret(self):
        token = create_token({"sub": "user"}, secret="right")
        with pytest.raises(JWTError, match="Invalid signature"):
            decode_token(token, secret="wrong")

    def test_expired_token(self):
        token = create_token({"sub": "user"}, secret="s", expires_in=-1)
        with pytest.raises(JWTError, match="expired"):
            decode_token(token, secret="s")

    def test_malformed_token(self):
        with pytest.raises(JWTError, match="Malformed"):
            decode_token("not.a.valid.jwt.token.parts", secret="s")

    def test_jwt_auth_class(self):
        auth = JWTAuth(secret="mysecret", expires_in=3600)
        token = auth.create({"sub": "123"})
        claims = auth.decode(token)
        assert claims["sub"] == "123"

    def test_refresh_token(self):
        import time
        auth = JWTAuth(secret="s", expires_in=3600)
        token = auth.create({"sub": "u"})
        time.sleep(1)  # ensure different iat/exp
        new_token = auth.refresh(token)
        claims = auth.decode(new_token)
        assert claims["sub"] == "u"
        # Refreshed token is valid and carries original sub
        assert claims["iat"] > 0

    def test_iat_and_exp_claims(self):
        before = int(time.time())
        token = create_token({"sub": "x"}, secret="s", expires_in=60)
        claims = decode_token(token, secret="s")
        assert claims["iat"] >= before
        assert claims["exp"] > claims["iat"]


class TestRBAC:
    def setup_method(self):
        self.policy = RBACPolicy()
        self.policy.define_role("admin", permissions={"*"})
        self.policy.define_role("editor", permissions={"articles:read", "articles:write"})
        self.policy.define_role("viewer", permissions={"articles:read", "users:read"})
        self.policy.define_role(
            "senior_editor",
            permissions={"articles:publish"},
            inherits=["editor"],
        )

    def test_admin_has_all(self):
        assert self.policy.has_permission("admin", "anything:at:all")

    def test_editor_permissions(self):
        assert self.policy.has_permission("editor", "articles:write")
        assert not self.policy.has_permission("editor", "users:write")

    def test_viewer_restrictions(self):
        assert self.policy.has_permission("viewer", "articles:read")
        assert not self.policy.has_permission("viewer", "articles:write")

    def test_inheritance(self):
        assert self.policy.has_permission("senior_editor", "articles:write")
        assert self.policy.has_permission("senior_editor", "articles:publish")
        assert not self.policy.has_permission("senior_editor", "users:write")

    def test_unknown_role(self):
        assert not self.policy.has_permission("ghost", "anything")

    def test_wildcard_resource(self):
        self.policy.define_role("content_mgr", permissions={"content:*"})
        assert self.policy.has_permission("content_mgr", "content:read")
        assert self.policy.has_permission("content_mgr", "content:delete")
        assert not self.policy.has_permission("content_mgr", "users:read")

    def test_all_permissions(self):
        perms = self.policy.all_permissions("senior_editor")
        assert "articles:publish" in perms
        assert "articles:write" in perms
