"""Real upstream ZMQ acceptance; no orders or downloads.

Upstream probe_capabilities includes read-only account capability probes.
"""
import time

from .config import create_client, load_profile


def check_bars(data, count):
    from test_gateway import _bars
    frame = data["002463.SZ"]
    if hasattr(frame, "to_dict"):
        split = frame.to_dict(orient="split")
        # Upstream raw native adapter represents stime as a column.
        for field in ("stime", "time", "index"):
            if field in split["columns"]:
                pos = split["columns"].index(field)
                split["index"] = [row[pos] for row in split["data"]]
                break
    elif isinstance(frame, dict) and "records" in frame:
        columns = frame["columns"]
        records = frame["records"]
        rows = [[row.get(c) for c in columns] if isinstance(row, dict) else row for row in records]
        time_col = next((c for c in ("stime", "time", "index") if c in columns), None)
        if time_col is None:
            raise AssertionError("No native timestamps in upstream payload")
        split = {"columns": columns, "data": rows,
                 "index": [row[columns.index(time_col)] for row in rows]}
    else:
        raise AssertionError("Unknown upstream bar payload")
    _bars({"002463.SZ": split}, count)


def main():
    total = time.perf_counter()
    client = create_client()
    profile = load_profile()
    failures = []

    def check(label, method, params, validate, timeout=5):
        start = time.perf_counter()
        try:
            data = client.call(method, params, use_formula=False, timeout_seconds=timeout)
            validate(data)
            print("PASS %-26s %.3fs" % (label, time.perf_counter() - start))
            return True
        except Exception as exc:
            # Do not echo configured account IDs in shareable diagnostics.
            detail = str(exc).replace(profile["account_id"], "<local-account>")
            print("FAIL %-26s %.3fs: %s" % (label, time.perf_counter() - start, detail))
            failures.append(label)
            return False

    def ping(data):
        assert data["allow_order_methods"] == profile["allow_order_methods"], "Unexpected order configuration"

    def caps(data):
        assert isinstance(data, dict) and data, "Empty capabilities"
        print("  upstream capabilities returned; simulated order RPC enabled=%s" % data.get("allow_order_methods"))
        methods = data.get("contextinfo_methods", {})
        for name in ("get_market_data_ex", "get_stock_list_in_sector"):
            assert methods.get(name), "Missing native ContextInfo method: " + name
        print("  native single download bound=%s" % data.get("qmt_globals", {}).get("down_history_data"))

    def sector(data):
        assert isinstance(data, list) and "002463.SZ" in data, "Sector missing target stock"
        print("  sector members: %d" % len(data))

    try:
        print("REAL Galaxy QMT / upstream ZMQ acceptance (no orders)")
        if not check("ping", "ping", {}, ping, timeout=1.5):
            print("Big QMT Gateway is not running or is misconfigured")
            print("Run BIGQMT_GALAXY_SIM in the QMT strategy editor; native Python OFF.")
            return 1
        # Upstream otherwise probes a financial-data download as a side effect.
        check("capabilities", "probe_capabilities", {"download_probe": False}, caps)
        check("sector: HS A shares", "get_stock_list_in_sector", {"sector_name": "沪深A股"}, sector)
        for period, count in (("1d", 10), ("5m", 20)):
            params = {"stock_list": ["002463.SZ"], "period": period, "count": count,
                      "field_list": ["open", "high", "low", "close", "volume", "amount"],
                      "dividend_type": "none", "fill_data": True, "subscribe": True}
            check("002463.SZ %s x %d" % (period, count), "get_market_data_ex", params,
                  lambda d: check_bars(d, count))
        return int(bool(failures))
    finally:
        transport = client._transport_instance
        if transport is not None:
            transport.stop()
        print("TOTAL %.3fs; %s" % (time.perf_counter() - total,
                                  "NOT VERIFIED" if failures else "LIVE MVP PASS"))


if __name__ == "__main__":
    raise SystemExit(main())
