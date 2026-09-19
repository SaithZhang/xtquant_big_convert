import json

import pytest

from .build import configure_shell
from .config import load_profile, runtime_config


PROFILE = {"account_id": "123456", "account_type": "STOCK",
           "simulation": True, "allow_order_methods": True}


def test_private_config_rejects_password_and_login_label(tmp_path):
    path = tmp_path / "profile.json"
    for changes in ({"password": "do-not-store"}, {"account_id": "public test"},
                    {"simulation": False}, {"allow_order_methods": "false"}):
        path.write_text(json.dumps(dict(PROFILE, **changes)), encoding="utf-8")
        with pytest.raises(ValueError):
            load_profile(path)


def test_config_patch_does_not_touch_embedded_source():
    embedded = 'def module():\n    BIGQMT_ACCOUNT_ID = "embedded"\n'
    source = ('BIGQMT_ACCOUNT_ID = "template"\nBIGQMT_ACCOUNT_TYPE = "STOCK"\n'
              'BIGQMT_REDIS_CONFIG = {}\n' + embedded)
    result = configure_shell(source, PROFILE)
    assert result.endswith(embedded)
    namespace = {}
    exec(result, namespace)
    assert namespace["BIGQMT_ACCOUNT_ID"] == "123456"
    with pytest.raises(RuntimeError):
        configure_shell(source.replace("BIGQMT_REDIS_CONFIG", "RENAMED"), PROFILE)


def test_loopback_and_qmt_callback_routing():
    config = runtime_config(PROFILE)
    assert config["rpc_allow_order_methods"] is True
    assert config["rpc_background_threads"] is False
    assert config["rpc_process_in_listener"] is False
    assert config["redis_enabled"] is False
    for endpoint in (config["zmq"]["bind_address"], config["zmq"]["connect_address"],
                     config["quote_push"]["zmq_bind_address"]):
        assert endpoint.startswith("tcp://127.0.0.1:")


def test_acceptance_only_sends_reads_and_disables_download_probe(monkeypatch):
    from . import test_live
    calls = []

    class Client:
        _transport_instance = None

        def call(self, method, params, **kwargs):
            calls.append(method)
            assert kwargs["use_formula"] is False
            if method == "ping":
                return {"allow_order_methods": True}
            if method == "probe_capabilities":
                assert params == {"download_probe": False}
                return {"contextinfo_methods": {"get_market_data_ex": True,
                                                 "get_stock_list_in_sector": True}}
            if method == "get_stock_list_in_sector":
                return ["002463.SZ"]
            assert method == "get_market_data_ex"
            columns = ["stime", "open", "high", "low", "close", "volume", "amount"]
            return {"002463.SZ": {"columns": columns,
                                   "records": [["20260918%06d" % i] + [10] * 6
                                               for i in range(params["count"])]}}

    monkeypatch.setattr(test_live, "create_client", Client)
    monkeypatch.setattr(test_live, "load_profile", lambda: PROFILE)
    assert test_live.main() == 0
    assert calls == ["ping", "probe_capabilities", "get_stock_list_in_sector",
                     "get_market_data_ex", "get_market_data_ex"]
