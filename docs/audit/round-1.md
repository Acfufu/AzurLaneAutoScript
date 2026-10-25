# 审计第 1 轮（2026-10-25）

分支 `offpeak-audit/20261026`（基线 master `11dc9b1a`）。流程：5 路只读扇出 →
双审仲裁（验真 × 证伪）→ 修正 → 回归 → diff 双审 → 异议修正 → 落盘。

## 0. 基线修正

用户简报的基准点已过时：最近一次 sync merge 不是 `a0d74120`（2026-09-28），而是
`e9e9e7eac`（已合并上游至 `4d88c22d8`，2026-10-23）。真正未合并上游提交 = 12 个
（`git log master..upstream/master`，head `fe8302142`）。本轮 E 线以此为基准。

## 1. 扇出结果（5 个只读子代理）

- **A 语义漂移**：0 条。对 2026-08-29..10-23 全部 126 个上游提交做「旧行存活」
  穷举（3323 条旧行，0 条在上游当前版缺席情况下存活于本仓），并逐函数 AST 对比
  迁移代码（module/core、config_updater、research/preset、flow timers）——无
  verify_thresholds 覆盖面之外的阈值/签名/默认值漂移。
- **B 补偿假设**：6 条候选（B1-B6）。
- **C 跨仓契约**：3 条候选（C1-C3）；control_api 注入锚点、i18n 四语言键、updater
  状态协议逐字段核对为一致。
- **D 运行时证据**：error/ 目录 47 条（10-21..10-25 全在窗口内）。已修历史的实证
  （D1 color_threshold TypeError ×12、D2 color_mask NameError）+ 2 条 .app 潜伏
  （D3/D4）+ 1 条环境类风暴（D5）。
- **E 上游盲区**：merge-tree 干跑（ort + alas-assets driver，树 `c54ea71e6`）实证
  11 个冲突路径，E1-E5 五类风险。

## 2. 双审仲裁表（验真 × 证伪 → 裁决）

| 候选 | 验真 | 证伪 | 裁决 |
|---|---|---|---|
| B1 sync 直推不触发 ci.yml（R2 残余失实） | ✔ | SURVIVES | **确认级** |
| B2 R6 依赖漂移守卫是名字撞车 | ✔ | SURVIVES | **确认级** |
| B3 五目录门禁盲区 + pyproject 注释失实 | ✔ | 盲区主张 BROKEN（三处已披露；证伪者实跑分类器 139 条 0 违例；campaign/ 为桩件结构性不可门）；**注释残留为真** | 残留注释→**确认级**；盲区主张→excluded |
| B4 checklist「每次提交都跑」夸大 | ✔ | SURVIVES(doc-only) | **确认级** |
| B5 SOP 门列表窄于 CI 且缺 undefined-names 门 | ✔ | BROKEN（成本排序最低集属设计；人工 push 触发全量 ci.yml；文档早于门一天） | 待验证 |
| B6 ci 步骤名「Import smoke (full tree)」名不副实 | ✔ | BROKEN（低于阈值；repo 文档一致按 module 域解读） | 待验证（修复目标亦为禁改的 workflow 文件） |
| C1 launcher sparse-checkout 排除现役 SPA | ✔ | SURVIVES（实机实证：$APP/webapp 仅剩 dist） | **确认级**（修复在 launcher 仓→仅建议） |
| C2 payload updater 硬依赖注入的 control_api | ✔ | BROKEN（handler 内惰性导入；端点契约即 launcher 专属；仅缺 try/except 属 nit） | 待验证 |
| C3 launcher alas_tasks.rs 机制注释过时 | ✔ | SURVIVES(doc-only) | **确认级**（launcher 侧→仅建议） |
| D1 阈值 245↔10 等价性存疑 | 等价成立 | BROKEN（否定疑虑=确认等价，255−245=10） | excluded（无问题） |
| D3/D4 .app 快照缺 6bc726f93 修复 | ✔ | SURVIVES(latent；island 任务全禁用；有热补通道；git 更新自愈) | **确认级**（修复=重部署，禁触 /Applications→仅建议） |
| D5 GameStuckError 风暴 | — | — | excluded（设备/atx-agent 环境类，与 fork 代码无关） |
| E1 research.py 半采纳陷阱 | ✔ | SURVIVES | **确认级**（文档化决议） |
| E2 restaurant.py 静默子集陷阱 | ✔ | SURVIVES | **确认级**（文档化决议） |
| E3 modify/delete 测试复活 | ✔ | SURVIVES(降级:卫生陷阱，pytest 兜底) | **确认级**（文档化决议） |
| E4/E5 五个头部冲突 | ✔（修正：仅 3 个 rename 携带） | DOWNGRADE（噪音，门禁可捕获） | 待验证（并入 memo 作信息性行） |

