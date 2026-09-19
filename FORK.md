# Galaxy fork：package + Redis LAN

## 定位与分支

上游 `litaolemo/xtquant_big_convert` 提供 QMT API 适配、xtdata/xt_trader、Redis/ZMQ RPC、订阅和通用修复。本 fork 只维护银河差异、部署、能力验收和跨平台接入；监控、策略、股票池、预警、Agent 属于其他业务仓库。

- upstream 基线：`c163f561694d23853c0e84aa3e03ca18612dfb1e`，0.3.49（本次 fetch 后未发现更新）。
- 长期分支：`market-gateway`；本次从它创建 `feat/redis-package-lan`，未合并。
- `main` 保持 upstream 镜像，本次不修改。
- 源码部署来自当前 checkout；`src/bigqmt_signal_trader/` 没有修改。`deploy.ps1` 拒绝部署未提交的工作区。

## 为什么仍要打开大 QMT

上游和本 fork 都需要已登录的大 QMT 客户端持续运行策略：ContextInfo 和注入 API 由客户端提供。单独运行它自带的 pythonw.exe 并不能连接这些 API。

2 万多行只是上游把模块打包成单文件的分发方式，不是业务代码必须复制的内容。现在改用 package：驱动模块部署在 QMT 的 python 目录，编辑器仅加载约 400 行的上游入口加 17 行银河生命周期适配。外部 Mac/Windows/Linux 程序只安装 SDK。

```text
业务 Python：configure() / xtdata / xt_trader
                │ 上游 Redis RPC 与订阅
Windows Redis Service（认证 + 指定主机地址 + 私有子网防火墙）
                │
大 QMT 内 GALAXY_REDIS_RUN → checkout 部署的 package → ContextInfo
```

Redis 只做传输，关闭磁盘持久化。QMT 和 Windows Redis 服务都必须运行；不依赖 Docker Desktop 或 WSL2。SDK 新项目优先显式导入，旧 `from xtquant import xtdata` shim 保留但不推荐与官方 xtquant 混装。

## Windows 部署与运行

本机已有 `.venv` 和 QMT 自带 redis 3.5.3。客户端使用上游 `[redis]` extra。Redis 服务采用原 README 指定的 redis-windows 社区发行版，固定 7.4.11，使用随包提供的 `RedisService.exe`。新机器先创建 Python 3.12 venv：

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[redis,dev]' 'pandas>=2,<3'
# 第一次生成私有配置；LAN_IPV4 替换成本机可信局域网地址
.\.venv\Scripts\python.exe -m extensions.galaxy_sim.redis_package --host LAN_IPV4
# 普通 PowerShell，下载并校验固定版本（无需 Docker/WSL）
powershell -ExecutionPolicy Bypass -File extensions\galaxy_sim\redis-lan.ps1 -Mode Prepare
# 管理员 PowerShell：防火墙、服务安装/启动
powershell -ExecutionPolicy Bypass -File extensions\galaxy_sim\redis-lan.ps1 -Mode Firewall
powershell -ExecutionPolicy Bypass -File extensions\galaxy_sim\redis-lan.ps1 -Mode Lan
# 普通 PowerShell，部署 package
powershell -ExecutionPolicy Bypass -File deploy.ps1
```

首次资金账号来自既有 `.local/galaxy_sim.json`（格式见 `extensions/galaxy_sim/profile.example.json`）。不需要登录密码。新 Redis package 无论旧 profile 如何配置，始终 `rpc_allow_order_methods=False`。

部署结构：

```text
<QMT>\python\
  bigqmt_signal_trader\                     # 当前 checkout 的上游原文件
  bigqmt_signal_trader_strategy.py
  bigqmt_signal_trader_redis_rpc_runtime.py
  BIGQMT_REDIS_DRYRUN.py                     # 上游入口原文件
  BIGQMT_GALAXY_REDIS.py                     # 原入口 + 最小 overlay
  bigqmt_signal_trader_local_config.py       # 私有生成配置
  galaxy-package-manifest.json              # commit、dirty 状态、SHA256
