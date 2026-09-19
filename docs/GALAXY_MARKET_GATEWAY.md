# BigQmtGateway

这是保留的旧 HTTP MVP 说明。当前上游 ZMQ 版本见 [FORK.md](../FORK.md)；本文只读限制仅适用于旧入口。

实验性、仅行情的大 QMT 网关。地址固定为 `http://127.0.0.1:18688/rpc`。
不查询资金、持仓，不下单、不撤单，没有任何交易写接口。`trade_authority=none`。

## 1. 部署

在 PowerShell 执行：

```powershell
cd D:\work\market\BigQmtGateway
powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy.ps1 -Legacy
```

只复制一个文件到：

```text
D:\银河证券QMT测试 - 交易终端\python\BIGQMT_GATEWAY.py
```

不放入 `bin.x64`，不安装包，不修改银河原文件。脚本验证 SHA256；目标相同则跳过，目标不同则拒绝覆盖。
更新时先停止网关，手动把旧 `BIGQMT_GATEWAY.py` 改名备份，再运行部署。
策略源码只有 ASCII 字符，声明 GBK，避免旧 QMT 编辑器编码差异。

## 2. 在 QMT 中启动（这一步需要你操作 GUI）

1. 打开并登录 **大 QMT**。进入顶部 **模型研究**（或“我的主页”），点击 **新建模型 → Python 模型**。
2. 如果模型列表已显示 `BIGQMT_GATEWAY`，直接打开它。否则在新建模型编辑器中，将项目 `qmt\BIGQMT_GATEWAY.py` 的全部源码粘贴进去，保存为 `BIGQMT_GATEWAY`。只操作自己的新模型，不编辑系统示例。
3. 默认品种可保留 **000300（沪深300）**，默认周期“日线”；外部请求仍可指定 `002463.SZ`。保存/编译，确认没有报错。这是本机实际通过验收的配置。
4. 在 **策略编辑器** 顶部直接点击 **运行**，无需新建模拟交易。2026-09-19 已实测此方式能注入 API、触发 QMT 回调并通过全部五项外部验收。
5. 右侧 **“原生python”保持不勾选**（本机截图中的名称）；其他版本若叫“独立 Python 进程”或“启动本地 Python”，同样不勾选。不要点击“回测”；不要用命令行 `python BIGQMT_GATEWAY.py` 启动网关。只运行一个实例。
6. 查看编辑器下方 **日志输出**，应看到：

```text
[BigQmtGateway] listening http://127.0.0.1:18688/rpc; waiting for QMT callbacks
[BigQmtGateway] market APIs: ...
[BigQmtGateway] ready: QMT callback active
```

`source loaded` 只表示文件被读取；`ready` 加上外部 `ping` 成功才表示回调链路已工作。启动后等约 2 秒再测试。
源码当前仍会打印 `Start in MODEL TRADING`，这是初版提示，**不代表本机必须进入模型交易**。之前据参考项目把模型交易作为必需条件的说明已被本机实测纠正；判断依据是 `init`、QMT 回调和外部验收是否成功。

## 3. 验收

在正常 Python 环境运行，无需安装依赖：

```powershell
cd D:\work\market\BigQmtGateway
python test_gateway.py --legacy
```

依次验证 `ping`、`capabilities`、沪深 A 股股票列表、002463.SZ 最近 10 根日 K、最近 20 根 5m K；逐项打印耗时、数据时间范围和最后一根 K 线。
验证 K 线条数、时间轴唯一且递增、OHLCV/成交额及价格关系；空数据、条数不足或缺失字段会失败。任何必测项失败，退出码为 1。
只有全部通过才打印 `LIVE MVP PASS`。取的是 QMT 原生接口当前可取得的最后 N 根；日志保留原始时间，**不凭电脑日期推断行情新鲜度或最后一根已经收盘**。

没启动 QMT/网关时，约 0.6 秒返回 `Big QMT Gateway is not running`，不会继续发四个请求。
端口存在但策略回调停了，健康检查约 2 秒返回 `QMT callback timeout`；其他 API 的 HTTP 等待上限为 8 秒。

可另外运行离线回归：

```powershell
python test_gateway.py --self-test
```

