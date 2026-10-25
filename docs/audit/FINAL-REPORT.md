# ALAS 工程「多轮双审 + 修正」审计最终报告

- 分支 `offpeak-audit/20261026`（自 master `11dc9b1a` 切出，保留、不合并、不 push）
- 期间 2026-10-25 ~ 10-26；协议：每轮 5 路只读扇出（A 语义漂移 / B 补偿假设 /
  C 跨仓契约 / D 运行时证据 / E 上游盲区）→ 验真×证伪双审仲裁 → 仅修确认级 →
  每修必过门禁 → diff 双审 → 落盘。第 4 轮确认级零新增，收敛终止（未触 10 轮
  上限）。
- 基线修正：简报所称「最近 sync merge a0d74120（2026-09-28）」已过时；实际最近
  sync merge 为 `e9e9e7eac`（合并上游至 `4d88c22d8`，2026-10-23），真正未合并
  上游提交 12 个（head `fe8302142`）。审计全程以此为准。
- 逐轮详情：[round-1.md](round-1.md) · [round-2.md](round-2.md) ·
  [round-3.md](round-3.md) · [round-4.md](round-4.md) · 状态机 [state.json](state.json)。

## 1. 确认发现与修正确认表（15 个修复 commit）

| # | 发现（类别） | 内容 | Commit(s) | 复验命令 |
|---|---|---|---|---|
| B1（③） | risk-register R2 声称跳过的门「仍由推送后的 ci.yml 把守」 | GITHUB_TOKEN 直推不触发 ci.yml（递归防护），前端/log-align/打包/requirements 门在自动同步路径无处运行；R2 残余如实重写，含共享路径暴露面（deploy/dev_tools/webapp 上游同样维护；requirements.txt 例外：0 行相同、上游再改必响亮冲突转 PR） | `ec8f3685b` `8d80a2603` | `grep -n "仍由推送后的" docs/risk-register.md`（应无）；对照 `.github/workflows/sync-upstream.yml` push 步与 `ci.yml:3-7` 触发器 |
| B2（③） | R6 声称「requirements matrix CI job 守漂移」 | 该 job 只查文件存在；`requirements_updater.py` 未接任何 workflow；漂移实无守卫 | `1adc645cc` | `.venv/bin/python dev_tools/verify_requirements.py \| tail -3`（只输出行数核对）；`grep -rn requirements_updater .github/`（空） |
| B3 残留（③） | pyproject F405 注释声称「pyright + import smoke 兜底」 | 改为点名真实门（check_undefined_names.py）并精确披露其排除面（module/campaign、module/submodule、campaign/、submodule/ 全在门外；module/config 仅模块级+utils.py 有覆盖） | `4fcc175c9` `63f1a19ef` | `uv run --frozen ruff check module/campaign --select F405 --statistics`（83）；`ruff check . --select F821,F405` 对排除树为 0 |
| B4（③） | checklist「每次提交都跑」夸大（11 门中 log-align/docker/前端/requirements 在自动同步不跑） | 按运行面拆分改写；requirements-matrix §6 同款标题一并修正 | `f1e8dd96d` `297ff2afa` | `sed -n '73,82p' docs/real-machine-checklist.md`；`sed -n '62,68p' docs/requirements-matrix.md` |
| E1-E3（② 前瞻） | 下次 sync（4d88c22d8→fe8302142）11 个冲突路径的危险决议 | upstream-sync 增「预解析备忘」：research.py 整块取上游+删 EOF 调试块（防半采纳）、restaurant.py 取 `_RESTAURANT_ITEM_IDS`（防静默丢历史菜品修复）、四个 modify/delete 平铺测试 `git rm`（防 `git add -A` 复活）、exchange_policy 第 2 块按金标覆盖情况决、五个头部冲突保留双方 | `a0c4a70b4` `78dfc602b` | `git merge-tree --write-tree offpeak-audit/20261026 upstream/master \| grep -c ^CONFLICT`（11）；`sed -n '/下次同步预解析/,/合并后必跑/p' docs/upstream-sync.md` |
| B2-1（③ 自纠） | 第 1 轮 fixup「requirements.txt 逐字共享」失实（blob 0 行相同） | 反转为「例外：上游再改必冲突转 PR」 | `204c3b5ba` | `git diff upstream/master HEAD -- requirements.txt \| grep -c '^[ ]'`（0 上下文行） |
| B2-2（③） | checklist 阈值站点数 550（从未正确） | → 549 | `0f0115a92` | `uv run --frozen python dev_tools/verify_thresholds.py --check \| tail -1` |
| C2（④，唯一代码修复） | `POST /update/restart` 惰性导入 launcher 注入的 control_api；无 launcher 源码检出中 SPA 仍渲染重启按钮 → 500 → 前端未处理拒绝、按钮无反馈死掉 | 守卫化：仅捕获目标模块的 `ModuleNotFoundError`（注入损坏仍响亮抛出），返回 200 `{ok:false,error}`（SPA 渲染「Update failed: …」）；launcher 侧仅文件 watcher 消费、不受影响（第 3 轮双端复验） | `a1f4427cd` | `uv run --frozen pyright module/webui/api/routers/updater.py`（0 错）；launcher 侧 `rg -n "update/restart" /Users/acfufu/Codehub/alas-launcher/src`（无 HTTP 调用） |
| E2-1（② 前瞻） | 上游新金标套件依赖 gitignored `collection/` 且插件未注册——合并后 pytest 批量 ERROR，易误判回归 | memo 增「预期红」条 | `3e5b16299` | `git show upstream/master:.gitignore \| grep collection`；`grep -c skip` 上游 module/testing/screenshot.py（0） |
| B3-1/2/3（③ 数字） | README 活文档计数失实（667→689 py、1393→1396 json、1343/441→1347/444、1459→1534 passed+8 skipped） | 刷新至工具真值（全量 pytest 实测） | `93949c3a4` | `find campaign -name '*.py' -not -path '*snapshot*' \| wc -l`（689）；`uv run --frozen pytest tests -q \| tail -1` |
| B3-4（③ 数字） | matrix §6 活表格 16/16（从未正确：同提交随附工具即 21 行）、27→30 | 四行刷新 + §4/§5 证据格随动（2762） | `a72657fe7` | `.venv/bin/python dev_tools/verify_requirements.py \| tail -1`（21/21） |

