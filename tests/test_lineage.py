from codelineage.lineage import build_repository_mapping, mapping_from_migration_report


def test_mapping_from_report():
    report = {
        "schema_version": 1,
        "batch_id": "b1",
        "source": "Owner/Repo",
        "destination": "WatchCodes/nastech-repo",
        "sha": "a" * 40,
        "status": "VERIFIED",
        "license": "MIT",
        "generated_at": "2026-11-22T00:00:00Z",
    }
    m = mapping_from_migration_report(report)
    assert m["source"] == "Owner/Repo"
    assert m["destination"] == "WatchCodes/nastech-repo"
