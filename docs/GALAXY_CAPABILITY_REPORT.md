# 银河大 QMT Gateway：当前能力与后续方向评估

日期：2026-09-19。供协作 AI / 开发者阅读的事实基线，不是上游功能表的逐项成功声明。

## 1. 项目结论

当前项目已经是一座在银河大 QMT 测试客户端内运行的本机行情桥。外部正常 Python 经 ZMQ 调用 QMT 注入的 ContextInfo/API，已实测拿到五档快照、板块成分和日线/分钟 K 线。可以继续开发外部选股和监控实验，但**盘中持续更新、订阅稳定性、跨交易时段运行、重启恢复和报警时效尚未验收**。

当前重点是普通行情及监控。用户已确认 **没有 L2 权限**，L2 不纳入当前目标，不安排权限绕过、适配修复或验收。允许模拟交易接口存在，但本轮没有测试交易，也没有自动交易规则。

## 2. 代码来源与维护方式

- Fork：[SaithZhang/xtquant_big_convert](https://github.com/SaithZhang/xtquant_big_convert)。开发分支 `market-gateway`。
- 上游：[litaolemo/xtquant_big_convert](https://github.com/litaolemo/xtquant_big_convert)，本次基线 `c163f561694d23853c0e84aa3e03ca18612dfb1e`，版本 0.3.49。
- 复用上游传输、序列化、行情提供器、客户端 SDK、订阅与交易接口；`src/`、`tools/` 和上游测试没有改动。
- 银河代码集中在 `extensions/galaxy_sim/`：配置、构建、生命周期补丁、实机测试。旧 HTTP MVP 留在 `qmt/`、`client/` 作为对照。
- 生成的大文件位于忽略目录 `build/`；账户配置位于忽略目录 `.local/`。公开文件不含账户、密码、资产、持仓和委托原文。
- 后续用 `git fetch upstream`、审阅更新、`git merge upstream/main`、重建及验收的方式吸收作者更新；未设置自动合并或自动部署。

## 3. 到底需要启动什么

```text
银河大 QMT 客户端运行并登录
  └─ 内嵌 Python 3.6.8 中的网关策略保持运行
       ├─ ContextInfo / QMT 注入 API
       ├─ ZMQ RPC：127.0.0.1:18689
       └─ 行情/成交回报 PUB：127.0.0.1:18690（推送尚待盘中验收）
外部 Python 3.12 + 上游客户端 SDK
  └─ 请求行情；后续在这里计算监控规则和发送本地提醒
```

**完整 RPC 桥不能只启动 QMT 安装目录下的 pythonw.exe。** 那只提供解释器，不会自动生成策略 ContextInfo、注入 API、登录会话及行情连接。上游也要求在 QMT 里运行入口，见 [README 快速开始](../README.md#快速开始) 和 [上游运行手册](BIG_QMT_SIGNAL_TRADER_RUNBOOK.md)。

上游还提供 FormulaServer 直连，只覆盖部分行情/参考数据；不经过 Python 策略线程，却仍依赖 QMT 的 C++ 行情服务。它不支持完整账户/交易/五档接口，文档还记录了复权、字段覆盖和盘中快照滞后的限制。本机验收显式关闭该旁路，没有验证脱离客户端 GUI 启动其服务的方式，不能承诺“不开客户端也能用”。详见 [README FormulaServer](../README.md#formulaserver-直连快速路径只读行情默认开启)。

### 2.9 万行代码是什么，是否每次都要粘贴

它是上游生成器把约 50 个包模块和 4 个顶层模块合成的部署文件，解决部分 QMT 环境的导入限制。大量代码是已有上游功能，不是新增的业务规则。

- **首次安装或升级代码**才需要部署/加载。当前已保存为 QMT 中的「新建策略文件1」并运行，不需要每次请求行情或每次打开外部 Python 都重新粘贴。
- 当前流程仍需启动并登录 QMT、启动已保存的策略；自动启动策略、后台无人值守与重启恢复未实现。无需每次新建模拟交易实例。
- 上游支持 `package` 多文件部署：同步包目录和配置，在 QMT 中加载较短的 `BIGQMT_ZMQ_DRYRUN.py` 入口。这可以减少编辑器内的大段文本操作，**不会消除 QMT 客户端和策略运行环境的依赖**。
- 下一步可以小范围验证银河客户端是否能稳定使用多文件导入；成功后再切换。当前单文件方式已经实机跑通，多文件方式尚未在本机完成验收，报告不将其标为已完成。

上游推荐模型交易运行方式以获得完整交易语义。本机已证明策略编辑器“运行”、不勾原生/独立 Python，可以完成当前行情读取；**这不能推广为账户查询、交易和成交回报也完整可用**。当前不需要为了行情 MVP 切换到真实交易模式。

## 4. 实测能力摘要

环境：银河测试客户端 2.1.26.0，内嵌 Python 3.6.8、pyzmq 18.0.1；外部 Python 3.12.10。本次为非交易时段，股票样本主要是 `002463.SZ`，ETF 期权样本由 `510050.SH` 的实际期权列表选出。

| 分类 | 当前证据 | 可以得出的结论 |
|---|---|---|
| 连接与生命周期 | 编辑器保存、编译、启动；真实 ping 成功 | 当前策略与外部进程连通 |
| 股票快照 | `get_ticks/get_full_tick` 五档价格/数量数组均为 5，最新价大于零 | L1 五档数据结构有效；未测试盘中更新延迟 |
| K 线 | 日 K 10 根；1m/5m/15m/60m 各 20 根，时间唯一递增，OHLC/成交量/金额检查通过 | 五种周期读取可用；仅验证样本及现有历史，不证明全市场完整覆盖 |
| 板块成分 | 沪深 A 股返回 5224 只，含目标股票 | 可用于构建监控标的池 |
| 合约及期权 | 合约信息、期权列表（28 条）、期权详情、隐波、标的、BSM 计算等非空 | 调用有结果；尚未独立校验所有字段及模型计算精度 |
| 交易日历 | 日期列表返回；部分接口由上游派生 | 可继续验证日历应用；`get_markets` 是硬编码列表，不是原生查询 |
| 财务/股东等 | 当前样本窗口多数为空或 None | 未证明可用于分析；不自动下载、不将空值当零 |
| 账户只读 | 资产字段全为 None；持仓、委托、成交等为空 | 账户读取未验收，不代表真实余额为零或没有持仓/成交 |
| L2 | 请求走 SDK 路径报连接错误；用户确认无 L2 权限 | 当前明确排除，不继续处理 |
| 历史下载 | 已捕获单笔下载注入函数；离线验证了别名桥接 | 真实下载未执行；上游批量包装不等于银河原生批量函数 |
| 行情订阅/回报 | 复用上游实现、发布端口配置存在 | 本机尚未实测持续推送、丢失恢复及退订清理 |
| 模拟交易 | 本地配置开启上游交易 RPC | 没有下单/撤单实测；没有自动交易策略 |

完整 5 项 MVP 实测耗时约 5 秒，其中 capabilities 约 4.48 秒。该结果不是持续性能基准。日 K 最后时间为 20260918，分钟 K 最后时间为 20260918150000；不把周末获取的收盘历史描述成正在产生的盘中实时流。

扩展审计共有 **89 个测试项（含同一方法不同周期，不是 89 个不同方法）**：7 项行情结构/价格校验、3 项本地时间转换、34 项非空返回、28 项空结果、14 项错误、2 项零值/哨兵待核实、1 项静态回退。

错误需要分开看：多数来自原生 xtdata 行情服务不可达；`get_etf_info` 还涉及本机 SDK 需要 stockCode、上游适配器却无参调用的签名差异；历史期权等 ContextInfo 方法不存在；`get_ETF_list` 底层符号未定义。不应全部归因为权限不足，也不应把上游函数名存在当成功。

`get_stock_type` 的 RPC 返回零，`get_turn_over_rate` 返回 None；上游高层 `BigQmtXtData` 已显式抛 NotImplementedError，不应把这些值用于分析。

未测试：任何交易/下载/板块写入/持仓同步/因子生成；显式订阅及退订；没有配置有效公式/因子时不臆造参数执行；没有现成委托号时不伪造 ID 调用 get_value_by_order_id。

## 5. 后续方向建议与验收标准

建议优先完成小范围、只提醒的监控闭环，不扩大成交易系统。

1. **降低启动成本**：验证上游多文件入口；补充状态检查和可重复启动/停止操作。验收：客户端重启后可恢复，端口无残留，不依赖反复粘贴代码。
2. **盘中数据验收**：先用少量标的观察订阅或有界轮询，记录行情时间、接收时间、陈旧状态、断开恢复及午休行为。实测后再决定全市场规模和频率；没有基准前不承诺全市场实时扫描。
3. **55 日线监控**：先确认 MA55 的计算口径、复权方式、当日未完成日 K 是否纳入、触发条件是接近/突破/站稳还是其他定义。补齐至少 55 个有效交易日并校验缺口。本次日线仅测 10 根，尚未验证 MA55 所需历史长度。
4. **15 分钟红 K 提醒**：明确盘中暂时变红与收盘确认；按交易时段划分 K 线，使用股票+K线时间+规则去重，允许转绿撤销提示或只收盘提醒。数据过期时显示不可判定。
5. **后续再决定是否补其他数据**：财务、股东、资金流应先证明样本的语义/覆盖/新鲜度再使用；账户读取与交易不作为行情监控前置条件；L2 暂不考虑。

请协作 AI 优先回答：现有数据是否足够验证规则；采用订阅还是轮询；如何定义未完成 K 线、复权和陈旧数据；最小可用监控规模；哪些工作可以复用上游而非重写。不要以函数表替代实测证据，也不要建议自动交易作为第一步。

## 6. 复现与交付物

- [FORK.md](../FORK.md)：部署、日常使用、上游更新步骤。
- [构建器](../extensions/galaxy_sim/build.py)、[银河补丁](../extensions/galaxy_sim/qmt_overlay.py)、[本机配置示例](../extensions/galaxy_sim/profile.example.json)。
- `python test_gateway.py`：当前真实行情 MVP 验收；自动使用本项目虚拟环境。
- `.venv\Scripts\python.exe -m extensions.galaxy_sim.audit_readonly`：只读扩展审计，私有原始报告保存在 `.local/`；不能把原始资产/持仓写入公开报告。
- 40 项相关回归测试、11 项旧网关离线测试通过；合成 ContextInfo + 真实 ZMQ 测试在外部 Python 3.12 和 QMT Python 3.6 均通过。这些离线测试不等于盘中验收。

下附脱敏逐项记录。RETURNED 仅表示非空，EMPTY 不表示业务事实为零；ERROR 是该参数和当前环境下的结果。错误文本中的“needs SDK/quote service”保留以供定位，不应自动视为用户权限诊断。

## 7. 只读审计明细

| 方法 / 参数范围 | 结果 | 耗时（秒） | 结构或错误 |
|---|---|---:|---|
| `ping` | RETURNED | 0.158 | dict len=7; first=bool |
| `get_instrument` | RETURNED | 0.099 | dict len=30; first=str |
| `get_instrument_type` | RETURNED | 0.100 | dict len=2; first=bool |
| `get_stock_name` | RETURNED | 0.099 | str |
| `get_stock_type` | REVIEW | 0.100 | zero/false, missing-value sentinel or nonfinite scalar |
| `get_last_close` | RETURNED | 0.099 | float |
| `get_last_volume` | RETURNED | 0.099 | int |
| `get_open_date` | RETURNED | 0.100 | int |
| `get_contract_expire_date` | RETURNED | 0.099 | str |
| `get_svol` | RETURNED | 0.143 | int |
| `get_bvol` | RETURNED | 0.056 | int |
| `get_float_caps` | RETURNED | 0.099 | int |
| `get_total_share` | RETURNED | 0.101 | int |
| `get_turn_over_rate` | EMPTY | 0.099 | None |
| `get_contract_multiplier` | RETURNED | 0.099 | int |
| `get_risk_free_rate` | RETURNED | 0.100 | float |
| `get_weight_in_index` | REVIEW | 0.098 | zero/false, missing-value sentinel or nonfinite scalar |
| `is_stock_type` | ERROR | 2.141 | RuntimeError: is_stock_type failed on both paths: SDK Exception: 无法连接行情服务！ / ContextInfo NotImplementedError: is_stock_type is unavailable: needs native xtdata SDK quote service (not reachable in Big QMT full terminal) |
| `get_cb_info` | ERROR | 2.050 | RuntimeError: get_cb_info failed on both paths: SDK Exception: 无法连接行情服务！ / ContextInfo NotImplementedError: get_cb_info is unavailable: needs native xtdata SDK quote service (not reachable in Big QMT full terminal) |
| `get_market_data / 1d` | RETURNED | 0.312 | DataFrame shape=(10, 7) |
| `get_market_data_ex / 1d` | VERIFIED_BARS | 0.123 | dict len=1; first=DataFrame shape=(10, 7) |
| `get_local_data / 1d` | RETURNED | 0.075 | DataFrame shape=(10, 7) |
| `get_market_data_ex / 1m` | VERIFIED_BARS | 0.114 | dict len=1; first=DataFrame shape=(20, 7) |
| `get_market_data_ex / 5m` | VERIFIED_BARS | 0.119 | dict len=1; first=DataFrame shape=(20, 7) |
| `get_market_data_ex / 15m` | VERIFIED_BARS | 0.064 | dict len=1; first=DataFrame shape=(20, 7) |
| `get_market_data_ex / 60m` | VERIFIED_BARS | 0.098 | dict len=1; first=DataFrame shape=(20, 7) |
| `get_close_price` | RETURNED | 0.098 | float |
| `get_index_weight` | ERROR | 2.141 | RuntimeError: get_index_weight failed on both paths: SDK Exception: 无法连接行情服务！ / ContextInfo NotImplementedError: get_index_weight is unavailable: needs native xtdata SDK quote service (not reachable in Big QMT full terminal) |
| `get_l2_quote` | EXCLUDED_NO_L2_PERMISSION (probe ERROR) | 2.034 | RuntimeError: get_l2_quote failed on both paths: SDK Exception: 无法连接行情服务！ / ContextInfo NotImplementedError: get_l2_quote is unavailable: needs native xtdata SDK quote service (not reachable in Big QMT full terminal) |
| `get_l2_order` | EXCLUDED_NO_L2_PERMISSION (probe ERROR) | 2.038 | RuntimeError: get_l2_order failed on both paths: SDK Exception: 无法连接行情服务！ / ContextInfo NotImplementedError: get_l2_order is unavailable: needs native xtdata SDK quote service (not reachable in Big QMT full terminal) |
| `get_l2_transaction` | EXCLUDED_NO_L2_PERMISSION (probe ERROR) | 2.032 | RuntimeError: get_l2_transaction failed on both paths: SDK Exception: 无法连接行情服务！ / ContextInfo NotImplementedError: get_l2_transaction is unavailable: needs native xtdata SDK quote service (not reachable in Big QMT full terminal) |
| `get_stock_list_in_sector` | RETURNED | 0.007 | list len=5224; first=str |
| `get_sector_list` | ERROR | 2.045 | NotImplementedError: get_sector_list cannot enumerate this terminal's sectors: the native xtdata SDK is present but its quote service is unreachable from inside Big QMT, and ContextInfo has no get_sector_list. It used to answer with a hardcoded list of 13 well-known names, which looks exactly like a real listing and never contains your own sectors (issue #143). Pass allow_fallback=True to get those names deliberately -- get_stock_list_in_sector works with them. |
| `get_sector_info` | ERROR | 0.002 | NotImplementedError: get_sector_info is unavailable: needs native xtdata SDK quote service (not reachable in Big QMT full terminal) |
| `get_trading_dates` | RETURNED | 2.102 | list len=5; first=str |
| `get_holidays` | RETURNED | 2.041 | list len=31; first=str |
| `get_date_location` | RETURNED | 0.002 | int |
| `get_trading_calendar` | RETURNED | 2.043 | list len=14; first=str |
| `get_trade_times` | ERROR | 2.039 | RuntimeError: get_trade_times failed on both paths: SDK Exception: 无法连接行情服务！ / ContextInfo NotImplementedError: get_trade_times is unavailable: needs native xtdata SDK quote service (not reachable in Big QMT full terminal) |
| `get_financial_data` | EMPTY | 0.002 | None |
| `get_raw_financial_data` | EMPTY | 0.001 | dict len=1; first=dict len=1; first=dict len=0 |
| `get_etf_info` | ERROR | 0.002 | RuntimeError: get_etf_info failed on both paths: SDK TypeError: get_etf_info() missing 1 required positional argument: 'stockCode' / ContextInfo NotImplementedError: get_etf_info is unavailable: needs native xtdata SDK quote service (not reachable in Big QMT full terminal) |
| `get_ipo_info` | ERROR | 0.002 | NotImplementedError: ContextInfo.get_ipo_info is not available |
| `get_option_list` | RETURNED | 0.008 | list len=28; first=str |
| `get_his_option_list` | ERROR | 0.002 | NotImplementedError: ContextInfo.get_his_option_list is not available |
| `get_his_option_list_batch` | ERROR | 0.002 | NotImplementedError: ContextInfo.get_his_option_list_batch is not available |
| `get_option_undl_data` | RETURNED | 0.006 | list len=96; first=str |
| `get_ETF_list` | ERROR | 0.002 | NameError: name 'get_etf_list' is not defined |
| `get_main_contract` | RETURNED | 0.001 | str |
| `get_his_contract_list` | EMPTY | 0.001 | list len=0 |
| `bsm_price` | RETURNED | 0.002 | float |
| `bsm_iv` | RETURNED | 0.002 | float |
| `get_longhubang` | EMPTY | 0.007 | DataFrame shape=(0, 11) |
| `get_holder_num` | EMPTY | 0.007 | DataFrame shape=(0, 9) |
| `get_turnover_rate` | EMPTY | 0.003 | DataFrame shape=(0, 1) |
| `get_industry` | EMPTY | 0.002 | list len=0 |
| `get_his_st_data` | EMPTY | 0.001 | dict len=0 |
| `get_his_index_data` | EMPTY | 0.001 | dict len=0 |
| `get_north_finance_change / 1d` | RETURNED | 0.080 | dict len=1; first=dict len=16; first=zero/false, missing-value sentinel or nonfinite scalar |
| `get_hkt_statistics` | RETURNED | 0.060 | dict len=1; first=dict len=5; first=str |
| `get_hkt_details` | RETURNED | 0.092 | dict len=1; first=dict len=6; first=str |
| `get_hkt_exchange_rate` | EMPTY | 0.003 | dict len=0 |
| `get_positions` | EMPTY | 0.002 | dict len=0 |
| `query_orders` | EMPTY | 0.002 | list len=0 |
| `query_trades` | EMPTY | 0.001 | list len=0 |
| `get_ipo_data` | EMPTY | 0.002 | dict len=0 |
| `get_new_purchase_limit` | EMPTY | 0.001 | dict len=0 |
| `get_assure_contract` | EMPTY | 0.002 | list len=0 |
| `get_enable_short_contract` | EMPTY | 0.001 | list len=0 |
| `get_unclosed_compacts` | EMPTY | 0.001 | list len=0 |
| `get_closed_compacts` | EMPTY | 0.002 | list len=0 |
| `get_debt_contract` | EMPTY | 0.001 | list len=0 |
| `get_option_subject_position` | EMPTY | 0.001 | list len=0 |
| `get_comb_option` | EMPTY | 0.003 | list len=0 |
| `query_stock_position` | EMPTY | 0.003 | None |
| `get_history_trade_detail_data` | EMPTY | 0.001 | list len=0 |
| `get_last_order_id` | EMPTY | 0.001 | empty/sentinel string |
| `get_option_detail_data` | RETURNED | 0.002 | dict len=30; first=str |
| `get_option_undl` | RETURNED | 0.001 | str |
| `get_option_iv` | RETURNED | 0.002 | float |
| `datetime_to_timetag` | LOCAL_ROUNDTRIP_OK | 0.000 | local SDK conversion |
| `timetag_to_datetime` | LOCAL_ROUNDTRIP_OK | 0.000 | local SDK conversion |
| `timetagToDateTime` | LOCAL_ROUNDTRIP_OK | 0.000 | local SDK conversion |
| `get_ticks` | VERIFIED_SNAPSHOT | 0.066 | Five-level price/volume arrays, positive lastPrice; time=1789716600001; not a live-session test |
| `get_full_tick` | VERIFIED_SNAPSHOT | 0.099 | Five-level price/volume arrays, positive lastPrice; time=1789716600001; not a live-session test |
| `get_markets` | STATIC_FALLBACK | 0.098 | Upstream hardcoded market list; not a native QMT query |
| `get_market_last_trade_date` | RETURNED | 0.099 | str; derived from get_trading_dates |
| `get_top10_share_holder` | EMPTY | 0.101 | dict len=0 |
| `get_asset` | EMPTY | 0.098 | Account envelope returned, all asset fields None; balances unknown |
