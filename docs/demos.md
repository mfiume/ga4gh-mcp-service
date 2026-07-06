# Demonstration concepts — GA4GH MCP service

Ideas for the most compelling thing we could show with this server, ranked, with what each
proves, which tools it uses, whether it runs today, and the honest caveats. All numbers below are
real, pulled from the live registry on **2026-07-05** via `python scripts/probe_registry.py` — not
illustrative. Re-run any time to refresh.

## The one-line "wow"

> Any AI client (Claude Desktop, Claude Code, Vertex, Bedrock), through one small server, can
> **discover and use the entire GA4GH federation in plain language** — and it stays honest about
> the messy reality of real deployments instead of pretending everything is up and compliant.

Two things make that land: the **universality** (no bespoke integration per service) and the
**honesty** (it classifies down / non-compliant / version-drifted / auth-gated services instead of
crashing or lying).

## Audience lenses (who we'd show this to, and what they care about)

- **GA4GH community / AI Workstream:** the ecosystem becoming *legible to AI*; conformance and
  version reality across real implementations.
- **DNAstack stakeholders / partners:** the discover → access → compute federation story, told by
  an agent, with zero glue code.
- **Funders / execs:** "watch an AI get genomics-federation superpowers in 60 seconds."

---

## Ranked concepts

### 1. Live "State of the GA4GH Ecosystem" health & conformance report  ★ recommended headliner (the hook)

**Story.** Ask the agent: *"Audit every service in the GA4GH Implementation Registry and tell me
what's actually live, spec-compliant, and version-consistent."* In ~30s it probes all 46 registered
implementations and returns a structured, sourced report.

**What it proves.** The hard engineering (robust liveness classification, tolerant service-info
parsing, version reconciliation, auth discovery) — and it surfaces **genuinely new, talk-worthy
findings** nobody currently has a live view of.

**Real findings it would surface today (2026-07-05):**
- Only **24 of 46** registered implementations are **live and spec-compliant** right now (~52%).
- **12 of those 24 live services report a `type.version` that disagrees with the registry's declared
  spec version.** Almost all are Gen3-based DRS servers reporting the *service-info schema* version
  (`1.0.3`) where the registry declares the *DRS API* version (`1.2.0`). This is a real, nuanced
  ambiguity in how the community populates `type.version` — exactly the kind of thing the AI
  Workstream / conformance effort should see.
- **WES, htsget, and refget each have 0 live+compliant endpoints** among registered entries.
- **8 entries are effectively dead** (DNS failures on placeholder hosts, a private `10.x` IP, a TLS
  mismatch on BioContainers, 404s).
- Live coverage by type: DRS 17/27, TES 3/8, TRS 3/6, Beacon 1/1, WES 0/1, htsget 0/2, refget 0/1.
- The federation is **global**: 11 countries represented (US, UK, Czechia, Canada, South Africa,
  Finland, Germany, China, Japan, Chile, Greece).

**Tools used.** `list_services`, `list_service_types`, `check_service_health` (fan-out), `get_service_info`.

**Feasible today?** ✅ Fully, headless, no credentials. This is the strongest immediate demo.

**Headline.** *"An AI just gave the GA4GH community the first live conformance snapshot of its own
ecosystem — and found that half of the working DRS servers disagree with the registry about which
version they run."*

**Caveats.** The version "drift" is mostly a spec-interpretation nuance, not services being broken —
we should present it precisely (and it's more interesting told that way). Numbers shift as the
registry changes; always re-probe before showing.

### 2. Discover → Access → Compute across the federation  ★ recommended headliner (the payoff)

**Story.** *"Find a variant-calling workflow anywhere in the GA4GH ecosystem, show me a dataset I
could run it on, and tell me where it could execute."* The agent queries TRS registries (Dockstore,
WorkflowHub, Yevis) for the workflow, resolves a DRS data object to a concrete access URL, and
identifies live TES/WES execution endpoints — narrating the whole federated chain in plain English.

**What it proves.** The GA4GH / DNAstack north star: standards-based **compute-to-data federation**,
assembled on the fly by an agent across independently operated services.

**Tools used.** `trs_list_tools` / `trs_get_tool`, `drs_get_object` / `drs_get_access_url`,
`tes_list_tasks` (as "where could this run"), `list_services(product=TES/WES)`.

**Feasible today?** ⚠️ Partially. Discovery (TRS/registry) and DRS metadata resolution work now on
public services. Actually *executing* a workflow or fetching protected bytes needs credentials and a
cooperating endpoint — stage that part or narrate it. Great as a vision demo; scope the live portion
to discovery + resolution.

**Headline.** *"From a plain-English request to a runnable, federated genomics pipeline — no custom
integration, three GA4GH standards stitched together live."*

**Caveats.** Real data access is auth-gated; pick a public workflow + a resolvable public DRS object
for the live portion, and describe the compute step.

### 3. Conversational registry exploration (the easy crowd-pleaser)

**Story.** A relaxed Claude Desktop chat: *"What genomics services run in Africa?"* (uses
geolocation), *"Which organizations operate DRS servers?"*, *"Compare Terra's and Gen3's DRS
implementations,"* *"Is the Dockstore TRS healthy right now?"* The agent answers each by calling the
right tools and reasoning over the results.

