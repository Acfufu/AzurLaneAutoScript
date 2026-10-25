# 风险登记表（上游同步）

> 2026-10-24 建立：对 Acfufu/AzurLaneAutoScript 与 LmeSzinc/AzurLaneAutoScript 差异的
> 首轮审计（提交拓扑 283 ahead / 0 behind、5030 文件差异）后，经逐项决策收束而成。
> 每行风险注明：成因、既有防线、已拍板的处置、人工触发条件。
> 配套流程见 [upstream-sync.md](upstream-sync.md)；机器防线在
> [`.github/workflows/sync-upstream.yml`](../.github/workflows/sync-upstream.yml)。

## 总览

| # | 风险 | 等级 | 处置（2026-10-24 拍板） | 状态 |
|---|---|---|---|---|
| R0 | payload bundle 被启动 reset 冲掉（操作性约束） | 契约 | 改动一律 push 到本仓；严禁只改 launcher 内 bundle | 长期有效 |
| R1 | campaign 双轨制下的静默漂移 | P1 | 同步期红线检测，命中转 PR 不直推 | ✅ 已落地 |
| R2 | 同步回归先推后测 | P1 | 推前跑 ci.yml 的 python 侧门禁，红项转 PR | ✅ 已落地 |
| R3 | Joxos 侧演进零可见性 | P2 | 接受现状；按下文触发条件人工 diff，不做自动化 | 登记在案 |
| R4 | 资产基线重录的固定人工成本 | P2 | 维持人工重录，不自动化 | 登记在案 |
| R5 | `.qoder/` 开发残留入库 | P3 | 已解除跟踪（`4850e4a4`） | ✅ 已关闭 |
| R6 | `uv.lock` + `requirements.txt` 双依赖声明 | P3 | 接受双声明；漂移目前**无自动守卫**（见下） | 登记在案 |

## R0 — bundle 启动即被 reset（操作性约束）

launcher 每次启动对 payload 执行 `fetch + reset --hard origin/master` 并重注入
control_api 相关补丁。**任何直接改 bundle 工作区的改动都会在下次启动被冲掉**，
同步的唯一正道是 push 到本仓。这不是缺陷而是部署契约；登记在案防止再踩。

## R1 — campaign 双轨制下的静默漂移（P1）

**成因**：静态章节 `campaign/**/*.py` 在本仓是 11 行战斗逻辑桩件，地图数据已迁
YAML + `.legacy_snapshot/`；上游仍维护完整 `.py`。上游每周改地图（如
`25f8baa7` Fix: map configs in chapter T），改动落在桩化文件上时文本 merge 可能
干净成功，但地图修复被静默丢弃——上游修的正是我们 YAML 里那份旧数据。

**已落地处置**：`dev_tools/check_campaign_stub_drift.py`（含
`tests/test_campaign_stub_drift.py` 四场景测试）。sync 工作流在 merge 后、push 前
执行：凡上游本轮改动的 `campaign/*.py` 在上游版本含 `CampaignMap(` 而我们合并树
不含（桩化或已删除）即命中，不开直推、把合并结果推成分支开 PR 人工转换。新活动
整文件落地、双方都带完整定义，天然不命中。

**残余**：上游对桩文件只改战斗逻辑（合法吸收）也会转 PR——保守取向，人工过目
成本远低于静默丢修复。campaign 冲突的既有策略见 upstream-sync.md「冲突策略」表。

## R2 — 同步回归先推后测（P1）

**成因**：原 sync 工作流「merge 干净即直推」，CI 在推送之后才跑。历史三起同步
带入的回归均为推后才发现并修复：`5218994d`（`id is ''`，ruff F632 捕获类）、
`c253f4e6`（改名前 kwarg，pytest 捕获类）、`74d74355`（game_tips 裸颜色判定，
flow 行为类）；另有 `e3c728f5` 等 pyright 类。

**已落地处置**：sync 工作流 push 前在 **windows-latest + PYTHONUTF8=1**（与 ci.yml
逐字同环境，避免平台差异假信号）跑 python 侧门禁：ruff / pyright / 全树 import
冒烟 / 结构校验 ×3 / pytest / verify_thresholds / Phase456 等价全套。门禁收集红项
不炸 job，红则把合并结果推成分支开 PR。

