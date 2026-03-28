"""JWT authentication — HS256 token creation and validation."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from nexus.core.request import Request
from nexus.di.dependencies import Depends


class JWTError(Exception):
    """Raised when a JWT is invalid, expired, or tampered with."""
    pass


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + "=" * padding)


def create_token(
    payload: dict[str, Any],
    *,
    secret: str,
    expires_in: int = 3600,
    algorithm: str = "HS256",
) -> str:
    """
    Create a signed JWT token.

    Parameters
    ----------
    payload:
        Claims to embed (e.g. ``{"sub": "user_id", "role": "admin"}``).
    secret:
        HMAC secret key.
    expires_in:
        Token lifetime in seconds (default: 1 hour).
    algorithm:
        Signing algorithm — currently only HS256 is supported.

    Returns
    -------
    str
        Compact JWT string: ``header.payload.signature``
    """
    now = int(time.time())
    claims = {
        **payload,
        "iat": now,
        "exp": now + expires_in,
    }

    header = {"alg": algorithm, "typ": "JWT"}
    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    payload_b64 = _b64url_encode(json.dumps(claims, separators=(",", ":")).encode())
    signing_input = f"{header_b64}.{payload_b64}".encode()

    sig = hmac.HMAC(secret.encode(), signing_input, hashlib.sha256).digest()
    return f"{header_b64}.{payload_b64}.{_b64url_encode(sig)}"


def decode_token(token: str, *, secret: str) -> dict[str, Any]:
    """
    Decode and verify a JWT token.

    Raises
    ------
    JWTError
        If the token is malformed, signature is invalid, or it is expired.
    """
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise JWTError("Malformed token: expected 3 parts")

        header_b64, payload_b64, sig_b64 = parts
        signing_input = f"{header_b64}.{payload_b64}".encode()
        expected_sig = hmac.HMAC(secret.encode(), signing_input, hashlib.sha256).digest()
        actual_sig = _b64url_decode(sig_b64)

        if not hmac.compare_digest(expected_sig, actual_sig):
            raise JWTError("Invalid signature")

        claims = json.loads(_b64url_decode(payload_b64))
        now = int(time.time())
        if "exp" in claims and claims["exp"] < now:
            raise JWTError("Token has expired")

        return claims
    except JWTError:
        raise
    except Exception as exc:
        raise JWTError(f"Token decode failed: {exc}") from exc


class JWTAuth:
    """
    Stateful JWT authentication helper.

    Usage::

        auth = JWTAuth(secret="super-secret", expires_in=3600)

        token = auth.create({"sub": user.id, "role": "admin"})
        claims = auth.decode(token)

        # As a DI dependency
        def get_auth():
            return JWTAuth(secret=settings.JWT_SECRET)

        @app.post("/login")
        async def login(body=Body(), auth=Depends(get_auth)):
            token = auth.create({"sub": body["user_id"]})
            return Response.json({"token": token})
    """

    def __init__(
        self,
        secret: str,
        *,
        expires_in: int = 3600,
        algorithm: str = "HS256",
    ) -> None:
        self.secret = secret
        self.expires_in = expires_in
        self.algorithm = algorithm

    def create(self, payload: dict[str, Any]) -> str:
        return create_token(
            payload,
            secret=self.secret,
            expires_in=self.expires_in,
            algorithm=self.algorithm,
        )

    def decode(self, token: str) -> dict[str, Any]:
        return decode_token(token, secret=self.secret)

    def refresh(self, token: str) -> str:
        """Issue a new token from an existing (possibly still-valid) one."""
        claims = self.decode(token)
        # Strip JWT reserved claims before re-issuing
        for key in ("iat", "exp"):
            claims.pop(key, None)
        return self.create(claims)


def jwt_required(secret: str, *, schemes: tuple[str, ...] = ("Bearer",)) -> Depends:
    """
    DI dependency factory that validates the Authorization header.

    Usage::

        SECRET = "my-secret"

        @app.get("/me")
        async def me(claims=jwt_required(SECRET)):
            return Response.json({"user": claims["sub"]})
    """
    async def _resolve(request: Request) -> dict[str, Any]:
        auth_header = request.headers.get("authorization", "")
        if not auth_header:
            raise PermissionError("Missing Authorization header")

        scheme, _, token = auth_header.partition(" ")
        if scheme not in schemes:
            raise PermissionError(f"Unsupported auth scheme: {scheme!r}")
        if not token:
            raise PermissionError("Missing token after Bearer")

        try:
            return decode_token(token, secret=secret)
        except JWTError as exc:
            raise PermissionError(str(exc)) from exc

    return Depends(_resolve)
