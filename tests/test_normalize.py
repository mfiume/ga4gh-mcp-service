"""Pure-logic tests for normalization — the empirically-derived compatibility core."""

from __future__ import annotations

from ga4gh_mcp.normalize import (
    api_base_url,
    classify_liveness,
    host_of,
    looks_like_service_info,
    normalize_base_url,
    normalize_environment,
    parse_version,
    parse_www_authenticate,
    service_info_candidates,
)


class TestNormalizeBaseUrl:
    def test_strips_drs_objects_suffix(self):
        assert normalize_base_url("https://data.bloodpac.org/ga4gh/drs/v1/objects/", "drs") == \
            "https://data.bloodpac.org/ga4gh/drs/v1"
        assert normalize_base_url("https://caninedc.org/ga4gh/drs/v1/objects", "drs") == \
            "https://caninedc.org/ga4gh/drs/v1"

    def test_leaves_clean_base(self):
        assert normalize_base_url("https://viral.ai", "drs") == "https://viral.ai"
        assert normalize_base_url("https://viral.ai/", "drs") == "https://viral.ai"

    def test_only_strips_for_matching_artifact(self):
        # /objects is not a TRS collection suffix, so it stays
        assert normalize_base_url("https://x.org/objects", "trs") == "https://x.org/objects"


class TestApiBaseUrl:
    def test_adds_drs_prefix_when_missing(self):
        assert api_base_url("https://data.terra.bio/", "drs") == "https://data.terra.bio/ga4gh/drs/v1"

    def test_keeps_existing_prefix(self):
        assert api_base_url("https://data.bloodpac.org/ga4gh/drs/v1/objects/", "drs") == \
            "https://data.bloodpac.org/ga4gh/drs/v1"

    def test_trs_prefix(self):
        assert api_base_url("https://dockstore.org", "trs") == "https://dockstore.org/ga4gh/trs/v2"

    def test_unknown_artifact_no_prefix(self):
        assert api_base_url("https://x.org", "beacon-unknown") == "https://x.org"


class TestServiceInfoCandidates:
    def test_drs_candidates(self):
        cands = service_info_candidates("https://data.bloodpac.org/ga4gh/drs/v1/objects/", "drs")
        assert cands[0] == "https://data.bloodpac.org/ga4gh/drs/v1/service-info"

    def test_generic_candidate(self):
        cands = service_info_candidates("https://x.org", None)
        assert cands == ["https://x.org/service-info"]

    def test_wes_nested(self):
        cands = service_info_candidates("https://host", "wes")
        assert "https://host/service-info" in cands
        assert "https://host/ga4gh/wes/v1/service-info" in cands


class TestParseVersion:
    def test_semver(self):
        assert parse_version("1.3.0")["tuple"] == (1, 3, 0)

    def test_experimental_suffix(self):
        v = parse_version("1.3.0experimental")
        assert v["tuple"] == (1, 3, 0)
        assert v["suffix"] == "experimental"

    def test_partial(self):
        assert parse_version("2.0")["tuple"] == (2, 0, 0)

    def test_label_only(self):
        v = parse_version("N/A (SaaS)")
        assert v["tuple"] is None
        assert v["label"] == "N/A (SaaS)"

    def test_none(self):
        assert parse_version(None)["tuple"] is None


class TestEnvironment:
    def test_variants(self):
        assert normalize_environment("Production") == "production"
        assert normalize_environment("prod") == "production"
        assert normalize_environment("Development") == "development"
        assert normalize_environment("dev") == "development"
        assert normalize_environment(None) == "unknown"
        assert normalize_environment("demo") == "demo"


class TestLiveness:
    def test_verdicts(self):
        assert classify_liveness(200, None) == "live"
        assert classify_liveness(401, None) == "auth_required"
        assert classify_liveness(403, None) == "auth_required"
        assert classify_liveness(404, None) == "live_no_serviceinfo"
        assert classify_liveness(503, None) == "server_error"
        assert classify_liveness(400, None) == "client_error"
        assert classify_liveness(None, "timeout") == "unreachable"


class TestLooksLikeServiceInfo:
    def test_accepts_real(self):
        assert looks_like_service_info({"id": "x", "name": "y", "type": {}, "version": "1"})
        assert looks_like_service_info({"version": "1.0.0"})
        assert looks_like_service_info({"id": "x", "name": "y"})

    def test_rejects_spa_and_junk(self):
        assert not looks_like_service_info("<html></html>")
        assert not looks_like_service_info(None)
        assert not looks_like_service_info({"random": "payload"})
        assert not looks_like_service_info([1, 2, 3])


class TestWwwAuthenticate:
    def test_parse_bearer(self):
        parsed = parse_www_authenticate('Bearer realm="https://issuer", scope="openid", error="invalid_token"')
        assert parsed["scheme"] == "Bearer"
        assert parsed["params"]["realm"] == "https://issuer"
        assert parsed["params"]["scope"] == "openid"

    def test_empty(self):
        assert parse_www_authenticate(None) == {}


class TestHostOf:
    def test_host(self):
        assert host_of("https://data.terra.bio/ga4gh/drs/v1") == "data.terra.bio"
        assert host_of("http://10.42.28.180:4500") == "10.42.28.180:4500"
