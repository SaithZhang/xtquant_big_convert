"""Synthetic integration test for the generated entry, also runs on QMT 3.6.

Run in a disposable process, not in the live QMT strategy editor.
No real QMT APIs or financial account are accessed.
"""
import runpy
import sys
import threading
import time

import pandas as pd


def main():
    owner = threading.get_ident()
    calls = []

    def check_thread():
        assert threading.get_ident() == owner, "ContextInfo called outside strategy thread"

    def download(*args, **kwargs):
        check_thread()
        calls.append("download")
        return True

    def forbidden(*args, **kwargs):
        raise AssertionError("Smoke test must never submit or cancel an order")

    class Context:
        def set_account(self, account):
            check_thread()

        def run_time(self, *args):
            check_thread()
            calls.append("timer")

        def get_full_tick(self, codes):
            check_thread()
            return {code: {"lastPrice": 10} for code in codes}

        def get_stock_list_in_sector(self, *args):
            check_thread()
            return ["002463.SZ"]

        def get_market_data_ex(self, fields, stock_code, period, start_time, end_time,
                               count, dividend_type, fill_data=True, subscribe=True):
            check_thread()
            calls.append("bars:" + period)
            return {code: pd.DataFrame({field: [10.0] * count for field in fields},
                                      index=["20260918%06d" % i for i in range(count)])
                    for code in stock_code}

    namespace = runpy.run_path(sys.argv[1], init_globals={
        "download_history_data": download, "passorder": forbidden, "cancel": forbidden,
        "get_trade_detail_data": lambda *args: []})
    runtime = namespace["_runtime"]
    # Synthetic identity: the built private account is never passed to a broker.
    runtime.configure_runtime_account("123456")
    context = Context()
    errors = []
    done = threading.Event()
    namespace["init"](context)
    strategy = runtime._strategy_module
    assert strategy._config["rpc"]["warm_context_data"] is False
    transport_type = type(strategy._rpc_service._transport)

    def request_loop():
        client = transport_type(connect_address="tcp://127.0.0.1:18689", account_id="123456")
        try:
            cases = [("ping", {}, None),
                     ("get_stock_list_in_sector", {"sector_name": "test"}, None),
                     ("get_market_data_ex", {"stock_list": ["002463.SZ"], "period": "1d", "count": 10,
                                              "field_list": ["open", "high", "low", "close", "volume", "amount"]}, 10),
                     ("get_market_data_ex", {"stock_list": ["002463.SZ"], "period": "5m", "count": 20,
                                              "field_list": ["open", "high", "low", "close", "volume", "amount"]}, 20),
                     ("download_history_data", {"stock_code": "002463.SZ", "period": "1d"}, None)]
            for i, (method, params, count) in enumerate(cases):
                response = client.send_request({"schema_version": 1, "request_id": str(i),
                                               "account_id": "123456", "method": method,
                                               "params": params, "timeout_seconds": 2}, 2)
                assert response["ok"], response.get("error")
                if count:
                    assert len(response["data"]["002463.SZ"]["records"]) == count
        except BaseException as exc:
            errors.append(exc)
        finally:
            client.stop()
            done.set()

    worker = threading.Thread(target=request_loop)
    worker.start()
    try:
        deadline = time.monotonic() + 12
        while not done.is_set() and time.monotonic() < deadline:
            namespace["adjust"](context)
            time.sleep(0.01)
        worker.join(3)
        assert done.is_set(), "RPC smoke test timed out"
        if errors:
            raise errors[0]
        assert "bars:1d" in calls and "bars:5m" in calls and "download" in calls
    finally:
        namespace["stop"](context)
    # Verify stop released both listening sockets, so another run can bind.
    import socket
    for port in (18689, 18690):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
    print("SYNTHETIC EMBEDDED SMOKE PASS Python=" + sys.version.split()[0])


if __name__ == "__main__":
    main()
