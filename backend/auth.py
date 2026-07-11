"""Backend authentication + authorization for the client portal (P0).

The backend is reachable directly from the browser, so it must NOT trust the
`email` query param (spoofable). Instead the frontend mints a short-lived HS256
token from the server-side NextAuth session (see the frontend route
/api/auth/backend-token) and forwards it — `Authorization: Bearer <token>` for
fetch, or `?token=<token>` for EventSource (which can't set headers). This
module verifies that token and enforces site-scoped access.

Trust boundary: authorization is enforced HERE, in the FastAPI service-role
layer. RLS on the tenancy tables is deny-by-default defense-in-depth, not this.
"""
import os
from typing import Optional

import jwt
from fastapi import Request, HTTPException

ROLE_RANK = {"client_viewer": 1, "member": 2, "owner": 3}
STAFF_DOMAIN = "apexure.com"


def _secret() -> str:
    # A dedicated backend secret if set, else the shared NextAuth secret.
    return os.getenv("BACKEND_AUTH_SECRET") or os.getenv("NEXTAUTH_SECRET") or ""


def verify_token(token: str) -> Optional[str]:
    """The trusted, lowercased email from a valid HS256 token, else None.

    Never raises — a bad/expired/forged token is simply unauthenticated.
    """
    secret = _secret()
    if not token or not secret:
        return None
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except Exception:
        return None
    email = payload.get("email")
    return email.strip().lower() if isinstance(email, str) and email.strip() else None


def _token_from_request(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth[:7].lower() == "bearer ":
        return auth[7:].strip()
    return request.query_params.get("token", "")


def caller_email(request: Request) -> Optional[str]:
    """The verified caller email for this request, or None if unauthenticated."""
    return verify_token(_token_from_request(request))


def role_satisfies(role: Optional[str], min_role: str) -> bool:
    return ROLE_RANK.get(role or "", 0) >= ROLE_RANK.get(min_role, 99)


def is_staff(email: str) -> bool:
    return bool(email) and email.lower().endswith("@" + STAFF_DOMAIN)


async def _authorize_scope(email: Optional[str], scope: Optional[dict], min_role: str) -> dict:
    """Core check shared by every site-scoped route. `scope` is the site's
    {workspace_id, client_id}. Returns the caller's access context or raises."""
    from database import resolve_membership

    if not email:
        raise HTTPException(status_code=401, detail="Authentication required.")
    if not scope or not scope.get("workspace_id"):
        # Either the site doesn't exist or it predates backfill (no workspace).
        raise HTTPException(status_code=404, detail="Not found.")
    membership = await resolve_membership(email, scope["workspace_id"])
    if not membership:
        raise HTTPException(status_code=403, detail="No access to this workspace.")
    role = membership.get("role")
    if not role_satisfies(role, min_role):
        raise HTTPException(status_code=403, detail="Insufficient role for this action.")
    if role == "client_viewer" and membership.get("client_id") != scope.get("client_id"):
        raise HTTPException(status_code=403, detail="Out of scope.")
    return {"email": email, "role": role, "workspace_id": scope["workspace_id"],
            "client_id": scope.get("client_id")}


def require_site_access(min_role: str = "member"):
    """FastAPI dependency for routes with a `site_id` path param."""
    from database import site_scope

    async def dep(site_id: str, request: Request) -> dict:
        return await _authorize_scope(caller_email(request), await site_scope(site_id), min_role)

    return dep


def require_scan_access(min_role: str = "client_viewer"):
    """Dependency for routes with a `scan_id` path param (resolves scan → site)."""
    from database import scan_scope

    async def dep(scan_id: str, request: Request) -> dict:
        return await _authorize_scope(caller_email(request), await scan_scope(scan_id), min_role)

    return dep


def require_finding_access(min_role: str = "member"):
    """Dependency for routes with a `finding_id` path param."""
    from database import finding_scope

    async def dep(finding_id: str, request: Request) -> dict:
        return await _authorize_scope(caller_email(request), await finding_scope(finding_id), min_role)

    return dep
