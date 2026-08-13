from backend.redact import redact_payload


def test_redact_serial():
    out = redact_payload({"data": {"serial": "ABC123456789"}})
    assert out["data"]["serial"] == "****6789"


def test_redact_raw_os_release():
    out = redact_payload({"data": {"raw_os_release": {"ID": "pop", "VERSION_ID": "22"}}})
    assert out["data"]["raw_os_release"] == {"redacted": True}


def test_redact_nested_in_results():
    payload = {
        "ok": True,
        "resource": "bundle",
        "results": [{"data": {"uuid": "1111-2222-3333-4444"}}],
    }
    out = redact_payload(payload)
    assert out["results"][0]["data"]["uuid"].startswith("****")


def test_redact_sku_and_asset_tag():
    out = redact_payload(
        {"data": {"sku": "ABCDE12345", "asset_tag": "TAG-9999", "part_number": "HMAA1G"}}
    )
    assert out["data"]["sku"] == "****2345"
    assert out["data"]["asset_tag"] == "****9999"
    assert out["data"]["part_number"] == "****AA1G"
