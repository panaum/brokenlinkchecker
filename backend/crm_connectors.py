"""CRM connectors — narrow by design: exactly the three ops the tracer needs
(search a contact by the tracer email, read its properties, delete it), plus a
connection test. Two real CRMs (HubSpot, GHL) behind one interface so a third
slots in later without touching the pipeline.

Least privilege is guidance shown at connect time, not enforceable here. Tokens
are redacted in every error via tracer_crypto.redact — a connector error must
never carry a credential.
"""
from tracer_crypto import redact


class CRMError(Exception):
    """Always constructed with a redacted message."""


class Connector:
    crm_type = "base"

    async def test_connection(self) -> dict:
        raise NotImplementedError

    async def search_contact(self, email: str):
        """Return {id, properties:{...}} for the contact with this email, or None."""
        raise NotImplementedError

    async def delete_contact(self, contact_id: str) -> bool:
        raise NotImplementedError


class HubSpotConnector(Connector):
    crm_type = "hubspot"
    BASE = "https://api.hubapi.com"

    def __init__(self, token: str):
        self._token = token

    def _headers(self):
        return {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}

    async def test_connection(self) -> dict:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.get(f"{self.BASE}/crm/v3/objects/contacts?limit=1", headers=self._headers())
            if r.status_code == 200:
                return {"ok": True, "detail": "token valid · contacts scope ok"}
            if r.status_code in (401, 403):
                return {"ok": False, "detail": "token rejected or missing contacts read/write scope"}
            return {"ok": False, "detail": f"unexpected status {r.status_code}"}
        except Exception as e:
            return {"ok": False, "detail": redact(str(e))}

    async def search_contact(self, email: str):
        import httpx
        body = {
            "filterGroups": [{"filters": [{"propertyName": "email", "operator": "EQ", "value": email}]}],
            "properties": ["email", "firstname", "lastname", "phone", "company",
                           "hs_analytics_source", "gclid", "utm_source"],
            "limit": 1,
        }
        try:
            async with httpx.AsyncClient(timeout=20) as c:
                r = await c.post(f"{self.BASE}/crm/v3/objects/contacts/search",
                                 headers=self._headers(), json=body)
            if r.status_code != 200:
                raise CRMError(f"search failed: {r.status_code}")
            results = r.json().get("results", [])
            if not results:
                return None
            return {"id": results[0]["id"], "properties": results[0].get("properties", {})}
        except CRMError:
            raise
        except Exception as e:
            raise CRMError(redact(str(e)))

    async def delete_contact(self, contact_id: str) -> bool:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.delete(f"{self.BASE}/crm/v3/objects/contacts/{contact_id}", headers=self._headers())
            return r.status_code in (200, 204, 404)   # already gone counts as clean
        except Exception as e:
            raise CRMError(redact(str(e)))


class GHLConnector(Connector):
    crm_type = "ghl"
    BASE = "https://rest.gohighlevel.com/v1"

    def __init__(self, api_key: str):
        self._key = api_key

    def _headers(self):
        return {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"}

    async def test_connection(self) -> dict:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.get(f"{self.BASE}/contacts/?limit=1", headers=self._headers())
            if r.status_code == 200:
                return {"ok": True, "detail": "location key valid · contacts ok"}
            if r.status_code in (401, 403):
                return {"ok": False, "detail": "location key rejected"}
            return {"ok": False, "detail": f"unexpected status {r.status_code}"}
        except Exception as e:
            return {"ok": False, "detail": redact(str(e))}

    async def search_contact(self, email: str):
        import httpx
        try:
            async with httpx.AsyncClient(timeout=20) as c:
                r = await c.get(f"{self.BASE}/contacts/", headers=self._headers(),
                                params={"query": email, "limit": 1})
            if r.status_code != 200:
                raise CRMError(f"search failed: {r.status_code}")
            contacts = r.json().get("contacts", [])
            for ct in contacts:
                if (ct.get("email") or "").lower() == email.lower():
                    return {"id": ct.get("id"), "properties": ct}
            return None
        except CRMError:
            raise
        except Exception as e:
            raise CRMError(redact(str(e)))

    async def delete_contact(self, contact_id: str) -> bool:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.delete(f"{self.BASE}/contacts/{contact_id}", headers=self._headers())
            return r.status_code in (200, 204, 404)
        except Exception as e:
            raise CRMError(redact(str(e)))


def make_connector(crm_type: str, credentials: dict) -> Connector:
    """credentials: {token} for hubspot, {api_key} for ghl."""
    if crm_type == "hubspot":
        return HubSpotConnector(credentials.get("token") or credentials.get("api_key") or "")
    if crm_type == "ghl":
        return GHLConnector(credentials.get("api_key") or credentials.get("token") or "")
    raise CRMError(f"unsupported CRM: {crm_type}")


# Least-privilege guidance surfaced at connect time (never a secret).
CONNECT_GUIDANCE = {
    "hubspot": "Use a HubSpot private-app token scoped to crm.objects.contacts read + write only.",
    "ghl": "Use a GHL Location API key (not agency); it needs contacts read + write.",
}
