"""Default: upstream ZMQ acceptance. --legacy: original HTTP MVP."""
import json
import math
import sys
import time
from client.bigqmt_client import BigQmtClient, GatewayError


def _data(answer):
    if not answer["ok"]:
        raise GatewayError(answer["error"])
    return answer["data"]


def _bars(data, count):
    frame = data.get("002463.SZ") if isinstance(data, dict) else None
    if not isinstance(frame, dict):
        raise AssertionError("No DataFrame for 002463.SZ; check QMT history/permissions")
    rows, columns, index = frame.get("data", []), frame.get("columns", []), frame.get("index", [])
    if len(rows) != count or len(index) != count:
        raise AssertionError("Expected %d bars, got %d; download QMT history then re-run" % (count, len(rows)))
    if len(set(str(v) for v in index)) != count or any(v is None or str(v) == "" for v in index):
        raise AssertionError("Missing or duplicate QMT timestamps")
    if [str(v) for v in index] != sorted(str(v) for v in index):
        raise AssertionError("QMT timestamps are not chronological")
    for field in ("open", "high", "low", "close", "volume", "amount"):
        if field not in columns:
            raise AssertionError("Missing field: " + field)
        for row in rows:
            value = row[columns.index(field)]
            if (not isinstance(value, (int, float)) or isinstance(value, bool)
                    or not math.isfinite(value) or value < 0 or (field in ("open", "high", "low", "close") and value == 0)):
                raise AssertionError("Missing/invalid numeric field: " + field)
    for row in rows:
        o, h, low, c = [row[columns.index(f)] for f in ("open", "high", "low", "close")]
        if not low <= min(o, c) <= max(o, c) <= h:
            raise AssertionError("Inconsistent OHLC values")
    print("  native time range: %s -> %s (QMT timestamps; freshness not inferred)" % (index[0], index[-1]))
    print("  last bar: " + json.dumps(dict(zip(columns, rows[-1])), ensure_ascii=False))


def live_test():
    client = BigQmtClient()
    total = time.perf_counter()
    failures = []

    def check(label, func, validate):
        start = time.perf_counter()
        try:
            data = _data(func())
            validate(data)
            print("PASS %-28s %.3fs" % (label, time.perf_counter() - start))
            return True
        except Exception as exc:
            failures.append(label)
            print("FAIL %-28s %.3fs: %s" % (label, time.perf_counter() - start, exc))
            return False

    def ping(data):
        if data.get("service") != "BigQmtGateway" or data.get("trade_authority") != "none":
            raise AssertionError("Wrong service or trade authority")

    def capabilities(data):
        print(json.dumps(data, ensure_ascii=False, indent=2))
        for method in ("get_market_data_ex", "get_stock_list_in_sector"):
            if not data["methods"][method]["available"]:
                raise AssertionError("Required API unsupported: " + method)

    def sector(data):
        if not isinstance(data, list) or "002463.SZ" not in data:
            raise AssertionError("Sector empty/invalid or 002463.SZ missing")
        print("  sector members: %d" % len(data))

    print("REAL QMT acceptance (no mock data, no automatic downloads)")
    if not check("ping", client.ping, ping):
        print("Run BIGQMT_GATEWAY in the QMT strategy editor; native Python must be OFF.")
        print("TOTAL %.3fs; LIVE MVP NOT VERIFIED" % (time.perf_counter() - total))
        return 1
    check("capabilities", client.capabilities, capabilities)
    check("sector: HS A shares", lambda: client.get_stock_list_in_sector("沪深A股"), sector)
    check("002463.SZ 1d x 10", lambda: client.get_market_data_ex(["002463.SZ"], "1d", 10), lambda d: _bars(d, 10))
    check("002463.SZ 5m x 20", lambda: client.get_market_data_ex(["002463.SZ"], "5m", 20), lambda d: _bars(d, 20))
    print("TOTAL %.3fs; %s" % (time.perf_counter() - total, "LIVE MVP PASS" if not failures else "LIVE MVP NOT VERIFIED"))
    return 1 if failures else 0