**What it proves.** Immediate, tactile usefulness; low-risk; shows the breadth of the tool surface.

**Tools used.** `list_services`, `list_organisations`, `search_services`, `check_service_health`, `get_service`.

**Feasible today?** ✅ Fully. Best opener for a live, unscripted audience.

**Headline.** *"Ask the genomics federation anything, in English."*

**Caveats.** Lower "wow" ceiling on its own; use as the warm-up before #1/#2.

### 4. AI conformance co-pilot for implementers

**Story.** An implementer points the agent at their (or any) service: *"How spec-compliant is this
DRS server? What's missing, and does its reported version match what it claims?"* The agent returns
missing required fields, shape classification, and the declared-vs-reported version reconciliation.

**What it proves.** Direct utility to the people who *build* GA4GH services; complements the GA4GH
conformance/testbed work with an AI-native interface.

**Tools used.** `get_service_info`, `check_service_health`.

**Feasible today?** ✅ Fully. Strong for an implementer/working-group audience specifically.

**Headline.** *"A conformance reviewer for GA4GH services that any implementer can talk to."*

**Caveats.** We check service-info compliance + liveness, not full endpoint-level conformance (that's
the Testbed's job); position it as complementary, not a replacement.

### 5. Workflow portability across TRS registries

**Story.** *"Show me every registered workflow for X across Dockstore, WorkflowHub, and Yevis, and
where they overlap."* The agent unifies three independently run tool registries into one view.

**What it proves.** TRS as a real interoperability layer; the value of a common client across
registries.

**Tools used.** `list_services(product=TRS)`, `trs_list_tools`, `trs_get_tool`.

**Feasible today?** ✅ For listing/detail on the 3 live TRS registries. Deep cross-registry dedup is
a nice extension.

**Headline.** *"One question, every workflow registry."*

### 6. "Any client, instant genomics" universality montage

**Story.** The same natural-language genomics question answered in **Claude Desktop, Claude Code,
and a Vertex/Bedrock agent**, all pointed at the same server — showing the integration is write-once,
use-everywhere.

**What it proves.** The MCP + universality thesis: the ecosystem plugs into *any* agent platform.

**Tools used.** Any (the point is the transports/clients).

**Feasible today?** ✅ stdio clients now; HTTP clients need the server hosted (Dockerfile ready).

**Headline.** *"Write the genomics integration once; every AI platform gets it."*

### 7. Federated Beacon variant discovery (future)

**Story.** *"Has anyone seen variant chr17:g.41246747 in a registered Beacon?"* — a federated
variant query.

**Feasible today?** ⛔ Limited: only **1 Beacon** is registered, and querying needs a `beacon_query`
tool we haven't built yet (generic `call_service_endpoint` could reach it). Flag as a compelling
roadmap item, not a now-demo.

---

## Recommended demo: a 5-minute arc (hook → payoff)

Combine **#1 (credibility + real findings)** then **#2 (the vision)**, with **#3** as a 30-second
warm-up. Suggested live prompts in **Claude Desktop** (all public, no credentials except where noted):

1. *(warm-up)* "Using the ga4gh tools, what GA4GH service types exist in the registry and how many of
   each?"
2. *(the hook)* "Audit the health of all registered services and summarize: how many are live and
   spec-compliant, and which live services report a version that disagrees with the registry?"
   → expect ~24 live, ~12 version-drifted, mostly Gen3 DRS reporting `1.0.3` vs declared `1.2.0`.
3. *(depth)* "Show me the service-info for the NCI CRDC DRS service and explain the version
   discrepancy."
4. *(the payoff / vision)* "Find a workflow in the Dockstore TRS, then find a live TES service where a
   task like it could run, and walk me through how the pieces connect across the federation."
5. *(honesty flex)* "Which registered services are currently down or require authentication, and why?"
   → shows dead hosts (DNS/TLS/private-IP) and the TESK endpoint returning 403.

The point to make out loud: **none of this required per-service integration**, and the agent never
pretended a broken service was fine.

## Where this could go (bigger stages)

- **Standing public "GA4GH Ecosystem Health" page** regenerated on a schedule (the report from #1 as
  a shareable web artifact) — a lasting community resource, not just a demo.
- **GA4GH AI Workstream reference implementation** — the canonical way agents reach GA4GH services.
- **DNAstack Omics AI integration** — the same pattern against DNAstack's federated networks.

## Honest constraints (so we don't over-promise)

- Real *data access* (DRS bytes, running workflows) is auth-gated; the compelling public demos are
  discovery, resolution, health, and conformance. Access demos need a cooperating endpoint + creds.
- The registry is small and partly aspirational (placeholder/test entries, dead hosts); that's part
  of the honest story, but don't imply it's a huge live network.
- WES/htsget/refget have no live+compliant endpoints today, so avoid centering a demo on them.
- Version "drift" is largely a spec-interpretation nuance; present it precisely.

## Reproduce the numbers

```bash
cd ~/Development/ga4gh-mcp-service && . .venv/bin/activate
python scripts/probe_registry.py          # regenerates the live liveness/compliance snapshot
```
