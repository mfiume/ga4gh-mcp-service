"""WES (Workflow Execution Service) client — service-info and runs.

Spec: https://ga4gh.github.io/workflow-execution-service-schemas/
Endpoints (v1): ``/service-info``, ``/runs``, ``/runs/{run_id}``, ``/runs/{run_id}/status``.
Listing/inspecting runs almost always requires authentication.
"""

from __future__ import annotations

from ..errors import ERR_AUTH_REQUIRED, ERR_NOT_FOUND, ERR_UPSTREAM, ToolError
from ..normalize import parse_www_authenticate
from .base import TypedClient


class WESClient(TypedClient):
    artifact = "wes"

    async def get_service_info(self, url: str) -> dict:
        res = await self._get(url, "/service-info")
        if res.status == 200 and isinstance(res.json, dict):
            si = res.json
            return {
                "id": si.get("id"),
                "name": si.get("name"),
                "workflow_type_versions": si.get("workflow_type_versions"),
                "supported_wes_versions": si.get("supported_wes_versions"),
                "supported_filesystem_protocols": si.get("supported_filesystem_protocols"),
                "workflow_engine_versions": si.get("workflow_engine_versions"),
                "auth_instructions_url": si.get("auth_instructions_url"),
                "system_state_counts": si.get("system_state_counts"),
                "raw": si,
            }
        self._raise(res, "service-info")

    async def list_runs(self, url: str, page_size: int = 20, page_token: str | None = None) -> dict:
        params: dict = {"page_size": page_size}
        if page_token:
            params["page_token"] = page_token
        res = await self._get(url, "/runs", params=params)
        if res.status == 200 and isinstance(res.json, dict):
            body = res.json
            return {
                "runs": [
                    {"run_id": r.get("run_id"), "state": r.get("state")}
                    for r in (body.get("runs") or [])
                ],
                "next_page_token": body.get("next_page_token"),
            }
        self._raise(res, "runs")

    async def get_run(self, url: str, run_id: str) -> dict:
        res = await self._get(url, f"/runs/{run_id}")
        if res.status == 200 and isinstance(res.json, dict):
            r = res.json
            return {
                "run_id": r.get("run_id"),
                "state": r.get("state"),
                "run_log": r.get("run_log"),
                "task_logs_count": len(r.get("task_logs") or []),
                "outputs": r.get("outputs"),
                "request": r.get("request"),
            }
        self._raise(res, run_id)

    @staticmethod
    def _raise(res, what: str):
        if res.status in (401, 403):
            raise ToolError(ERR_AUTH_REQUIRED,
                            f"authentication required for WES {what}",
                            auth_challenge=parse_www_authenticate(res.www_authenticate) or None,
                            status=res.status)
        if res.status == 404:
            raise ToolError(ERR_NOT_FOUND, f"WES resource {what} not found", status=404)
        raise ToolError(ERR_UPSTREAM, f"WES request failed: {res.error or res.status}",
                        status=res.status, detail=(res.text or "")[:300] or None)
