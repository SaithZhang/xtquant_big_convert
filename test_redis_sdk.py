"""Portable, read-only SDK acceptance. No order, download or sector writes."""
import argparse
import importlib
import json
import os
from pathlib import Path
import sys
import threading
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-dir", default=str(Path(__file__).parent / ".local/redis-lan/windows"))
    parser.add_argument("--market-only", action="store_true")
    parser.add_argument("--seconds", type=float, default=6)
    parser.add_argument("--report")
    args = parser.parse_args()
    sys.path.insert(0, str(Path(args.config_dir).resolve()))
    os.environ["BIGQMT_CLIENT_CONFIG_MODULE"] = "bigqmt_signal_trader_client_config"
    os.environ["BIGQMT_FORMULA_ENABLED"] = "0"
    config = importlib.import_module("bigqmt_signal_trader_client_config")
    import redis
    from redis.backoff import NoBackoff
    from redis.retry import Retry
    from bigqmt_signal_trader.xtquant_compat import configure, xtdata, xt_trader
    configure()
    results = []

    def check(name, action):
        start = time.monotonic()
        try:
            detail = action()
            result = dict(name=name, status="PASS", detail=detail)
        except Exception as error:
            # Error strings can contain account ids/Redis URLs. Keep evidence private
            # and the shareable report limited to class names.
            result = dict(name=name, status="FAIL", error=type(error).__name__)
        result["seconds"] = round(time.monotonic() - start, 3)
        results.append(result)
        print(json.dumps(result, ensure_ascii=True))
        return result["status"] == "PASS"

    def connection():
        c = config.BIGQMT_REDIS_CONFIG
        client = redis.Redis(**{k: c[k] for k in ("host", "port", "db", "password")},
                             socket_connect_timeout=2, socket_timeout=2,
                             retry=Retry(NoBackoff(), 0))
        try:
            assert client.ping() is True
        finally:
            client.close()
        return "authenticated"

    def ping():
        response = xtdata.client.call("ping", {}, timeout_seconds=1.5, use_formula=False)
        assert response
        return "RPC responded"

    if not check("redis_network", connection) or not check("ping", ping):
        print("Big QMT Gateway is not running (or Redis/configuration is unavailable)")
        return 1

    def deployment():
        info = xtdata.get_deployment_info()
        assert info.get("version") and info.get("package_dir")
        # Do not publish private filesystem paths.
        return {k: info.get(k) for k in ("version", "python_version", "rpc_revision")}

    def tick():
        data = xtdata.get_full_tick(["000001.SZ"])
        item = data["000001.SZ"]
        assert isinstance(item, dict) and item.get("lastPrice", 0) > 0
        assert len(item.get("bidPrice", [])) >= 5 and len(item.get("askPrice", [])) >= 5
        return {"timestamp": item.get("time"), "levels": 5}

    def bars(period):
        data = xtdata.get_market_data_ex(field_list=["open", "high", "low", "close", "volume"],
                 stock_list=["000001.SZ"], period=period, count=10, heal=False)
        frame = data["000001.SZ"]
        assert len(frame) == 10 and frame.index.is_unique
        assert (frame["close"] > 0).all()
        assert (frame["high"] >= frame["low"]).all()
        return {"rows": len(frame), "last": str(frame.index[-1])}

    check("get_deployment_info", deployment)
    check("get_full_tick", tick)
    for period in ("1d", "5m", "15m", "60m"):
        check("bars_" + period, lambda p=period: bars(p))

    def sector():
        stocks = xtdata.get_stock_list_in_sector("\u6caa\u6df1A\u80a1")
        assert "000001.SZ" in stocks and len(stocks) > 1000
        return {"count": len(stocks)}

    check("sector", sector)
    if not args.market_only:
        def asset():
            value = xt_trader.query_stock_asset(config.BIGQMT_ACCOUNT_ID)
            cash = getattr(value, "cash", None)
            total = getattr(value, "total_asset", None)
            return {"content": "UNKNOWN" if cash is None or total is None else "PRESENT"}

        def positions():
            value = xt_trader.query_stock_positions(config.BIGQMT_ACCOUNT_ID)
            assert isinstance(value, list)
            return {"content": "EMPTY_NOT_PROOF_OF_NO_HOLDINGS" if not value else "PRESENT"}

        check("account", asset)
        check("positions", positions)

    def subscription():
        callbacks = []
        caller = threading.get_ident()
        def receive(data):
            if data and "000001.SZ" in data:
                callbacks.append(threading.get_ident() != caller)
        seq = xtdata.subscribe_whole_quote(["000001.SZ"], callback=receive)
        try:
            assert isinstance(seq, int) and seq > 0
            time.sleep(max(0, min(args.seconds, 60)))
            status = xtdata.quote_subscription_status()
            return {"registered": True, "initial_snapshot_callbacks": callbacks.count(False),
                    "background_callbacks": callbacks.count(True),
                    "stream": "RECEIVED" if any(callbacks) else "PENDING_TRADING_SESSION",
                    "status_available": bool(status)}
        finally:
            try:
                xtdata.unsubscribe_quote(seq)
            finally:
                xtdata.stop_all_subscriptions()

    check("subscribe_whole_quote", subscription)
    if args.report:
        Path(args.report).write_text(json.dumps(results, indent=2), encoding="utf-8")
    return int(any(r["status"] != "PASS" for r in results))


if __name__ == "__main__":
    raise SystemExit(main())
