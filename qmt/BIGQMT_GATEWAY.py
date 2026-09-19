# coding:gbk
# BIGQMT_GATEWAY_OWNED_V1 - standalone, ASCII-only QMT strategy source.
"""Load in Big QMT model trading; normal Python execution starts no server."""
import datetime
import json
import math
import queue
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

HOST, PORT = "127.0.0.1", 18688
PERIODS = ("1d", "1m", "5m", "15m", "60m")
METHODS = ("ping", "health", "capabilities", "get_market_data_ex",
           "get_stock_list_in_sector", "download_history_data", "download_history_data2")
_gateway = globals().get("_gateway")


def _reply(data=None, error=None):
    return {"ok": error is None, "data": data if error is None else None, "error": error}


def _plain(value):
    """Preserve DataFrame axes; missing/non-finite values become JSON null."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if type(value).__name__ in ("NaTType", "NAType"):
        return None
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if hasattr(value, "columns") and hasattr(value, "to_dict"):
        return _plain(value.to_dict(orient="split"))
    if hasattr(value, "tolist"):
        return _plain(value.tolist())
    if hasattr(value, "item"):
        return _plain(value.item())
    return str(value)


def _strings(value, name, maximum=50):
    if (not isinstance(value, list) or not 1 <= len(value) <= maximum
            or any(not isinstance(v, str) or not v or len(v) > 100 for v in value)):
        raise ValueError("%s must be a non-empty list of at most %d strings" % (name, maximum))
    return value


def _check_params(params, allowed):
    extra = set(params) - set(allowed)
    if extra:
        raise ValueError("unknown parameters: %s" % ", ".join(sorted(extra)))


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def setup(self):
        self.request.settimeout(2.0)
        BaseHTTPRequestHandler.setup(self)

    def _send(self, answer, status=200):
        body = json.dumps(answer, ensure_ascii=True, allow_nan=False).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
        except OSError:
            pass  # Client deadline may precede completion of a native QMT call.

    def do_GET(self):
        self._send(_reply(error="use POST /rpc with JSON"), 405)

    def do_POST(self):
        try:
            if self.path != "/rpc":
                raise ValueError("use POST /rpc")
            expected = "127.0.0.1:%d" % self.server.server_address[1]
            if self.headers.get("Host") != expected or self.headers.get("Origin"):
                raise ValueError("only local non-browser RPC clients are accepted")
            if self.headers.get_content_type() != "application/json":
                raise ValueError("Content-Type must be application/json")
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 65536 or self.headers.get("Transfer-Encoding"):
                raise ValueError("request body must be 1..65536 bytes, without chunking")
            request = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(request, dict) or set(request) - {"method", "params"}:
                raise ValueError("expected {method, params}")
            method, params = request.get("method"), request.get("params", {})
            if method not in METHODS:
                raise ValueError("unsupported method: %s" % method)
            if not isinstance(params, dict):
                raise ValueError("params must be an object")
            wait = 2.0 if method in ("ping", "health") else 8.0
            job = {"method": method, "params": params, "done": threading.Event(),
                   "deadline": time.monotonic() + wait, "answer": None}
            gateway = self.server.gateway
            if gateway.closed.is_set():
                raise RuntimeError("Big QMT Gateway is not running")
            gateway.pending.put_nowait(job)
            if not job["done"].wait(wait):
                job["deadline"] = 0  # Do not execute an expired queued download.
                raise RuntimeError("QMT callback timeout; check model trading and adjust timer")
            self._send(job["answer"])
        except Exception as exc:
            self._send(_reply(error="%s: %s" % (type(exc).__name__, exc)))


class _Gateway:
    def __init__(self, context, injected, port=PORT):
        self.pending = queue.Queue(maxsize=16)
        self.closed = threading.Event()
        self.drain_lock = threading.Lock()
        self.started = time.monotonic()
        self.observed_periods = set()
        self.callback_seen = False
        self.calls, self.sources = {}, {}
        for name in METHODS[3:]:
            candidates = [("ContextInfo." + name, getattr(context, name, None))]
            if name.startswith("download_"):
                candidates.insert(0, ("injected." + name, injected.get(name)))
                if name == "download_history_data":
                    candidates.append(("injected.down_history_data", injected.get("down_history_data")))
            for source, func in candidates:
                if callable(func):
                    self.calls[name], self.sources[name] = func, source
                    break
        self.server = HTTPServer((HOST, port), _Handler)
        self.server.gateway = self
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={"poll_interval": 0.1}, name="BigQmtHTTP")
        self.thread.daemon = True

    def dispatch(self, method, p):
        if method in ("ping", "health", "capabilities"):
            _check_params(p, ())
            data = {"service": "BigQmtGateway", "version": "0.1.0",
                    "python": sys.version.split()[0], "trade_authority": "none",
                    "execution": "QMT callback", "uptime_seconds": round(time.monotonic() - self.started, 3)}
            if method == "capabilities":
                data.update({"methods": {n: {"available": n in METHODS[:3] or n in self.calls,
                            "source": "gateway" if n in METHODS[:3] else self.sources.get(n),
                            "status": "available" if n in METHODS[:3] else
                            ("exposed_unverified" if n in self.calls else "unsupported")}
                            for n in METHODS},
                             "accepted_periods": list(PERIODS),
                             "periods_with_data_this_session": sorted(self.observed_periods),
                             "period_note": "native passthrough only; availability requires real data",
                             "default_fill_data": False, "default_subscribe": True})
            return data
        if method not in self.calls:
            raise NotImplementedError("unsupported: %s is not exposed by this QMT strategy" % method)
        func = self.calls[method]
        if method == "get_stock_list_in_sector":
            _check_params(p, ("sector_name",))
            name = p.get("sector_name")
            if not isinstance(name, str) or not name or len(name) > 100:
                raise ValueError("sector_name must be a non-empty string")
            return func(name)
        period = p.get("period", "1d")
        if period not in PERIODS:
            raise ValueError("unsupported period: %s" % period)
        for key in ("start_time", "end_time"):
            value = p.get(key, "")
            if not isinstance(value, str) or (value and (len(value) not in (8, 14) or not value.isdigit())):
                raise ValueError("%s must be empty, YYYYMMDD or YYYYMMDDhhmmss" % key)
        if method == "get_market_data_ex":
            _check_params(p, ("stock_list", "fields", "period", "start_time", "end_time",
                              "count", "dividend_type", "fill_data", "subscribe"))
            stocks = _strings(p.get("stock_list"), "stock_list")
            fields = p.get("fields", ["open", "high", "low", "close", "volume", "amount"])
            _strings(fields, "fields", 32)
            count = p.get("count", 10)
            if type(count) is not int or not 1 <= count <= 2000:
                raise ValueError("count must be 1..2000")
            for key in ("fill_data", "subscribe"):
                if key in p and type(p[key]) is not bool:
                    raise ValueError("%s must be boolean" % key)
            dividend = p.get("dividend_type", "none")
            if dividend not in ("none", "front", "back", "front_ratio", "back_ratio"):
                raise ValueError("unsupported dividend_type")
            # Exact positional signature from this installation's _PyContextInfo.py.
            result = func(fields, stocks, period, p.get("start_time", ""),
                          p.get("end_time", ""), count, dividend,
                          p.get("fill_data", False), p.get("subscribe", True))
            answer = _plain(result)
            if isinstance(answer, dict) and any(isinstance(v, dict) and v.get("data") for v in answer.values()):
                self.observed_periods.add(period)
            return answer
        _check_params(p, ("stock_code", "period", "start_time", "end_time") if method == "download_history_data"
                      else ("stock_list", "period", "start_time", "end_time"))
        if period not in ("1d", "1m", "5m"):
            raise ValueError("download supports native 1d/1m/5m only")
        stocks = (_strings([p.get("stock_code")], "stock_code")[0] if method == "download_history_data"
                  else _strings(p.get("stock_list"), "stock_list", 20))
        result = func(stocks, period, p.get("start_time", ""), p.get("end_time", ""))
        return {"source": self.sources[method], "native_result": _plain(result),
                "completion": "unknown; re-query market data to verify coverage"}

    def drain(self):
        # Called ONLY by QMT lifecycle callbacks, never by the HTTP thread.
        if self.closed.is_set() or not self.drain_lock.acquire(False):
            return
        try:
            if not self.callback_seen:
                self.callback_seen = True
                print("[BigQmtGateway] ready: QMT callback active")
            for unused in range(8):
                try:
                    job = self.pending.get_nowait()
                except queue.Empty:
                    break
                if time.monotonic() >= job["deadline"]:
                    continue
                try:
                    job["answer"] = _reply(_plain(self.dispatch(job["method"], job["params"])))
                except Exception as exc:
                    job["answer"] = _reply(error="%s: %s" % (type(exc).__name__, exc))
                job["done"].set()
        finally:
            self.drain_lock.release()

    def close(self):
        self.closed.set()
        while True:
            try:
                job = self.pending.get_nowait()
            except queue.Empty:
                break
            job["answer"] = _reply(error="Big QMT Gateway is not running")
            job["done"].set()
        if self.thread.is_alive():
            self.server.shutdown()
            self.thread.join(3.0)
        self.server.server_close()


def init(ContextInfo):
    global _gateway
    if _gateway is not None:
        _gateway.close()
    _gateway = None
    if getattr(ContextInfo, "do_back_test", False):
        raise RuntimeError("Backtest is unsupported; start in model trading simulation mode")
    if not callable(getattr(ContextInfo, "run_time", None)):
        raise RuntimeError("QMT strategy ContextInfo.run_time is required")
    gateway = _Gateway(ContextInfo, globals(), port=PORT)
    try:
        start = (datetime.datetime.now() + datetime.timedelta(seconds=1)).strftime("%Y-%m-%d %H:%M:%S")
        ContextInfo.run_time("adjust", "200nMilliSecond", start)
        _gateway = gateway
        gateway.thread.start()
    except Exception:
        gateway.close()
        _gateway = None
        raise
    print("[BigQmtGateway] listening http://127.0.0.1:%d/rpc; waiting for QMT callbacks" % gateway.server.server_address[1])
    print("[BigQmtGateway] market APIs: %s" % json.dumps(gateway.sources, sort_keys=True))


def adjust(ContextInfo):
    if _gateway is not None:
        _gateway.drain()


def handlebar(ContextInfo):
    adjust(ContextInfo)


def stop(ContextInfo):
    global _gateway
    if _gateway is not None:
        _gateway.close()
        _gateway = None
        print("[BigQmtGateway] stopped")


print("[BigQmtGateway] source loaded. Start in MODEL TRADING; disable standalone Python process.")
