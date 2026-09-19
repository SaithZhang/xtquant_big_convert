"""Local Galaxy profile; the bridge and SDK remain upstream implementations."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT / ".local" / "galaxy_sim.json"
RPC_ADDRESS = "tcp://127.0.0.1:18689"
PUSH_ADDRESS = "tcp://127.0.0.1:18690"


def load_profile(path=PROFILE):
    profile = json.loads(Path(path).read_text(encoding="utf-8"))
    if set(profile) != {"account_id", "account_type", "simulation", "allow_order_methods"}:
        raise ValueError("Profile must contain only the four documented fields; no passwords")
    if profile["simulation"] is not True or profile["account_type"] != "STOCK":
        raise ValueError("This deployment profile is for a STOCK simulation client")
    if not isinstance(profile["account_id"], str) or not profile["account_id"].isascii() or not profile["account_id"].isdigit():
        raise ValueError("Use the numeric account ID from QMT account management")
    if type(profile["allow_order_methods"]) is not bool:
        raise ValueError("allow_order_methods must be a boolean")
    return profile


def runtime_config(profile):
    return {
        "transport": "zmq", "redis_enabled": False,
        "rpc_allow_order_methods": profile["allow_order_methods"],
        "rpc_default_strategy_name": "galaxy_sim",
        "rpc_background_threads": False, "rpc_process_in_listener": False,
        "rpc_listener_methods": (), "schedule_adjust": True,
        "schedule_adjust_interval": "100nMilliSecond",
        "full_tick_cache_enabled": False, "download_jobs_enabled": False,
        "exec_events_enabled": True, "exec_events_debug_raw_fields": False,
        "zmq": {"bind_address": RPC_ADDRESS, "connect_address": RPC_ADDRESS,
                "redis_discovery_enabled": False},
        "quote_push": {"enabled": True, "zmq_bind_address": PUSH_ADDRESS},
    }


def create_client(profile=None):
    from bigqmt_signal_trader.xtquant_compat import BigQmtRpcClient
    profile = profile or load_profile()
    return BigQmtRpcClient(
        account_id=profile["account_id"], transport="zmq", timeout_seconds=5,
        redis_config={"zmq": {"connect_address": RPC_ADDRESS,
                              "redis_discovery_enabled": False},
                      "formula_server": {"enabled": False},
                      "local_cache_enabled": False, "full_tick_cache_enabled": False})