```

部署器先检查所有冲突再复制，不覆盖未知文件或被 GUI 改过的文件；升级自己的文件会在 `.local/redis-lan/backups/` 备份。升级前先停止 QMT 策略，部署后重新加载。不要手改生成包或 manifest。

QMT「模型研究 → 策略编辑器」中右键「PYTHON模型指标 → 新建模型 → Python模型」，命名 `GALAXY_REDIS_RUN`。把 `build/redis-package/BIGQMT_GALAXY_REDIS.py` 的文本放进编辑器，保存后点「运行」。**不要勾原生 python/独立 Python 进程，不点回测。** 这台银河终端已验证编辑器运行能注入 API，不需要新建模拟交易实例。日志有 `[GalaxyPackage] ready transport=redis orders=False commit=...`；外部测试通过才代表通路可用。

不要让 GUI 保存覆盖部署器管理的 `BIGQMT_GALAXY_REDIS.py`；QMT 自己保存的策略可能是专有编码，因此使用独立的 `GALAXY_REDIS_RUN` 名称。

```powershell
.\.venv\Scripts\python.exe test_redis_sdk.py --report .local\redis-lan\windows-results.json
```

原 `python test_gateway.py` 仍检查 **legacy ZMQ**，不用于验收 Redis。停止 Redis 策略：编辑器点「停止」，应有 `[GalaxyPackage] stopped`；只停 Redis 服务可在管理员 PowerShell 执行 `redis-lan.ps1 -Mode Stop`，查看状态用 `-Mode Status`。服务名 `BigQmtGalaxyRedis`，Automatic 启动，使用低权限 `NT AUTHORITY\LocalService` 身份；不启动 QMT、不自动登录。修改配置后，在管理员 PowerShell 再运行 `-Mode Lan` 重启本服务，随后重新运行 QMT 策略。

## LAN 配置边界

私有配置都在 `.local/redis-lan/`，包括 `settings.json`、随机强密码、Redis 配置、Windows/Mac 客户端配置及备份。不要提交或公开发送此目录。QMT 本地配置也包含认证信息。

Redis 来自 [redis-windows 7.4.11 的带 Service 安装包](https://github.com/redis-windows/redis-windows/releases/tag/7.4.11)，是 Windows 社区构建（附带 Cygwin DLL，不需要安装 Cygwin、WSL 或 Docker），不是 Redis 官方 Windows 发行。下载 SHA256 固定为 `2289eca02c25e96a918812c3b05083c3a8bc9440f1b268cc48e14bd93ed2acb0`；启动前还逐项比对安装包中的 exe/dll。二进制位于 `.local/redis-lan/native/`，运行目录是 `.local/redis-lan/service-data/`；代码仓库不分发二进制。

Redis 直接绑定 `127.0.0.1` 和具体 LAN IPv4，沿用端口 16379、db 5 和原随机密码；无主机通配绑定或 IPv6 监听。服务自动启动，运行时仅需 Windows 服务进程，不需要 Docker Desktop / WSL2 常驻。
防火墙规则 `BigQmtGalaxyRedisLAN` 只允许当前网卡子网、Private profile、指定本机地址和 TCP 端口。默认入站防火墙必须保持启用，勿添加其他宽泛放行规则；路由器不得做公网端口转发，勿经公网隧道公开服务。Redis AUTH 未加密，仅用于用户指定的可信局域网。IP/网段改变后需重新审查私有配置、重建规则并重启 Windows 服务，不能盲目延用旧配置。需要仅本机访问时应另行审查配置；当前 `Lan` 模式固定校验精确的双地址绑定。

服务安装参数遵循 [redis-windows 的 RedisService 文档](https://github.com/redis-windows/redis-windows#usage)。

## Galaxy patch 审查

| 旧适配 | package 决策 |
| --- | --- |
| 手动捕获 QMT injected globals | 移除重复逻辑；上游入口调用 canonical capture |
| download_history_data → down_history_data | 移除重复逻辑；上游 RPC 已支持两种命名及 batch 回退 |
| 禁止后台 ContextInfo 预热 | 保留：上游 runtime 未转发此配置；overlay 在 init 前设置 warm_context_data=False |
| stop 清理 | 保留：调用上游 reset_app；不上游复制清理实现 |

新 patch 是 `extensions/galaxy_sim/package_overlay.py`，不改驱动目录。网络接收使用上游 Redis 后台接收线程，`rpc_process_in_listener=False`，QMT 回调处理请求；关闭 FormulaServer 旁路、行情缓存、自动下载任务。旧 `qmt_overlay.py` 仅由 legacy 构建器使用，保留已验证回滚产物，不把它接到 package。

## 2026-09-19 Windows Service 迁移后实测

在 Docker Desktop 退出后，使用 Windows Redis 7.4.11 Service、银河 2.1.26.0、内置 Python 3.6.8 的**真实策略**重新完成（非 mock）。RPC/SDK/package 未改，QMT package 仍为 `b5139f9` 提交部署的原文件；本次仅更换宿主 Redis 服务。

| 检查 | 结果 |
| --- | --- |
| Redis 认证、RPC ping | PASS |
| get_deployment_info | PASS：0.3.49 / Python 3.6.8；路径核对部署 package |
| 000001.SZ 五档快照 | PASS；最后交易日快照，不标为周末实时成交 |
| 1d / 5m / 15m / 60m K 线 | PASS，每项 10 根，末端 2026-09-18 |
| 沪深 A 股名单 | PASS，5224 项 |
| 账户查询 | 调用 PASS，资金内容 UNKNOWN；不能视为完整账户验收 |
| 持仓查询 | 调用 PASS，空列表；不证明账户无持仓 |
| subscribe_whole_quote / unsubscribe | 注册、初始快照、清理 PASS；持续推送 PENDING_TRADING_SESSION |
| 本机经 LAN 地址运行同一 SDK | PASS；不替代跨机器防火墙验收 |
| Mac 实机 | PENDING_MANUAL_VERIFICATION |

没有测试交易写操作；L2 无权限，本次不测。模拟客户端与策略编辑器的账户上下文限制需要后续单独诊断；不得用 0 补齐未知资产字段。私有逐项耗时报告见 `.local/redis-lan/windows-native-results.json`。

回归验证：90 个测试及 15 个 subtests 通过（Galaxy 配置/部署保护、Redis RPC、关闭清理、客户端配置优先级、订阅流程）。两处 Redis 主机发布地址均验证拒绝匿名/错误密码；Windows 有效防火墙配置为启用且默认入站 Block。已核对运行 package 路径及部署文件 SHA256。跨机器访问仍需 Mac 实机验收。

## Mac 与其他业务项目

见 [Mac 最短验收](docs/GALAXY_REDIS_MAC.md)。Mac 无需安装或启动 QMT，只需 Windows 端保持客户端和策略运行。

```python
from bigqmt_signal_trader.xtquant_compat import configure, xtdata, xt_trader
configure()  # 读取本机 private client config
print(xtdata.get_full_tick(['000001.SZ']))
print(xtdata.get_market_data_ex(stock_list=['000001.SZ'], period='5m', count=10))
```

业务不直接访问 Redis key、不构造 RPC payload、不复制驱动源码。内部稳定后再打 `galaxy-v0.1.0` 等 tag，通过固定 tag 安装；本次不提前打稳定标签。基础设施验收脚本的 Redis PING 仅检查网络，不是业务接口。

## 回滚与跟进上游

旧 `BIGQMT_GALAXY_SIM` / 单文件构建器 / ZMQ 测试全部保留，未删除。停止 `GALAXY_REDIS_RUN`，在旧策略页运行 ZMQ 入口即可回到旧链路；不要同时运行两个服务处理同一账号。**原 legacy 私有配置曾允许模拟交易 RPC，回滚前需设 `.local/galaxy_sim.json` 的 allow_order_methods=false，重新构建并粘贴至旧策略保存**，保持当前只读要求。`python -m extensions.galaxy_sim.build` 构建；`deploy.ps1 -ZmqRollback` 仍执行原有拒绝覆盖策略，已有不同文件时用生成文本在 GUI 更新，不覆盖券商文件。更早 HTTP MVP 用 `deploy.ps1 -Legacy`。

旧版操作记录保留于 [ZMQ 历史说明](docs/GALAXY_ZMQ_LEGACY.md)，其中旧配置和路径描述仅代表迁移前状态。

更新顺序：fetch upstream → 检查上游变化 → 在功能分支合并 upstream/main → 审查剩余 overlay → 测试 → commit → 停策略/部署/重新加载 → Windows 实测 → Mac 验收。仅在验收后考虑合并回 market-gateway；不要在 main 开发银河功能。

迁移清理：旧 `galaxy-qmt-redis` 容器已停止并设为 restart=no；Docker Desktop 已退出。保留停止的旧容器/镜像，不删除用户的 Docker 数据，也不修改全局 Docker 或其他 WSL 发行版设置。旧 Docker 配置只作迁移历史，不再是部署依赖。ZMQ 回滚继续保留。