此模式使用模拟 ContextInfo 和临时端口，明确打印 `OFFLINE SELF-TEST`，不能作为真实行情验收结果。

## 4. 空数据与历史下载

首次查询可能只有当天数据，或因订阅刚建立而暂时为空。稍候重新运行验收；仍不足时，在 QMT 的行情数据下载功能中补充 **002463.SZ 的日线和 5 分钟历史**。

也可先查看 `capabilities`，当 `download_history_data.available=true` 时，在外部 Python 使用：

```python
from datetime import datetime, timedelta
from client.bigqmt_client import BigQmtClient

c = BigQmtClient()
print(c.capabilities())
start = (datetime.now() - timedelta(days=90)).strftime("%Y%m%d")
print(c.download_history_data("002463.SZ", "1d", start))
print(c.download_history_data("002463.SZ", "5m", start))
```

下载只调用当前策略确实暴露的函数：

- 单股：注入的 `download_history_data` → 同名 ContextInfo 方法 → 注入的 `down_history_data`。后者是本机大 QMT 手册明确记载的原生名称，实际来源会显示在 `source`。
- 批量：只有注入的 `download_history_data2` 或同名 ContextInfo 方法存在才支持；不循环单股下载伪造批量能力。
- 不存在：`{"ok": false, "data": null, "error": "NotImplementedError: unsupported: ..."}`。
- 原生函数返回不等于下载完成。返回保留 `native_result`，`completion` 明确为 `unknown`；稍候重跑行情查询确认覆盖范围。

下载会由 QMT 写入自己的行情缓存；网关没有数据库，不解析 DAT 文件。默认验收不会自动下载。
已经进入原生 API 的调用不能被 Python 超时强制中断；超时不代表下载取消，不要立即连续重试。尚未执行且已超时的队列请求会被丢弃。

## 5. 停止

在当前 **策略编辑器** 顶部点击 **停止**，应看到 `[BigQmtGateway] stopped`。如果以后改用模型交易运行，则在对应模型交易行停止。
`stop(ContextInfo)` 会结束 HTTP 线程并关闭端口，QMT 自己结束定时器。随后运行验收应快速提示未运行。
若银河版本没有触发停止回调、端口仍占用，请在方便时退出并重新打开 QMT；不要启动第二个实例争抢端口。

## 架构与 JSON

```text
正常 Python → localhost HTTP JSON → 网络线程 → Queue
                                              ↓
                     QMT run_time("adjust", "200nMilliSecond", ...)
                     / handlebar → 白名单 API → 普通 JSON → HTTP 响应
```

入口提供 `init / handlebar / adjust / stop`，只有 QMT 回调执行 ContextInfo/注入函数。`ping` 也经过队列，避免仅端口存活却报告健康。
HTTP 单接收线程、串行处理请求；只绑定 `127.0.0.1`，不使用 Redis、ZMQ、数据库、Web UI 或 MiniQMT 兼容层。
本机 pyzmq 可以导入，但标准库 HTTP 已满足这个小型串行网关的需要，QMT 端和外部端均无需增加依赖。
不开放任意函数调用；没有 `eval/exec` RPC；拒绝浏览器 Origin 和不匹配的 Host。任何本机程序仍可请求白名单行情，这是同机工具而非账号权限系统。

请求示例：

```json
{"method":"get_market_data_ex","params":{"stock_list":["002463.SZ"],"period":"5m","count":20}}
```

响应统一为 `{"ok":true,"data":...,"error":null}` 或 `{"ok":false,"data":null,"error":"..."}`。
DataFrame 转为 `data[股票代码] = {"index": [...], "columns": [...], "data": [[...], ...]}`，保留 QMT 时间索引与列名。
numpy 标量/数组转为普通标量/列表；NaN、Infinity、NaT 转为 `null`，不填零。其他特殊对象只转换为字符串，不展开其内部属性。

客户端方法：`ping()`、`health()`、`capabilities()`、`get_stock_list_in_sector(sector_name)`、`get_market_data_ex(stock_list, period, count, **kwargs)`、两个下载方法。
所有方法返回完整 JSON envelope；连接/协议错误抛 `GatewayError`，原生 API 错误保留在 envelope 中。