门禁纪律：每个修复 commit 后均过 `ruff check .`（全绿）、
`check_undefined_names.py`（2841 用例 OK）、`pyright tests`（0 错；已知 macOS
平台假错仅出现于 module/webui 的 BELOW_NORMAL_PRIORITY_CLASS，CI 平台不出现）、
相关 pytest 子集；第 3 轮另跑全量 pytest（1534 passed + 8 skipped）。

## 2. 待验证清单（含验证命令）

**无未决待验证项**——第 1 轮遗留 pending（B5/B6/C2/E4-E5）已在第 2 轮全部裁决
关闭或修复；第 2-4 轮无新增 pending。下述为留观项（非缺陷，无需行动即可保持）：

- color_mask 热补丁实战验证：待用户重启 alas 核心后，已启用的 OpsiMonthBoss
  将走 `predict_caught_by_siren` 路径。验证：重启后
  `tail -f /Applications/AzurLaneAutoScript.app/Contents/AzurLaneAutoScript/log/*_alas.txt`
  观察 OpsiMonthBoss 运行无 `NameError`。
- memo 时效：若下次 sync 前上游前进过 `fe8302142`，按 SOP §1 ② 重跑
  `git merge-tree --write-tree master upstream/master` 复核后再套用备忘。

## 3. excluded 及理由

| 项 | 理由 |
|---|---|
| A 语义漂移（① 之外的全部主张） | 两轮穷尽（126 上游提交旧行存活扫描 0 存活；AST 逐函数对比；config/registry/arity/异常契约/资产归一化；SPA↔后端 22 端点逐字段）——verify_thresholds 覆盖面之外无漂移 |
| B3 完整盲区主张 | 排除面已三处披露；证伪者在排除树实跑分类器 139 条 0 违例；campaign/ 桩件结构性不可门；submodule/ 无导入方 |
| B2-3 R2 门清单缺 undefined-names | 拍板记录带日期锚定（门晚 41h 落地）；登记表头部明示机器真值以 workflow 为准 |
| B2-4 flow/model.py docstring | 实质正确（pyright 静态 + import 时 NameError 双真实）；仅措辞压缩 |
| B5 SOP 门列表窄于 CI | 成本排序最低集属设计；人工 push 触发全量 ci.yml 兜底；bot 推前门与 CI 同域 |
| B6 ci 步骤名「full tree」 | 低于阈值；repo 文档一致按 module 域解读；修复目标为冻结的 workflow 文件 |
| B3-5 split_core_utils「must stay 356/357」 | 自我声明的退役一次性工具，迁移期不变量，纯噪音 |
| A3-1 remoteStatus TS 类型 | 零消费者、编译期自暴露的 nit |
| D1 阈值等价性 | 245↔10 为精确互补（255−245；上游自身映射于 fec3917e），无问题 |
| D1/D2 运行时错误 | 均已在本审计前修复（c253f4e69 / 6681aa3e1），日志证实修复后零复发 |
| D5 GameStuckError 风暴 | 与设备/atx-agent 不稳定相关，环境类 |
| E4/E5 头部冲突 | 错误决议在收集期响亮失败；memo 已作信息性记录 |
| A4 STRATEGY_OPENED 缺席 | 纯同步滞后（上游 a538382fa 在最后 sync 之后落地），非 fork 漂移；memo 已覆盖吸收路径 |

## 4. 域外确认项（launcher 仓 / 部署面）

> **2026-10-26 收尾更新**：下表 launcher 侧三项（C1、C2-1、C3+C2-2+C4-1）已
> 在 alas-launcher `main` 提交 `9f89595` 修复（本地，未 push；cargo test 232
> passed / clippy clean）。生效条件：重打包发布 launcher（旧二进制仍持旧
> sparse pattern；存量安装的 `webapp/dist` 未被删过，不受影响）。D3/D4 与
> 运维重启项仍待用户动作（见 §6 后「阻塞项」）。

