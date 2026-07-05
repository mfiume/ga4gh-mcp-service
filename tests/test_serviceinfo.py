"""Service-info shape detection + version reconciliation (the compliance-tolerance core)."""

from __future__ import annotations

from ga4gh_mcp.serviceinfo import analyze_service_info, normalize_version


def test_normalize_version_variants():
    assert normalize_version("1.0") == (1, 0)
    assert normalize_version("v2.0.0") == (2, 0, 0)
    assert normalize_version("1.3.0-beta") == (1, 3, 0)
    assert normalize_version(None) is None
    assert normalize_version("garbage") is None


def test_compliant_ga4gh_matching_versions():
    payload = {
        "id": "org.example.drs", "name": "Example DRS",
        "type": {"group": "org.ga4gh", "artifact": "drs", "version": "1.3.0"},
        "version": "1.3.0",
        "organization": {"name": "Example", "url": "https://example.org"},
    }
    a = analyze_service_info(payload, declared_product="DRS", declared_version="1.3.0")
    assert a.shape == "ga4gh"
    assert a.compliant is True
    assert a.version.product_matches is True
    assert a.version.version_matches is True
    assert a.missing_required == []


def test_gen3_type_version_is_schema_not_spec_version():
    # Gen3 reports type.version 1.0.3 (service-info schema) while declared spec is 1.2.0.
    payload = {
        "id": "indexd-deployment-xyz", "name": "DRS System",
        "type": {"group": "org.ga4gh", "artifact": "drs", "version": "1.0.3"},
        "version": "1.0.3",
        "organization": {"name": "Gen3", "url": "https://gen3.org"},
    }
    a = analyze_service_info(payload, declared_product="DRS", declared_version="1.2.0")
    assert a.compliant is True  # it IS a valid service-info
    assert a.version.product_matches is True
    assert a.version.version_matches is False  # discrepancy surfaced, not crashed
    assert any("version discrepancy" in w for w in a.warnings)


def test_terra_jade_nonstandard_falls_back():
    payload = {"version": "0.0.1", "title": "Terra Data Repository",
               "description": "Jade", "contact": "x@y.z", "license": "Apache 2.0"}
    a = analyze_service_info(payload, declared_product="DRS", declared_version="1.3.0")
    assert a.shape == "nonstandard"
    assert a.compliant is False
    assert "id" in a.missing_required and "type" in a.missing_required
    assert a.name == "Terra Data Repository"  # mapped from title
    assert any("NOT a spec-compliant" in w for w in a.warnings)


def test_beacon_info_shape():
    payload = {"meta": {"beaconId": "org.example.beacon", "apiVersion": "v2.0.0"},
               "response": {"id": "beacon", "name": "Example Beacon",
                            "organization": {"name": "Org"}}}
    a = analyze_service_info(payload, declared_product="Beacon", declared_version="v2.0.0")
    assert a.shape == "beacon"
    assert a.name == "Example Beacon"
    assert a.version.reported_artifact == "beacon"
    assert a.version.product_matches is True


def test_tesk_short_version_normalizes_to_match():
    payload = {"id": "tes", "name": "TESK", "type": {"artifact": "tes", "version": "1.0"},
               "version": "1.0", "organization": {"name": "ELIXIR", "url": "https://elixir.org"}}
    a = analyze_service_info(payload, declared_product="TES", declared_version="1.0.0")
    assert a.version.version_matches is True  # "1.0" == "1.0.0" after normalization


def test_product_mismatch_flagged():
    payload = {"id": "x", "name": "y", "type": {"artifact": "trs", "version": "2.0.0"},
               "version": "2.0.0", "organization": {"name": "o", "url": "https://o"}}
    a = analyze_service_info(payload, declared_product="DRS", declared_version="1.2.0")
    assert a.version.product_matches is False
    assert any("product mismatch" in w for w in a.warnings)


def test_non_dict_payload_does_not_crash():
    a = analyze_service_info("<html>error</html>", declared_product="DRS", declared_version="1.0.0")
    assert a.shape == "unknown"
    assert a.compliant is False
