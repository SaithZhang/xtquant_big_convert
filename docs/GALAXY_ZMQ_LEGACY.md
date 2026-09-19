# 银河 QMT 二次开发入口

本目录现在是 [SaithZhang/xtquant_big_convert](https://github.com/SaithZhang/xtquant_big_convert) 的真实 Git 工作区，开发分支 `market-gateway`。`origin` 指向自己的 fork，`upstream` 指向 [litaolemo/xtquant_big_convert](https://github.com/litaolemo/xtquant_big_convert)。当前基线 `c163f561694d23853c0e84aa3e03ca18612dfb1e`，版本 0.3.49。银河开发代码与能力报告在 `market-gateway` 分支维护。

上游 `src/`、`tools/` 和原 README 保留原样。银河适配集中在 `extensions/galaxy_sim/`，只负责配置、构建、少量生命周期适配和验收。不要直接修改生成的大文件。

当前完整能力、实测明细及后续方向见 [能力报告](docs/GALAXY_CAPABILITY_REPORT.md)。L2 当前无权限，不纳入开发目标。

## 当前架构

```text
外部 Python：上游 BigQmtRpcClient / BigQmtXtData
    │ ZMQ RPC  tcp://127.0.0.1:18689
    ▼
BIGQMT_GALAXY_SIM（上游无 Redis 单文件入口 + 银河小补丁）
    │ QMT init / adjust / handlebar 回调处理请求
    ▼
ContextInfo / QMT 注入函数

行情订阅与成交回报：上游 PUB/SUB，127.0.0.1:18690
```

复用上游的通信协议、JSON 特殊对象转换、行情提供器、股票列表、历史下载、订阅管理、交易及成交回报接口。没有 Redis 服务、数据库或 Web UI。传输保留上游 `ok/data/error` 响应；上游 Python 客户端将成功响应还原成数据，错误抛异常。

本机配置已按用户要求开启模拟交易 RPC，**没有提交或撤销任何委托**。`simulation` 是使用者声明，软件不能仅凭该字段验证券商账户是否真的为模拟账户。公开示例仍默认关闭交易，实际账号只在 `.local/galaxy_sim.json` 和忽略的生成文件内，不包含密码。

银河补丁仅做三件事：捕获当前策略注入的函数并将 `download_history_data` 映射到上游的 `down_history_data`；关闭上游后台 ContextInfo 预热；提供 `stop` 清理回调。RPC 接收和执行均使用上游无后台线程模式，由 QMT 回调驱动，避免网络线程直接访问 ContextInfo。

## 本机操作

1. 在 `D:\work\market\BigQmtGateway` 打开 PowerShell。本机已经创建 `.venv` 并安装上游 SDK、测试依赖和 pandas。新机器初始化：

   ```powershell
   py -3.12 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -e '.[dev]' 'pandas>=2,<3'
   New-Item -ItemType Directory .local -Force
   Copy-Item extensions\galaxy_sim\profile.example.json .local\galaxy_sim.json
   ```

   将示例的 `account_id` 改为 QMT「系统设置 → 账号管理」中的数字资金账号，普通股票使用 `STOCK`。不使用登录名称，不填密码。`allow_order_methods` 控制交易 RPC；本机私有配置已设为 `true`。

2. 构建并部署：

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\deploy.ps1
   ```

   生成 `build\BIGQMT_GALAXY_SIM.py`，复制到 `D:\银河证券QMT测试 - 交易终端\python\BIGQMT_GALAXY_SIM.py`，校验 SHA256。该脚本不覆盖已有不同内容文件；升级时先在 QMT 停止策略，将原来的 **BIGQMT_GALAXY_SIM.py** 改名备份，再重新部署。不要改动银河自带文件。生成文件包含本地账号，不要提交 Git 或分享。

3. 在你截图中的「策略编辑器」，新建 Python 策略 `BIGQMT_GALAXY_SIM`，导入上述文件，或将整个文件内容粘贴进去并保存。不要把文件当普通 Python 程序运行。

4. **不需要新建模拟交易实例**。本机旧网关和新 ZMQ 网关均已在编辑器「运行」方式完成行情验收。先停止旧策略，然后点击新策略的「编译」和「运行」，不是「回测」。不要勾选 **原生python / 独立 Python 进程**。

5. 日志出现 `[GalaxySim] ready RPC=127.0.0.1:18689 ... orders=True` 表示入口启动完成；外部验收通过才代表行情通路可用。

6. 外部验收：

   ```powershell
   cd D:\work\market\BigQmtGateway
   python test_gateway.py
   ```

   脚本自动使用本目录 `.venv`，依次验证 ping、上游 capabilities、沪深 A 股名单、002463.SZ 最近 10 根日 K、20 根 5m K，并打印各项耗时和 QMT 原始时间戳。不开自动下载、不发委托。上游 `probe_capabilities` 会附带只读的账户/信用接口探测；脚本不打印账号、资产或持仓。断开时首个 ping 超时 1.5 秒并退出，提示 `Big QMT Gateway is not running`。

7. 停止：在新策略编辑器点击「停止」。应看到 `[GalaxySim] stopped`，两端口释放。不需要关闭整个 QMT。

## 外部代码复用

```python
from extensions.galaxy_sim.config import create_client
from bigqmt_signal_trader.xtquant_compat import BigQmtXtData

client = create_client()
xtdata = BigQmtXtData(client)
bars = client.call("get_market_data_ex", {
    "stock_list": ["002463.SZ"], "period": "5m", "count": 20,
    "field_list": ["open", "high", "low", "close", "volume", "amount"],
    "dividend_type": "none"
}, use_formula=False)
print(bars)
```

使用上游 `BigQmtXtData` 的订阅和取消订阅接口即可继续开发监控；本机关闭 FormulaServer 旁路和行情缓存，便于验收真实策略连接。上游 API 详细说明见 [README](README.md)。不要在上游代码外再造一套通信或 MiniQMT 兼容层。

## 合并作者后续更新

```powershell
git status
# 先检查并提交自己的代码；确认 .local、build 和账号未进入提交。
git fetch upstream
git log --oneline HEAD..upstream/main
git merge upstream/main
.\.venv\Scripts\python.exe -m extensions.galaxy_sim.build
.\.venv\Scripts\python.exe -m pytest -q extensions/galaxy_sim/test_config.py tests/test_single_file_build.py tests/bigqmt_signal_trader/test_single_file_zmq_bind.py
.\.venv\Scripts\python.exe -m extensions.galaxy_sim.smoke_embedded build/BIGQMT_GALAXY_SIM.py
# 部署、在 QMT 停止后重新加载，再运行真实验收。
python test_gateway.py
```

离线 smoke 使用合成 ContextInfo，只用于无交易地验证入口加载、线程路由、序列化和停止释放端口；运行前停止真实新网关，避免占用相同端口。构建器会检查上游配置结构变化并报错，便于升级时发现不兼容。没有自动拉取、自动合并或自动部署任务。

## 能力边界及下一步

本次验证（2026-09-19）：40 项相关上游/银河回归测试通过，旧 HTTP 的 11 项离线测试通过；生成入口在 Python 3.12.10 与银河内置 Python 3.6.8 均通过合成 ContextInfo + 真实 ZMQ 集成测试，覆盖策略线程执行与停止释放端口。新文件已复制到银河 `python` 目录并通过 SHA256 校验。随后已通过 QMT 编辑器将正确按 GBK 解码的源码粘贴到「新建策略文件1」，保存、编译并运行；2026-09-19 19:38 外部真实验收全部通过：ping 0.043 秒、capabilities 4.478 秒、沪深 A 股 5224 只、日 K 10 根、5m K 20 根，总耗时 4.996 秒。日 K 最后时间 20260918，5m 最后时间 20260918150000。未下单、未撤单、未触发下载。原生 Python 保持未勾选。复制源码时必须先按 GBK 正确解码，不能将按 UTF-8 误读后已乱码的文本贴回编辑器。损坏策略的原文件已备份至 `.local/broken-editor-before-repair.py.bak`。

- **旧 HTTP 入口已实机验证**：沪深 A 股 5224 只、002463.SZ 日 K 10 根和 5m K 20 根；该结果属于旧入口，不等于新 ZMQ 入口已实机验证。
- **新入口复用现成功能**：行情、订阅、账户查询、模拟交易 RPC 和成交回报。是否能在当前银河策略运行模式下完成订阅和委托，须分别验收；配置已开启不代表委托已成功。
- 当前银河暴露单笔历史下载函数；补丁已桥接，尚未进行真实下载验证。上游 `download_history_data2` 可能逐股票调用单笔下载，不能据此宣称银河有原生批量函数。异步下载任务关闭。1m / 15m / 60m 已分别实测 20 根 K 线并通过数据校验；盘中更新仍待验收。
- 后续 55 日线和 15 分钟红 K 监控放在外部 Python：复用行情订阅，在有时间戳的新数据上算规则。实现前明确 55 日线是否排除当日未完成日 K、红 K 是盘中形成还是收盘确认，以及提醒去重和午休时段。当前没有实现报警或自动交易规则。

旧 HTTP 源码保留在 `qmt/`、`client/`；`python test_gateway.py --legacy` 可复测，`--self-test` 可运行原 11 个离线测试。旧部署使用 `deploy.ps1 -Legacy`。原说明保存在 [GALAXY_MARKET_GATEWAY.md](docs/GALAXY_MARKET_GATEWAY.md)，最初五文件备份位于忽略目录 `.local/legacy-mvp-20260919.zip`。
