# 审计第 3 轮（2026-10-25 深夜）

分支 `offpeak-audit/20261026`（本轮基线 `4937ce2c5`）。收敛轮：五路扇出聚焦前两轮
技术面结构性未达的角落 + 既往结论复核。

## 1. 扇出结果

- **A 语义漂移**：主契约面 0 发现（SPA↔后端 22 个 REST 端点 + SSE + pydantic
  模型逐字段比对全部一致；打包/CLI 一致；campaign 桩加载器与门禁行为与
  docstring 一致；tests 收集 1542 无错误）。2 条轻量候选：A3-1（client.ts
  remoteStatus 的 `state: string` vs 后端 int——零消费者，编译期自暴露）、
  A3-2（verify_thresholds 门禁单向比较盲区）。
- **B 补偿假设**：5 条候选（B3-1..B3-5，全部为「文档计数失实」族：README 活
  文档地图计数 667→689/1393→1396、资产 1343/441→1347/444、pytest 1459→
  1534+8skip、matrix 16/16→21/21 与 27→30、退役工具 docstring 356/357→445）+
  既往审计文档内部一致性核对（15 commits 全对账无误）。
- **C 跨仓契约**：**零新发现**。C2 修复经 launcher 侧验证完全兼容（launcher
  从不 HTTP 调用该端点，仅文件 watcher；优雅路径仅在无 launcher 检出触发=
  无 watcher 可错过）。launcher 对 payload 的全部文件依赖（补丁锚点、内嵌
  Python、deploy 键、协议 v2）逐项在场；i18n 反向全覆盖。C1 修复需连带更新
  launcher 守卫测试 setup.rs:559-560 与注释（记入 C1 建议）。
- **D 运行时证据**：**零新代码发现**；运维状态定论：核心调度**已死**（非停摆）
  ——日志队列 handler 18:50:24 终止，GUI 心跳至 26 日 01:13，07:03 后无任何
  START/RESTART；grid_predictor 热补丁在盘但**未经实战**（存活进程持有补丁前
  字节码；待重启后 OpsiMonthBoss 才会实弹验证）。无 launcher 摩擦痕迹。
- **E 上游盲区**：**零发现**。审计分支新提交后重跑 merge-tree：冲突集与 memo
  记载的 11 路径 1:1 不变（pyproject.toml/updater.py 为上游不存在的 fork 专属
  路径，结构性无冲突面）；两个二进制资产均安全（新增 png 干净并入；tw
  STRATEGY_OPENED png 我方无 delta，静默取上游=正确结果）；无 fetch、无外来
  提交。

## 2. 双审仲裁表

| 候选 | 验真 | 证伪 | 裁决 |
|---|---|---|---|
| B3-1 README 地图计数 + 3 个未转化目录 | ✔（实测 689/1396/134；门禁静默跳过无 snapshot 目录属实但为文档化契约；legacy 是受支持稳态） | SURVIVES（README 为活文档→修数字；「3 目录破坏运行」框架被驳回） | **确认级**（README 数字面） |
| B3-2 资产 1343/441→1347/444 | ✔ | SURVIVES（README/matrix 修；checklist 留快照） | **确认级** |
| B3-3 pytest 1459 | ✔（收集 1542） | SURVIVES + 关键修正：**1534 passed + 8 skipped** 才是可写数字（1542 是 collected；全量实测复核一致） | **确认级** |
| B3-4 matrix 16/16 与 27 | ✔ | 16/16 SURVIVES（**从未正确**：同提交随附的工具就是 21 行——第 2 轮 550 类先例）；27→30 once-true 活表格 | **确认级** |
| B3-5 split_core_utils「must stay 356/357」 | ✔（事实） | BROKEN（自我声明的退役一次性工具，迁移期不变量） | excluded |
| A3-1 remoteStatus TS 类型 | ✔ | 低于阈值（零消费者、编译期自暴露） | excluded（nit） |
| A3-2 verify_thresholds 单向比较盲区 | ✔（两种漂移变体在真实代码路径上实证零输出；当前 0 站点处于盲区） | SURVIVES（真实缺口：**c253f4e69 正是本门禁盲区漏掉的同类**；按章程属仅建议） | 建议（FINAL-REPORT） |

## 3. 修正

| Commit | 发现 | 内容 |
|---|---|---|
| `93949c3a4` | B3-1/2/3 | README 活文档计数刷新：689 py / 1396 json / 1347/444 / 1534 passed + 8 skipped（checklist/plan 按时点快照先例不动） |
| `a72657fe7` | B3-2/3/4 | matrix §6 活表格：21/21、30、1534+8、1347/444；§4/§5 证据格随动（2762） |

门禁：ruff ✔ / undefined-names ✔ / pyright tests 0 错 / **全量 pytest 1534
passed + 8 skipped（15.4s，兼作本轮 pytest 回归）**。commit message 一处措辞
不精确（2759→2762 实为 §5 实现列，非 §4 证据格）——记入本报告，不改史。

## 4. diff 双审

双 PASS、0 异议。两位审阅者独立复跑全部工具核对每个写入数字 = 工具真值；
确认未越界（checklist/plan 旧数字原样保留）；grep 无旧值残留。nit：README
工程门行「1534 passed + 8 skipped」较邻格冗长（保留理由：规避 1542-collected
陷阱且与 matrix 逐字一致）。

## 5. 遗留

- 结构性建议（FINAL-REPORT）：活文档数字刷新无 owner——SOP 合并后清单不含
  回写步骤，verify_requirements 也不比对文档数字 vs 工具输出；建议二选一。
- 运维（升级严重度）：核心调度已死待用户重启；重启后 OpsiMonthBoss 将实弹
  验证 color_mask 热补丁。
- conversion backlog（建议）：3 个 2026-10 同步带入的 campaign 目录（22 图）
  未数据化，位于 verify_map_data 覆盖之外（门禁按文档化契约只查已转化目录）。
