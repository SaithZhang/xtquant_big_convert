"""Standard-library client for the read-only Big QMT market gateway."""
import http.client
import json
import socket


class GatewayError(RuntimeError):
    pass


class BigQmtClient:
    def __init__(self, port=18688, timeout=9.0):
        self.port, self.timeout = port, timeout

    def call(self, method, params=None, timeout=None):
        """Return the uniform {ok, data, error} envelope; transport failures raise."""
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=0.6)
        try:
            try:
                conn.connect()
            except OSError as exc:
                raise GatewayError("Big QMT Gateway is not running (127.0.0.1:%d): %s" % (self.port, exc)) from exc
            conn.sock.settimeout(self.timeout if timeout is None else timeout)
            body = json.dumps({"method": method, "params": {} if params is None else params}).encode("utf-8")
            conn.request("POST", "/rpc", body, {"Content-Type": "application/json"})
            response = conn.getresponse()
            answer = json.loads(response.read().decode("utf-8"))
            if (not isinstance(answer, dict) or set(answer) != {"ok", "data", "error"}
                    or type(answer["ok"]) is not bool
                    or (answer["ok"] and answer["error"] is not None)
                    or (not answer["ok"] and (answer["data"] is not None or not isinstance(answer["error"], str)))):
                raise GatewayError("Invalid Big QMT Gateway response")
            return answer
        except (socket.timeout, TimeoutError) as exc:
            raise GatewayError("Big QMT Gateway is not responding; check the model strategy / adjust timer") from exc
        except (OSError, http.client.HTTPException, ValueError) as exc:
            raise GatewayError("Big QMT Gateway protocol/connection error: %s" % exc) from exc
        finally:
            conn.close()

    def ping(self):
        return self.call("ping", timeout=2.5)

    def health(self):
        return self.call("health", timeout=2.5)

    def capabilities(self):
        return self.call("capabilities")

    def get_stock_list_in_sector(self, sector_name):
        return self.call("get_stock_list_in_sector", {"sector_name": sector_name})

    def get_market_data_ex(self, stock_list, period="1d", count=10, **kwargs):
        return self.call("get_market_data_ex", dict(kwargs, stock_list=stock_list, period=period, count=count))

    def download_history_data(self, stock_code, period="1d", start_time="", end_time=""):
        return self.call("download_history_data", dict(stock_code=stock_code, period=period,
                                                      start_time=start_time, end_time=end_time))

    def download_history_data2(self, stock_list, period="1d", start_time="", end_time=""):
        return self.call("download_history_data2", dict(stock_list=stock_list, period=period,
                                                       start_time=start_time, end_time=end_time))
