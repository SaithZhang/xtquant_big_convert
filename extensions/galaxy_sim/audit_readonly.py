"""Bounded real-terminal read audit. No orders, downloads, or subscriptions.

Reports contain shapes/errors, never raw account balances, positions or orders.
Run: python -m extensions.galaxy_sim.audit_readonly
"""
import datetime
import json
import math
import sys
import time
from collections import Counter

from .config import ROOT, create_client, load_profile


def cases():
    code = "002463.SZ"
    yield "ping", {}
    yield "get_ticks", {"codes": [code]}
    yield "get_full_tick", {"codes": [code]}
    yield "get_instrument", {"code": code}
    yield "get_instrument_type", {"code": code, "variety_list": ["stock", "fund"]}
    for name in ("get_stock_name", "get_stock_type", "get_last_close", "get_last_volume",
                 "get_open_date", "get_contract_expire_date", "get_svol", "get_bvol"):
        yield name, {"stock": code}
    for name in ("get_float_caps", "get_total_share", "get_turn_over_rate", "get_contract_multiplier"):
        yield name, {"stockcode": code}
    yield "get_risk_free_rate", {}
    yield "get_weight_in_index", {"mtkindexcode": "000300.SH", "stockcode": code}
    yield "is_stock_type", {"stock": code, "tag": "stock"}
    yield "get_cb_info", {"stockcode": "113052.SH"}
    for name in ("get_market_data", "get_market_data_ex", "get_local_data"):
        yield name, {"stock_list": [code], "field_list": ["open", "high", "low", "close", "volume", "amount"], "period": "1d", "count": 10, "dividend_type": "none"}
    for period in ("1m", "5m", "15m", "60m"):
        yield "get_market_data_ex", {"stock_list": [code], "field_list": ["open", "high", "low", "close", "volume", "amount"], "period": period, "count": 20, "dividend_type": "none"}
    stamp = int(datetime.datetime(2026, 9, 18, 15).timestamp() * 1000)
    yield "get_close_price", {"market": "SZ", "stock_code": "002463", "real_timetag": stamp}
    yield "get_index_weight", {"index_code": "000300.SH"}
    for name in ("get_l2_quote", "get_l2_order", "get_l2_transaction"):
        yield name, {"stock_code": code, "count": 3}
    yield "get_stock_list_in_sector", {"sector_name": "沪深A股"}
    yield "get_sector_list", {}
    yield "get_sector_info", {"sector_name": "沪深A股"}
    yield "get_trading_dates", {"market": "SH", "start_time": "20260901", "end_time": "20260918", "count": 5}
    for name in ("get_holidays", "get_markets"):
        yield name, {}
    yield "get_market_last_trade_date", {"market": "SH"}
    yield "get_date_location", {"date": "20260918"}
    yield "get_trading_calendar", {"market": "SH", "start_time": "20260901", "end_time": "20260918"}
    yield "get_trade_times", {"stockcode": code}
    window = {"start_time": "20260101", "end_time": "20260918"}
    yield "get_financial_data", dict(stock_list=[code], table_list=["CAPITAL"], **window)
    yield "get_raw_financial_data", dict(field_list=["CAPITAL.total_capital"], stock_list=[code], **window)
    # Factor names are deployment-specific; do not invent one to manufacture a failure.
    yield "get_etf_info", {}
    yield "get_ipo_info", {"start_time": "20260901", "end_time": "20260918"}
    yield "get_option_list", {"undl_code": "510050.SH", "dedate": "202609", "opttype": "", "isavailavle": True}
    yield "get_his_option_list", {"undl_code": "510050.SH", "dedate": "20260918"}
    yield "get_his_option_list_batch", {"undl_code": "510050.SH", "start_time": "20260917", "end_time": "20260918"}
    yield "get_option_undl_data", {"undl_code_ref": "510050.SH"}
    yield "get_ETF_list", {"market": "SH", "stock_code": "510050", "type_list": []}
    yield "get_main_contract", {"code_market": "IF"}
    yield "get_his_contract_list", {"market": "IF"}
    pricing = {"opt_type": "C", "target_price": 3.0, "strike_price": 2.8, "risk_free": 0.03, "days": 30}
    yield "bsm_price", dict(pricing, sigma=0.3)
    yield "bsm_iv", dict(pricing, option_price=0.25)
    yield "get_longhubang", dict(stock_list=[code], count=3, **window)
    yield "get_top10_share_holder", dict(stock_list=[code], data_name="flow_holder", **window)
    yield "get_holder_num", dict(stock_list=[code], **window)
    yield "get_turnover_rate", dict(stock_code=[code], **window)
    yield "get_industry", {"industry_name": "电子"}
    for name in ("get_his_st_data", "get_his_index_data"):
        yield name, {"stock_code": code}
    yield "get_north_finance_change", {"period": "1d"}
    for name in ("get_hkt_statistics", "get_hkt_details"):
        yield name, {"stock_code": "00700.HK"}
    yield "get_hkt_exchange_rate", {}
    for name in ("get_asset", "get_positions", "query_orders", "query_trades",
                 "get_ipo_data", "get_new_purchase_limit", "get_assure_contract",
                 "get_enable_short_contract", "get_unclosed_compacts", "get_closed_compacts",
                 "get_debt_contract", "get_option_subject_position", "get_comb_option"):
        yield name, {}
    yield "query_stock_position", {"stock_code": code}
    yield "get_history_trade_detail_data", {"start_date": "20260918", "end_date": "20260918", "detail_type": "DEAL"}
    yield "get_last_order_id", {"strategy_name": ""}


