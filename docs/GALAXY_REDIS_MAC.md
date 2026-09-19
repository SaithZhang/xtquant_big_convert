# Mac / Linux：最短 Redis SDK 验收

状态：`PENDING_MANUAL_VERIFICATION`。本次无法远程访问 Mac，Windows 自测不能代替 Mac 实机结果。无需新增远程部署服务。

## Windows 准备客户端材料

在已提交并部署的 checkout 下：

```powershell
.\.venv\Scripts\python.exe -m pip wheel . --no-deps -w .local\redis-lan\mac
Copy-Item test_redis_sdk.py .local\redis-lan\mac\test_redis_sdk.py
Copy-Item docs\GALAXY_REDIS_MAC.md .local\redis-lan\mac\README.md
git rev-parse HEAD | Set-Content .local\redis-lan\mac\SOURCE_COMMIT.txt
```

将 `.local/redis-lan/mac/` 私下复制到 Mac，例如 `~/bigqmt-client/`。其中有 wheel、测试脚本和已配置 Windows LAN 地址/账号/随机 Redis 密码的 `bigqmt_signal_trader_client_config.py`。不要贴到聊天、提交 Git 或传到公开文件服务。这是 SDK 安装包及本机配置，不是让业务复制驱动源码。

本次已在该目录准备材料。wheel 版本继承上游 0.3.49，以 `SOURCE_COMMIT.txt` 及包 SHA256 区分 fork 构建；完成双方验收后再发布内部固定 Git tag，不提前宣称稳定版。

## Mac 执行

使用 Python 3.10+（推荐 3.12）。依赖由 wheel 安装 pyzmq，另装 redis 5–7 和 pandas 2.x：

```bash
cd ~/bigqmt-client
python3 -m venv .venv
source .venv/bin/activate
python -m pip install ./xtquant_big_convert-*.whl 'redis>=5,<8' 'pandas>=2,<3'
chmod 600 bigqmt_signal_trader_client_config.py
export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"
export BIGQMT_CLIENT_CONFIG_MODULE=bigqmt_signal_trader_client_config
export BIGQMT_FORMULA_ENABLED=0
python test_redis_sdk.py --config-dir . --market-only --seconds 10 --report mac-results.json
```

脚本依次验证：Redis 网络和认证、RPC ping、部署版本、五档快照、日/5m/15m/60m K、股票名单、订阅与取消。失败返回非零退出码；未启动策略时快速提示 `Big QMT Gateway is not running`。不会调用账户、委托、下载或板块写接口。

单独验证用户业务所用 API：

```bash
python - <<'PY'
from bigqmt_signal_trader.xtquant_compat import configure, xtdata
configure()
print(xtdata.get_full_tick(['000001.SZ']))
print(xtdata.get_market_data_ex(stock_list=['000001.SZ'], period='5m', count=10, heal=False))
PY
```

单独检查 Redis 网络（不在命令行暴露密码）：

```bash
python - <<'PY'
import redis
from bigqmt_signal_trader_client_config import BIGQMT_REDIS_CONFIG as c
r = redis.Redis(**{k:c[k] for k in ('host','port','db','password')}, socket_connect_timeout=2, socket_timeout=2)
print('Redis PING:', r.ping())
r.close()
PY
```

订阅示例：

```python
import time
from bigqmt_signal_trader.xtquant_compat import configure, xtdata
configure()
seq = xtdata.subscribe_whole_quote(['000001.SZ'], callback=lambda ticks: print(ticks))
try:
    time.sleep(30)
finally:
    xtdata.unsubscribe_quote(seq)
    xtdata.stop_all_subscriptions()
```

SDK 会先投递一次初始快照。只有后续真实增量回调才能证明跨机器实时推送；交易时段再运行验收脚本，检查 `background_callbacks > 0` 和 `stream=RECEIVED`。休市没有推送时保留 `PENDING_TRADING_SESSION`，不能把初始快照当实时推送验证通过。

若 Redis 不通，先检查 Windows Docker/容器、LAN 地址是否变化、两机是否同一受信子网、Windows 网卡是否 Private、防火墙规则；不要关闭防火墙或改成公网开放。Redis 通而 RPC ping 超时，检查大 QMT 是否登录、策略是否运行、双方账号配置是否一致。可回传已脱敏的 `mac-results.json`（不包含账号/资产数值/密码），仍不要公开客户端配置。