def self_test():
    import ast
    import importlib.util
    from pathlib import Path
    import queue
    import socket
    import threading
    import unittest

    source = Path(__file__).parent / "qmt" / "BIGQMT_GATEWAY.py"
    spec = importlib.util.spec_from_file_location("gateway_under_test", str(source))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class Frame:
        columns = ["close"]

        def to_dict(self, orient):
            assert orient == "split"
            return {"index": ["20260918000000"], "columns": self.columns, "data": [[float("nan")]]}

    class Context:
        def __init__(self):
            self.thread = threading.get_ident()
            self.calls = []

        def get_market_data_ex(self, *args):
            assert threading.get_ident() == self.thread, "QMT API called from a network thread"
            self.calls.append(args)
            return {"002463.SZ": Frame()}

        def get_stock_list_in_sector(self, name):
            assert threading.get_ident() == self.thread, "wrong thread"
            return ["002463.SZ"] if name == "沪深A股" else []

        def run_time(self, *args):
            self.timer = args

    class Tests(unittest.TestCase):
        def setUp(self):
            self.context = Context()
            self.gateway = module._Gateway(self.context, {}, port=0)
            self.gateway.thread.start()
            self.client = BigQmtClient(self.gateway.server.server_address[1])

        def tearDown(self):
            self.gateway.close()

        def rpc(self, method, params=None):
            result = queue.Queue()

            def request():
                try:
                    result.put(self.client.call(method, params))
                except Exception as exc:
                    result.put(exc)

            worker = threading.Thread(target=request)
            worker.start()
            deadline = time.monotonic() + 4
            while worker.is_alive() and time.monotonic() < deadline:
                self.gateway.drain()  # Simulated QMT callback on THIS thread.
                worker.join(0.005)
            self.assertFalse(worker.is_alive())
            answer = result.get_nowait()
            if isinstance(answer, Exception):
                raise answer
            return answer

        def test_callback_thread_and_native_signature(self):
            self.assertTrue(self.rpc("ping")["ok"])
            answer = self.rpc("get_market_data_ex", {"stock_list": ["002463.SZ"], "period": "5m", "count": 20})
            self.assertIsNone(answer["data"]["002463.SZ"]["data"][0][0])
            args = self.context.calls[0]
            self.assertEqual(args[1:], (["002463.SZ"], "5m", "", "", 20, "none", False, True))
            self.assertEqual(self.rpc("get_stock_list_in_sector", {"sector_name": "沪深A股"})["data"], ["002463.SZ"])

        def test_no_account_or_trading_surface(self):
            for method in ("passorder", "cancel", "get_trade_detail_data", "get_positions", "get_asset", "eval", "__dict__"):
                answer = self.rpc(method)
                self.assertFalse(answer["ok"])
                self.assertIn("unsupported", answer["error"])
            self.assertEqual(self.context.calls, [])
            tree = ast.parse(source.read_text("ascii"))
            forbidden = {"passorder", "cancel", "get_trade_detail_data", "set_account", "eval", "exec", "xtdata", "xttrader"}
            self.assertFalse({n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} & forbidden)

        def test_capabilities_do_not_invent_downloads(self):
            caps = self.rpc("capabilities")["data"]
            self.assertEqual(caps["periods_with_data_this_session"], [])
            for method in ("download_history_data", "download_history_data2"):
                self.assertFalse(caps["methods"][method]["available"])
                self.assertIn("unsupported", self.rpc(method)["error"])

        def test_explicit_download_binding_without_batch_emulation(self):
            calls = []
            def download(*args):
                self.assertEqual(threading.get_ident(), self.context.thread)
                calls.append(args)
            other = module._Gateway(self.context, {"down_history_data": download}, port=0)
            try:
                self.assertEqual(other.sources["download_history_data"], "injected.down_history_data")
                result = other.dispatch("download_history_data", {"stock_code": "002463.SZ", "period": "1d"})
                self.assertIsNone(result["native_result"])
                self.assertNotIn("download_history_data2", other.calls)
                self.assertEqual(calls, [("002463.SZ", "1d", "", "")])
            finally:
                other.close()

        def test_native_batch_and_errors_remain_visible(self):
            def batch(*args):
                self.assertEqual(threading.get_ident(), self.context.thread)
                self.assertEqual(args, (["002463.SZ"], "5m", "", ""))
                return None
            other = module._Gateway(self.context, {"download_history_data2": batch}, port=0)
            try:
                self.assertIsNone(other.dispatch("download_history_data2", {"stock_list": ["002463.SZ"], "period": "5m"})["native_result"])
            finally:
                other.close()
            def broken(*args):
                raise RuntimeError("native market data unavailable")
            self.gateway.calls["get_market_data_ex"] = broken
            answer = self.rpc("get_market_data_ex", {"stock_list": ["002463.SZ"]})
            self.assertFalse(answer["ok"])
            self.assertIn("native market data unavailable", answer["error"])
            self.assertTrue(self.rpc("health")["ok"])

        def test_http_rejects_browser_origin_and_invalid_json(self):
            import http.client
            for body, headers in ((b'{', {}), (b'{}', {"Origin": "https://example.invalid"})):
                conn = http.client.HTTPConnection("127.0.0.1", self.client.port, timeout=1)
                try:
                    conn.request("POST", "/rpc", body, dict(headers, **{"Content-Type": "application/json"}))
                    answer = json.loads(conn.getresponse().read().decode("utf-8"))
                    self.assertFalse(answer["ok"])
                finally:
                    conn.close()
            self.assertEqual(self.context.calls, [])

        def test_bad_params_and_expired_jobs_never_reach_qmt(self):
            for params in ({"stock_list": []}, {"stock_list": ["002463.SZ"], "count": True},
                           {"stock_list": ["002463.SZ"], "account": "forbidden"}):
                self.assertFalse(self.rpc("get_market_data_ex", params)["ok"])
            self.gateway.pending.put({"deadline": 0, "method": "get_market_data_ex", "params": {}})
            self.gateway.drain()
            self.assertEqual(self.context.calls, [])

        def test_stalled_callbacks_fail_quickly(self):
            start = time.monotonic()
            answer = self.client.ping()  # Deliberately do NOT drain.
            self.assertFalse(answer["ok"])
            self.assertIn("callback timeout", answer["error"])
            self.assertLess(time.monotonic() - start, 3)

        def test_lifecycle_and_port_release(self):
            old_port = module.PORT
            module.PORT = 0
            try:
                module.init(self.context)
                port = module._gateway.server.server_address[1]
                self.assertEqual(self.context.timer[:2], ("adjust", "200nMilliSecond"))
                module.handlebar(self.context)
                module.stop(self.context)
                with socket.socket() as probe:
                    probe.bind(("127.0.0.1", port))
            finally:
                module.stop(self.context)
                module.PORT = old_port

        def test_unstarted_service_fails_quickly(self):
            with socket.socket() as blocker:
                blocker.bind(("127.0.0.1", 0))
                client = BigQmtClient(blocker.getsockname()[1])
                start = time.monotonic()
                with self.assertRaisesRegex(GatewayError, "Big QMT Gateway is not running"):
                    client.ping()
                self.assertLess(time.monotonic() - start, 2)

        def test_failed_timer_and_backtest_do_not_leave_a_server(self):
            old_port = module.PORT
            module.PORT = 0
            def broken_timer(*args):
                raise RuntimeError("timer unavailable")
            self.context.run_time = broken_timer
            try:
                with self.assertRaisesRegex(RuntimeError, "timer unavailable"):
                    module.init(self.context)
                self.assertIsNone(module._gateway)
                self.context.do_back_test = True
                with self.assertRaisesRegex(RuntimeError, "Backtest is unsupported"):
                    module.init(self.context)
                self.assertIsNone(module._gateway)
            finally:
                module.PORT = old_port

    print("OFFLINE SELF-TEST: synthetic ContextInfo; does NOT prove real QMT market data")
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        sys.exit(self_test())
    if sys.argv[1:] == ["--legacy"]:
        sys.exit(live_test())
    if sys.argv[1:]:
        print("Usage: python test_gateway.py [--legacy | --self-test]")
        sys.exit(2)
    # Prefer the isolated SDK environment without changing the user's Python.
    from pathlib import Path
    import subprocess
    python = Path(__file__).parent / ".venv" / "Scripts" / "python.exe"
    if python.exists() and Path(sys.executable).resolve() != python.resolve():
        sys.exit(subprocess.call([str(python), str(Path(__file__).resolve())]))
    try:
        from extensions.galaxy_sim.test_live import main
        sys.exit(main())
    except (ImportError, FileNotFoundError) as exc:
        print("Galaxy setup incomplete: %s; see FORK.md" % exc)
        sys.exit(1)