def describe(value):
    if value is None:
        return "EMPTY", "None"
    if hasattr(value, "shape"):
        return ("EMPTY" if value.empty else "RETURNED"), "DataFrame shape=%s" % (value.shape,)
    if isinstance(value, (dict, list, tuple)):
        if not value:
            return "EMPTY", "%s len=0" % type(value).__name__
        children = list(value.values()) if isinstance(value, dict) else list(value[:5])
        status = "EMPTY" if all(describe(v)[0] == "EMPTY" for v in children) else "RETURNED"
        return status, "%s len=%d; first=%s" % (type(value).__name__, len(value), describe(children[0])[1])
    if isinstance(value, (float, int)) and (not math.isfinite(value) or value in (0, -1, 2147483647)):
        return "REVIEW", "zero/false, missing-value sentinel or nonfinite scalar"
    if isinstance(value, str) and value.startswith("input "):
        return "ARGUMENT_ERROR", value
    if value == "" or value == "-1":
        return "EMPTY", "empty/sentinel string"
    return "RETURNED", type(value).__name__


def main():
    client = create_client()
    account = load_profile()["account_id"]
    path = ROOT / ".local" / "readonly-audit.json"
    only = set(sys.argv[1:])
    report = json.loads(path.read_text(encoding="utf-8")) if only and path.exists() else []
    report = [row for row in report if row["method"] not in only]
    options = []
    last_order = None

    def call(name, params):
        # Explicit cases only; prohibit accidental expansion into write operations.
        assert not name.startswith(("download", "submit", "cancel", "create", "add_", "remove", "subscribe", "unsubscribe", "sync", "gen_", "ipo_subscribe"))
        begin = time.perf_counter()
        value = None
        try:
            value = client.call(name, params, timeout_seconds=6, use_formula=False)
            status, detail = describe(value)
            if name == "get_asset" and isinstance(value, dict):
                fields = {k: v for k, v in value.items() if k != "account_id"}
                if fields and all(v is None for v in fields.values()):
                    status, detail = "EMPTY", "Account envelope returned, all asset fields None; balances unknown"
            if name == "get_markets":
                status, detail = "STATIC_FALLBACK", "Upstream hardcoded market list; not a native QMT query"
            if name == "get_market_last_trade_date":
                detail += "; derived from get_trading_dates"
            if name in ("get_ticks", "get_full_tick") and isinstance(value, dict):
                tick = value.get("002463.SZ", {})
                fields = ("askPrice", "bidPrice", "askVol", "bidVol")
                if all(len(tick.get(k, [])) == 5 for k in fields) and tick.get("lastPrice", 0) > 0:
                    status = "VERIFIED_SNAPSHOT"
                    detail = "Five-level price/volume arrays, positive lastPrice; time=%s; not a live-session test" % tick.get("time")
            if name == "get_market_data_ex" and status == "RETURNED":
                from .test_live import check_bars
                check_bars(value, params["count"])
                status = "VERIFIED_BARS"
        except Exception as exc:
            detail = str(exc).replace(account, "<local-account>")[:1600]
            status = "TIMEOUT" if "timeout" in detail.lower() else "ERROR"
        recorded_params = {"order_id": "<existing-order>"} if name == "get_value_by_order_id" else params
        row = {"method": name, "params": recorded_params, "status": status,
               "seconds": round(time.perf_counter() - begin, 3), "detail": detail}
        report.append(row)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("%s %-30s %.3fs %s" % (status, name, row["seconds"], detail[:110]), flush=True)
        return value, status

    try:
        for name, params in cases():
            if only and name not in only:
                continue
            value, status = call(name, params)
            if name == "ping" and status != "RETURNED":
                break
            if name == "get_option_list" and isinstance(value, list):
                options = [v for v in value if isinstance(v, str) and "." in v]
            if name == "get_last_order_id" and status == "RETURNED":
                last_order = value
            if status == "TIMEOUT":
                _, health = call("ping", {})
                if health != "RETURNED":
                    print("STOP: strategy unresponsive; no further requests queued", flush=True)
                    break
        else:
            if only:
                return
            if options:
                for name, key in (("get_option_detail_data", "stockcode"), ("get_option_undl", "opt_code"), ("get_option_iv", "opt_code")):
                    call(name, {key: options[0]})
            if last_order:
                # Never save a broker order ID in the report params.
                value, status = call("get_value_by_order_id", {"order_id": str(last_order)})
                report[-1]["params"] = {"order_id": "<existing-order>"}
            from bigqmt_signal_trader.xtquant_compat import BigQmtXtData
            stamp = BigQmtXtData.datetime_to_timetag("20260918150000")
            for name, value in (("datetime_to_timetag", stamp),
                                ("timetag_to_datetime", BigQmtXtData.timetag_to_datetime(stamp, "%Y%m%d%H%M%S")),
                                ("timetagToDateTime", BigQmtXtData.timetagToDateTime(stamp, "%Y%m%d%H%M%S"))):
                report.append({"method": name, "status": "LOCAL_ROUNDTRIP_OK" if value in (stamp, "20260918150000") else "REVIEW", "seconds": 0, "detail": "local SDK conversion"})
    finally:
        if client._transport_instance:
            client._transport_instance.stop()
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        lines = ["# 银河 QMT 只读接口实测", "", str(datetime.datetime.now()), "",
                 "RETURNED 只表示返回非空，未证明所有字段正确、实时或权限齐全；EMPTY 不等于业务上确实不存在。REVIEW 为零值/哨兵值待核实。账户仅保存结构，不保存资金、持仓或委托内容。", "",
                 "未执行：交易、下载、板块写入、持仓同步、因子生成、订阅/取消订阅。未提供有效公式或因子名，因此 formula/factor 查询未执行；无既有订阅 ID 时不测试 get_formula_result。", "",
                 "| 方法/周期 | 结果 | 秒 | 返回结构或错误 |", "|---|---|---:|---|"]
        for row in report:
            method = row["method"] + (" / " + row.get("params", {}).get("period", "") if row.get("params", {}).get("period") else "")
            detail = row["detail"].replace("|", "/").replace("\n", " ")
            lines.append("| %s | %s | %s | %s |" % (method, row["status"], row["seconds"], detail))
        path.with_suffix(".md").write_text("\n".join(lines), encoding="utf-8")
        print("COUNTS " + str(Counter(r["status"] for r in report)))
        print("REPORT " + str(path.with_suffix(".md")))


if __name__ == "__main__":
    main()
