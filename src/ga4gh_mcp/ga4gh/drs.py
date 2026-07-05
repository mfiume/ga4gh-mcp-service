"""DRS (Data Repository Service) client — objects and access URLs.

Spec: https://ga4gh.github.io/data-repository-service-schemas/
Endpoints (v1.x): ``/objects/{id}`` and ``/objects/{id}/access/{access_id}``.
"""

from __future__ import annotations

from ..errors import ERR_AUTH_REQUIRED, ERR_NOT_FOUND, ERR_UPSTREAM, ToolError
from ..normalize import parse_www_authenticate
from .base import TypedClient


class DRSClient(TypedClient):
    artifact = "drs"

    async def get_object(self, url: str, object_id: str, expand: bool = False) -> dict:
        res = await self._get(url, f"/objects/{object_id}", params={"expand": "true"} if expand else None)
        if res.status == 200 and isinstance(res.json, dict):
            obj = res.json
            return {
                "id": obj.get("id"),
                "name": obj.get("name"),
                "size": obj.get("size"),
                "created_time": obj.get("created_time"),
                "updated_time": obj.get("updated_time"),
                "mime_type": obj.get("mime_type"),
                "checksums": obj.get("checksums"),
                "is_bundle": bool(obj.get("contents")),
                "access_methods": [
                    {
                        "type": am.get("type"),
                        "access_id": am.get("access_id"),
                        "region": am.get("region"),
                        "has_access_url": bool(am.get("access_url")),
                        "access_url": (am.get("access_url") or {}).get("url"),
                    }
                    for am in (obj.get("access_methods") or [])
                ],
                "contents": obj.get("contents"),
                "description": obj.get("description"),
                "raw": obj,
            }
        self._raise(res, object_id)

    async def get_access_url(self, url: str, object_id: str, access_id: str | None = None) -> dict:
        # If no access_id given, inspect the object to pick one.
        if access_id is None:
            obj = await self.get_object(url, object_id)
            methods = obj["access_methods"]
            # Prefer a direct access_url if present.
            for m in methods:
                if m.get("access_url"):
                    return {"object_id": object_id, "access_url": m["access_url"],
                            "type": m.get("type"), "via": "inline_access_url"}
            # Otherwise pick the first method that has an access_id.
            with_id = [m for m in methods if m.get("access_id")]
            if not with_id:
                raise ToolError(ERR_NOT_FOUND,
                                f"object {object_id} has no access_url or access_id to resolve")
            access_id = with_id[0]["access_id"]

        res = await self._get(url, f"/objects/{object_id}/access/{access_id}")
        if res.status == 200 and isinstance(res.json, dict):
            au = res.json
            return {"object_id": object_id, "access_id": access_id,
                    "access_url": au.get("url"), "headers_required": au.get("headers"),
                    "via": "access_endpoint"}
        self._raise(res, object_id)

    @staticmethod
    def _raise(res, object_id: str):
        if res.status in (401, 403):
            raise ToolError(ERR_AUTH_REQUIRED,
                            f"authentication required for DRS object {object_id}",
                            auth_challenge=parse_www_authenticate(res.www_authenticate) or None,
                            status=res.status)
        if res.status == 404:
            raise ToolError(ERR_NOT_FOUND, f"DRS object {object_id} not found", status=404)
        raise ToolError(ERR_UPSTREAM,
                        f"DRS request failed: {res.error or res.status}",
                        status=res.status, detail=(res.text or "")[:300] or None)
