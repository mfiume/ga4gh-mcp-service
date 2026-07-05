"""TRS (Tool Registry Service) client — tools, versions, descriptors.

Spec: https://ga4gh.github.io/tool-registry-service-schemas/
Endpoints (v2): ``/tools``, ``/tools/{id}``, ``/tools/{id}/versions``.
"""

from __future__ import annotations

from ..errors import ERR_NOT_FOUND, ERR_UPSTREAM, ToolError
from .base import TypedClient


class TRSClient(TypedClient):
    artifact = "trs"

    async def list_tools(self, url: str, *, toolClass: str | None = None,  # noqa: N803
                         organization: str | None = None, limit: int = 20) -> dict:
        params: dict = {"limit": limit}
        if toolClass:
            params["toolClass"] = toolClass
        if organization:
            params["organization"] = organization
        res = await self._get(url, "/tools", params=params)
        if res.status == 200 and isinstance(res.json, list):
            tools = res.json[:limit]
            return {
                "count_returned": len(tools),
                "tools": [
                    {
                        "id": t.get("id"),
                        "name": t.get("name"),
                        "organization": t.get("organization"),
                        "toolclass": (t.get("toolclass") or {}).get("name"),
                        "description": (t.get("description") or "")[:300] or None,
                        "versions": [v.get("id") or v.get("name") for v in (t.get("versions") or [])],
                        "url": t.get("url"),
                    }
                    for t in tools
                ],
            }
        self._raise(res, "tools")

    async def get_tool(self, url: str, tool_id: str) -> dict:
        res = await self._get(url, f"/tools/{tool_id}")
        if res.status == 200 and isinstance(res.json, dict):
            t = res.json
            return {
                "id": t.get("id"),
                "name": t.get("name"),
                "organization": t.get("organization"),
                "toolclass": (t.get("toolclass") or {}).get("name"),
                "description": t.get("description"),
                "aliases": t.get("aliases"),
                "versions": [
                    {
                        "id": v.get("id"),
                        "name": v.get("name"),
                        "descriptor_types": v.get("descriptor_type"),
                        "is_production": v.get("is_production"),
                        "images": [i.get("image_name") for i in (v.get("images") or [])],
                    }
                    for v in (t.get("versions") or [])
                ],
                "url": t.get("url"),
            }
        self._raise(res, tool_id)

    @staticmethod
    def _raise(res, what: str):
        if res.status == 404:
            raise ToolError(ERR_NOT_FOUND, f"TRS resource {what} not found", status=404)
        raise ToolError(ERR_UPSTREAM, f"TRS request failed: {res.error or res.status}",
                        status=res.status, detail=(res.text or "")[:300] or None)
