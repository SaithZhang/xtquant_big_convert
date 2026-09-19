import json
from pathlib import Path
import pytest
from . import redis_package as package


def test_public_loopback_and_documentation_addresses_are_not_lan():
    import ipaddress
    for host in ("127.0.0.1", "0.0.0.0", "8.8.8.8", "192.0.2.1", "::1"):
        assert not package.trusted_address(ipaddress.ip_address(host))
    assert package.trusted_address(ipaddress.ip_address("192.168.1.5"))


def test_deploy_refuses_dirty_source(tmp_path):
    with pytest.raises(ValueError, match="Commit"):
        package.deploy(tmp_path, {"source_dirty": True})


def test_deploy_preflights_all_collisions(tmp_path, monkeypatch):
    qmt = tmp_path / "qmt" / "python"
    qmt.mkdir(parents=True)
    (qmt / "_PyContextInfo.py").write_text("vendor")
    (qmt / "second.py").write_text("user content")
    stage = tmp_path / "stage"
    stage.mkdir()
    for name in ("first.py", "second.py"):
        (stage / name).write_text("new")
    monkeypatch.setattr(package, "STAGE", stage)
    manifest = {"source_dirty": False, "files": {n: package.digest(stage / n) for n in ("first.py", "second.py")}}
    with pytest.raises(ValueError, match="not owned"):
        package.deploy(qmt.parent, manifest)
    assert not (qmt / "first.py").exists()
    assert (qmt / "second.py").read_text() == "user content"


def test_generated_config_disables_orders_and_bypasses(tmp_path, monkeypatch):
    monkeypatch.setattr(package, "PRIVATE", tmp_path / "private")
    monkeypatch.setattr(package, "STAGE", tmp_path / "stage")
    monkeypatch.setattr(package, "load_profile", lambda: {"account_id": "123456"})
    settings, account = package.generate("192.168.1.5")
    manifest = package.build(settings, account)
    local = {}
    exec((package.STAGE / "bigqmt_signal_trader_local_config.py").read_text(), local)
    config = local["BIGQMT_REDIS_CONFIG"]
    assert config["rpc_allow_order_methods"] is False
    assert config["rpc_process_in_listener"] is False
    assert config["transport"] == "redis"
    original = (package.ROOT / "src/BIGQMT_REDIS_DRYRUN.py").read_bytes()
    assert (package.STAGE / "BIGQMT_REDIS_DRYRUN.py").read_bytes() == original
    assert (package.STAGE / "BIGQMT_GALAXY_REDIS.py").read_bytes().startswith(original)
    assert all(package.digest(package.STAGE / name) == value for name, value in manifest["files"].items())
    second, _ = package.generate()
    assert second["password"] == settings["password"]
