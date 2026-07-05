"""Service-type plugin registry.

Adding support for a new GA4GH service type is a matter of registering a
:class:`ServiceTypePlugin` here. Types without a bespoke plugin are still fully
usable through the generic service-info + ``service_request`` tools, so the
server degrades gracefully to "generic" for anything it doesn't specialize.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ServiceTypePlugin:
    artifact: str
    title: str
    spec_url: str
    docs_url: str
    #: Human description of what the typed tools can do.
    capabilities: tuple[str, ...] = ()
    #: Names of the MCP tools specialized for this type.
    tools: tuple[str, ...] = ()
    #: Nested API prefix relative to the service base (for reference/UX).
    api_prefix: str | None = None
    notes: str = ""


REGISTRY: dict[str, ServiceTypePlugin] = {}


def register(plugin: ServiceTypePlugin) -> None:
    REGISTRY[plugin.artifact] = plugin


def get(artifact: str | None) -> ServiceTypePlugin | None:
    return REGISTRY.get((artifact or "").lower())


def all_plugins() -> list[ServiceTypePlugin]:
    return list(REGISTRY.values())


# ---- built-in plugins -----------------------------------------------------

register(ServiceTypePlugin(
    artifact="drs",
    title="Data Repository Service",
    spec_url="https://github.com/ga4gh/data-repository-service-schemas",
    docs_url="https://ga4gh.github.io/data-repository-service-schemas/",
    api_prefix="/ga4gh/drs/v1",
    capabilities=("Fetch object metadata (size, checksums, access methods)",
                  "Resolve a downloadable access URL for an object"),
    tools=("drs_get_object", "drs_get_access_url", "drs_resolve_curie"),
    notes="Most common type in the registry (22 deployments, spec 1.1-1.4).",
))

register(ServiceTypePlugin(
    artifact="trs",
    title="Tool Registry Service",
    spec_url="https://github.com/ga4gh/tool-registry-service-schemas",
    docs_url="https://ga4gh.github.io/tool-registry-service-schemas/",
    api_prefix="/ga4gh/trs/v2",
    capabilities=("List registered tools/workflows", "Inspect a tool and its versions"),
    tools=("trs_list_tools", "trs_get_tool"),
))

register(ServiceTypePlugin(
    artifact="wes",
    title="Workflow Execution Service",
    spec_url="https://github.com/ga4gh/workflow-execution-service-schemas",
    docs_url="https://ga4gh.github.io/workflow-execution-service-schemas/",
    api_prefix="/ga4gh/wes/v1",
    capabilities=("Read WES service capabilities", "List and inspect workflow runs (auth)"),
    tools=("wes_get_service_info", "wes_list_runs", "wes_get_run"),
))

register(ServiceTypePlugin(
    artifact="service-registry",
    title="Service Registry",
    spec_url="https://github.com/ga4gh-discovery/ga4gh-service-registry",
    docs_url="https://ga4gh.github.io/ga4gh-registry/docs/index.html",
    capabilities=("Enumerate services a registry advertises",),
    tools=("service_get_info", "service_request"),
    notes="Handled generically via service-info + service_request.",
))

for _art, _title, _spec, _docs in [
    ("refget", "Refget", "https://github.com/samtools/hts-specs",
     "https://samtools.github.io/hts-specs/refget.html"),
    ("htsget", "htsget", "https://github.com/samtools/hts-specs",
     "https://samtools.github.io/hts-specs/htsget.html"),
    ("rnaget", "RNAget", "https://github.com/ga4gh-rnaseq/schema",
     "https://ga4gh-rnaseq.github.io/schema/docs/index.html"),
    ("search", "Discovery Search / Data Connect", "https://github.com/ga4gh-discovery/data-connect",
     "https://github.com/ga4gh-discovery/data-connect"),
    ("beacon", "Beacon", "https://github.com/ga4gh-beacon/beacon-v2",
     "https://docs.genomebeacons.org/"),
    ("tes", "Task Execution Service", "https://github.com/ga4gh/task-execution-schemas",
     "https://ga4gh.github.io/task-execution-schemas/"),
]:
    register(ServiceTypePlugin(
        artifact=_art, title=_title, spec_url=_spec, docs_url=_docs,
        capabilities=("Generic access via service-info + service_request",),
        tools=("service_get_info", "service_request"),
        notes="Generic (no bespoke typed tools yet — easy to add via a plugin).",
    ))