**残余（2026-10-25 审计修正）**：前端 / log-align / 打包 / requirements-matrix 门
不在推前清单（非 python 同步面；requirements-matrix 当时也未列入）。早前表述
「仍由推送后的 ci.yml 把守」**不成立**：sync 工作流用仓库 `GITHUB_TOKEN` 直推
（`actions/checkout` 凭据 + fallback PR 用 `GH_TOKEN: github.token`），而 GitHub
对 `GITHUB_TOKEN` 产生的事件不再触发 `push` / `pull_request` 工作流，ci.yml 又只挂
这两个触发器——自动同步的直推提交**没有任何 CI 跑这些门**，它们只在人工 push /
人工合并 PR（触发 ci.yml）时运行。实际暴露面有限：未守门路径（`webapp/`、
`deploy/`、`dev_tools/`、`docs/`）为 fork 自有目录，上游合并没有等价物，同步不直
接带入其改动；风险仅来自同步合并决议本身改到这些目录。若要收紧需改用 PAT 触发
或 `workflow_run` 触发器（动 `.github/workflows`，另行立项决策）。

**残余**：运行时行为类回归（如 game_tips 实机假阳性）任何静态门禁都拦不全，
依赖 flow replay 测试面与实机观察；同步回归模式会随上游演进出现新类别。

## R3 — Joxos 侧演进零可见性（P2）

**成因**：本仓架构种子来自 Joxos（2026-10-16 全历史植入后冻结跟随）；对方是不可
控外部供应商，sync 自动化只覆盖 LmeSzinc。Joxos 修 bug 或改 webui/flow 协议时，
本仓不会被动知晓，直到交互断档才暴露。

**拍板**：不做任何自动化（含巡检 job）。人工触发条件——满足任一即手动 fetch
Joxos 并 diff 其 `webapp/`、`module/flow/`、`module/webui/` 相关提交评估移植：

1. launcher ↔ payload 交互协议（control API / 更新器握手）需要变更时；
2. 获知 Joxos 发布安全修复时；
3. 运行中出现断档现象（webui/flow 行为与预期不符且本仓与上游均无对应改动）。

## R4 — 资产基线重录的固定人工成本（P2）

**成因**：每次同步后 `verify_assets` 常因上游**新增**条目要求重录基线（近三次
同步两次跟着 re-record 提交：`d62ce38c`、`a211838f`）。

**拍板**：维持人工重录，不自动化。基线门禁存在的意义就是迫使人对资产变化过目
（资产是硬故障源，2026-09-08 MAP_PREPARATION 事故在前）；自动重录等于把阈值门
降级成形式。成本仅一条命令一个提交：

```
uv run python dev_tools/verify_assets.py dump dev_tools/baseline/assets_snapshot.json
```

## R5 — `.qoder/` 开发残留（P3，已关闭）

phase456 会话的笔记与基线文本曾被强制 add 入库。`.gitignore` 原本就有 `.qoder/`
条目，`4850e4a4` 补做解除跟踪（磁盘文件保留、历史可溯）。CI 的 Phase456 等价门
只读 `dev_tools/`，无运行时依赖。

## R6 — 双依赖声明（P3）

`pyproject.toml` + `uv.lock`（真实安装源）与 `requirements.txt`（上游兼容面；
consumers：`deploy/docker/Dockerfile`、`deploy/pip.py`）并存。

**2026-10-25 审计修正**：早前表述「漂移由 ci.yml 的 requirements matrix job
把守」**不成立**——该 job 跑的 `dev_tools/verify_requirements.py` 只检查功能清单
各行的产物 / 门禁**文件是否存在**（`Path.exists`），不做任何依赖内容比对；
`requirements.txt` 的再生成器 `dev_tools/requirements_updater.py`（`uv export`）
也未接入任何 workflow。即双声明漂移目前**没有任何自动守卫**，靠纪律兜底：新增
依赖时 `pyproject.toml` 与 `requirements.txt` 两处同步改，并手动跑 updater 再生成。
补上守卫（把 updater 接进 CI 或加 drift 比对）属基建变更，另行立项。