## 3. 修正（每项单独 commit，均过三道门禁 ruff / undefined-names / pyright tests；
pytest 子集 tests/test_campaign_stub_drift.py 4 passed；tests 收集 1542 正常）

| Commit | 发现 | 内容 |
|---|---|---|
| `ec8f3685b` | B1 | risk-register R2 增「残余（2026-10-25 审计修正）」：GITHUB_TOKEN 直推不触发 ci.yml，非 python 门在自动同步路径无处运行 |
| `1adc645cc` | B2 | risk-register R6：requirements matrix job 只查文件存在；漂移无守卫，靠纪律 + 手动 updater |
| `4fcc175c9` | B3 | pyproject F405 注释指向真实门（check_undefined_names.py）并披露其排除面 |
| `f1e8dd96d` | B4 | real-machine-checklist「每次提交都跑」按运行面拆分修正 |
| `a0c4a70b4` | E1-E3 | upstream-sync 增「下次同步预解析备忘」（11 冲突路径逐项决议，落库后删除） |

## 4. diff 双审异议与处置

双审均通过 B2/B4；对 B1/E1-E3 提出异议，B3 一处措辞过宽，两位审阅者一致指出
requirements-matrix.md:62 残留同款失实主张。处置方式：**以修正 commit 撤销异议
内容**（整体 revert 会恢复更失实的原文；等效回滚+重做且保留审计痕迹），异议针对的
是新加语句的准确性而非发现本身，故相关发现不降级：

| Commit | 回应异议 |
|---|---|
| `8d80a2603` [B1-fixup] | 「暴露面有限/fork 自有目录」论证错误——上游同样有 deploy/dev_tools/webapp 且根 requirements.txt 逐字共享（本协调者复核 `git ls-tree upstream/master` 属实）；改为如实陈述暴露面，并修正 upstream-sync.md 同款「上游没有等价物」前提（upstream module/webui=PyWebIO、webapp=Electron，仅 module/cli 真缺席） |
| `78dfc602b` [E-fixup] | 3 处测试路径写错（实为 tests/island_handler/{exchange,recipe}/）；exchange_policy 第 2 块从「琐碎头部」改判实质性冲突（TestScreenReads 类 vs 上游删除）并给出决议；删除「纯文本合并也取上游行」的错误双保险说法（纯文本会在 SUBMARINE_HUNT 相邻区冲突，driver 是唯一安全网）；memo 增「上游前进则重跑干跑」 |
| `297ff2afa` [B4-amend] | requirements-matrix.md §6 标题去掉「每次提交都跑」，加运行面说明并交叉引用 R2 残余 |
| `63f1a19ef` [B3-amend] | 「module/config 在所有门外」收窄为准确表述（utils.py 在 CI pyright 内、模块级有 smoke；仅函数体内未定义名无门） |

## 5. 遗留

- 待验证：B5（SOP 门列表是否需要显式对齐——证伪方主张按设计）、B6（ci 步骤名，
  修复需动禁改的 workflow）、C2（updater 惰性导入是否值得加 try/except 优雅降级，
  证伪方主张按设计）、E4/E5（纯信息性）。
- 确认但修复在域外：C1/C3（launcher 仓，只审不修）；D3/D4（重部署 .app，禁触
  /Applications）→ 全部进最终报告建议区。
- 改进建议（不实施）：见 FINAL-REPORT.md。

## 6. 门禁执行记录

每 commit 后：`uv run --frozen ruff check .`（全绿）、`python
dev_tools/check_undefined_names.py`（OK 2841 用例）、`uv run --frozen pyright
tests`（0 errors；已知 macOS 假错未出现于 tests 范围）。轮末 pytest 子集 4 passed。