| # | 位置 | 内容 |
|---|---|---|
| C1 | alas-launcher `src/setup.rs:216` | sparse-checkout `!webapp/` 排除**现役** SPA（payload 2026-09-08 由 webapp-tauri 改名 webapp；FastAPI 挂载 webapp/dist；dist 被 gitignore；launcher 自身不构建前端）——新装 clone 无前端，updater 重启路径反复重施错误 pattern；`!webapp-tauri/src-tauri/` 为死条目。修复需连带更新守卫测试 `setup.rs:552-560` 与注释 |
| C2-1 | alas-launcher `src/setup.rs:28-31` | 仓库探测第一探针要求 payload 已删除的 `deploy/installer.py`（e2f4ea925）——Windows/Linux 便携布局不可探测（当前仅 macOS 发行=潜伏；无备用探针） |
| C3+C2-2+C4-1 | alas-launcher `alas_tasks.rs:8-28`、`menu_model.rs:44-45`、`patch.rs` PRISTINE fixture | 过时的 PyWebIO/「无 HTTP API」/`app.py` 机制注释与过时 fixture 快照（行为均正确，仅误导后续维护者） |
| D3/D4 | `/Applications` .app（不可触） | .app 快照（10-24 05:31）缺 `6bc726f93`：production.py `page_island` 与 get_items.py `ImageError` 导入。经调用链核证：D3 在禁用任务+内层门之后、D4 在本 fork 为死代码（get-items 统计栈无调用方）——正常运行不可达；方便时随整体重部署收敛 |
| 运维 | .app 运行时 | `alas.txt` 冻结于 10-25 18:50:23，7h+ 无任务派发、全部 NextRun 过期（GUI 心跳存活；工作线程退出 vs 空转两轮解读分歧，运维结论一致）——**建议重启 alas 核心** |

## 5. gate / 基建改进建议（仅建议，未实施）

1. **verify_thresholds.py 单向比较盲区（最高优先）**：比对只迭代我方站点的
   kwargs，上游站点不再传的受监视 kwarg 被静默跳过、反向从不迭代——历史上
   `c253f4e69`（color_threshold=245 崩溃）正是被此盲区漏掉的本门禁奠基类。
   建议：每对匹配站点做对称 kwargs 名集比对。
2. **活文档数字刷新无 owner**：SOP 合并后清单无「回写 README/matrix §6 数字」
   步骤，verify_requirements 只查文件存在。建议二选一：SOP 增回写步骤，或
   verify_requirements 增「文档数字 vs 工具输出」交叉核对（本轮 6 处失实数字
   即此类漂移）。
3. **campaign 转化 backlog**：2026-10 两次 sync 带入 3 个目录
   （event_20261022_cn、war_archives_20241024_cn、war_archives_20251023_cn，
   22 图）为原始 .py，在数据化与 verify_map_data 覆盖之外（门禁按文档化契约
   只查带 snapshot 目录）。运行时无害（legacy 加载稳态），建议排期转化。
4. **R2 未守门面的收口**：sync 工作流改 PAT/app token 或 ci.yml 增
   `workflow_run` 触发器，使自动同步直推也过前端/log-align/打包/requirements
   门（涉冻结的 workflow 文件，另行立项）。
5. **pyrightconfig.json 陈旧**（仍含已删 alas.py/gui.py；CI 传显式路径故无实害，
   仅 IDE 面）+ `.gitignore` 列出该文件但文件被跟踪（死条目）。
6. **退役工具归档**：dev_tools/split_core_utils.py（自我声明的一次性重构工具）
   建议移 attic 或删除。
7. launcher 侧（对第 4 节）：修复 C1 时同步更新守卫测试与注释；探测探针改用
   fork 稳定标记（如 `pyproject.toml` + `module/cli/`）；批量清理过时注释。

## 6. 终态

- 分支 `offpeak-audit/20261026`：20 个 commit（15 修复 + 5 记录/报告/收尾），
  保留不合并、不 push；工作区无未提交审计产物。
- 收敛判定：第 4 轮五道扇出（B 道内联补齐）确认级零新增，无修正即无 diff 需
  复审——达成终止条件。

### 阻塞项（需用户动作/拍板）

1. **重启 alas 核心**（唯一"今天就该做"的）：Quit 整个 alas-launcher 再开，
   或 webui 调度页 Start。一次动作同时解决：7h+ 任务积压、color_mask 热补丁
   实战验证（重启后 OpsiMonthBoss 立即跑，看 error/ 目录数保持 47、日志无
   NameError）、D3/D4 自愈（.app 启动时 `reset --hard origin/master`，而
   origin 已含 6bc726f93——origin/master == 本地 master `11dc9b1a`）。
2. **审计分支合并**：`offpeak-audit/20261026` 的 15 个修复 commit（含 C2
   payload 代码修复）在合并进 master 前不会进入 .app；审阅后按你节奏合。
3. **推送**：launcher `main`（`9f89595`）与 payload 审计分支均为本地提交，
   push 由你执行（发布动作）。