K 线默认 `fields=[open,high,low,close,volume,amount]`、`dividend_type=none`、`fill_data=False`、`subscribe=True`；最多 50 个标的、每个最多 2000 根。
`subscribe=True` 由 QMT 订阅行情，停止策略释放订阅；只想读取终端已有缓存时传 `subscribe=False`。
可请求 `1d/1m/5m/15m/60m`，全部直接交给原生 API，不自行合成 K 线。15m/60m 是否有数据尚待实机确认。
`accepted_periods` 是参数白名单；`periods_with_data_this_session` 只记录本次进程查询实际得到非空结果的周期。
`exposed_unverified` 仅表示函数存在，不保证行情权限、下载成功或数据完整。

## 本机检查与验证记录（2026-09-19）

| 项目 | 结果 |
|---|---|
| QMT 安装目录 | `D:\银河证券QMT测试 - 交易终端` |
| 策略目录/包装代码 | `python\` / `python\_PyContextInfo.py` |
| 解释器/运行库 | `bin.x64\pythonw.exe` + `python36.dll`，实际运行 Python **3.6.8 64 位**；无 `python.exe` |
| 标准库/site-packages | `bin.x64\Lib` / `bin.x64\Lib\site-packages`，另有 `python36.zip` |
| 已验证可导入 | `http.server/socketserver/queue/threading/json`；pyzmq **18.0.1**、pandas **0.22.0**、numpy **1.19.1** |
| 示例 | `python\PY简单示例.py` 等；有些策略是 QMT 编码文本，没有执行它们 |
| 行情/板块 | 本机包装代码存在 `get_market_data_ex(fields, stock_code, period, start_time, end_time, count, dividend_type, fill_data, subscribe)` 和 `get_stock_list_in_sector(sectorname, real_timetag=-1)` |
| 下载 | 真实运行确认 `injected.download_history_data` 已暴露，但本次未执行下载；`download_history_data2` 未暴露，返回能力 `unsupported` |
| 生命周期 | 本机包装代码有 `run_time`；本机 API 手册说明 `init/handlebar`、定时器和 `stop` |
| 静态/离线 | **11 项自测**分别在 Python 3.13 与 QMT Python 3.6.8 通过；实际本机 ContextInfo 包装层 + pandas/numpy 序列化检查通过（底层数据为模拟值） |
| 部署 | 已复制到 QMT `python\BIGQMT_GATEWAY.py`，SHA256 一致；部署前已有的 34 个普通文件哈希全部不变。Windows PowerShell 5.1 下新建、重复跳过、拒绝覆盖测试通过 |
| 真实行情 | **策略编辑器直接“运行”：LIVE MVP PASS，退出码 0，总耗时 9.844 秒**。沪深 A 股 5224 个；002463.SZ 日 K 10 根（2026-09-07 至 09-18）、5m K 20 根（2026-09-18 13:25 至 15:00），最后收盘价均为 123.5 |

本次真实验收耗时：ping 1.437 秒、capabilities 2.203 秒、板块 1.817 秒、日 K 2.374 秒、5m K 2.013 秒。此前未启动策略时约 0.61 秒失败，属于启动前记录。
外部启动 `pythonw.exe` 只用于语法/导入/离线测试；上述真实行情结果来自已经运行的银河 QMT 策略。仍须验证：1m/15m/60m、实际下载效果、GUI 停止回调、长期稳定性及定时器实际频率；请求成功不代表定时器精确达到 200ms。

参考：

- [xtquant_big_convert](https://github.com/litaolemo/xtquant_big_convert/tree/c163f561694d23853c0e84aa3e03ca18612dfb1e)，检查了 `BIGQMT_ZMQ_DRYRUN.py`、`BIGQMT_REDIS_DRYRUN.py`、`bigqmt_signal_trader_strategy.py`，采用其“入口文件取得注入 API + QMT adjust 回调执行”的思路，没有复制整个实现。
- 本机 `config\help\python\迅投QMT极速策略交易系统_模型资料_Python_API_说明文档_Python3.pdf`：PDF 第 12、42–43、69 页（生命周期、定时器、停止、原生下载）。
- 本机 `config\help\systemfunction\迅投QMT极速策略交易系统说明文档.pdf`：PDF 第 14–15、31–32 页（新建 Python 模型、新建模拟交易），已核对正文与模型交易截图。
