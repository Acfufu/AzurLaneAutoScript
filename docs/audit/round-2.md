# 审计第 2 轮（2026-10-25）

分支 `offpeak-audit/20261026`（本轮基线 `f4dee9751`，即第 1 轮全部落盘后）。
同一五路协议，注入第 1 轮结果；各道并尝试以新证据解决本道 pending 项。

## 1. 扇出结果

- **A 语义漂移**：0 条。改用第 1 轮未覆盖的技术：config/argument 与
  registry 逐任务比对（上游 68 个任务方法全数在册）、返回元数逐提交扫描
  （唯一 arity 变更 1900e30d9 已正确解包）、异常契约扫描（唯一新增
  GameTooManyClicke 已在 exchange.py:223）、module/base 全部 10 文件函数级
  AST 对比（分歧全部归类为死代码删除/美化/带注释的刻意修复）、未合并 12 提交
  的资产级 AST 归一化对比（唯一语义差 = STRATEGY_OPENED tw，即未合并的
  a538382fa，与 E 线一致）。信息项：上游仍带我们已修的 `wait_until_stable`
  共享可变 Timer 默认值 bug——SOP 冲突表 module/base 行（手工：取上游逻辑，
  保留我们的改动）已覆盖该场景，登记为信息不另立项。
- **B 补偿假设**：4 条新候选（B2-1..B2-4）+ B5/B6 判定 CLOSE（证伪方考古：
  SOP 列表生于 2026-09-29 且当日为 ci.yml 子集，pyright 收窄是同日滞后而非设
  计，但人工 push 触发全量 CI 的兜底成立）+ 第 1 轮五项修正的主张逐条复核
  （发现 B2-1/B2-2 两处例外，其余准确）。
- **C 跨仓契约**：2 条新发现（C2-1 launcher 探测依赖已删除的
  deploy/installer.py；C2-2 menu_model.rs:45 同 C3 类过时引用）+ C2 判定
  PROMOTE（payload 侧修复）+ WebSocket/进程状态/文件路径/协议常量/认证五个
  新表面全部核对一致。
- **D 运行时证据**：0 新错误条目。发现 D2-1（运维）：核心调度自 18:50 崩溃后
  停摆 5.5h+（GUI 心跳活着但无 RESTART），全部任务 NextRun 过期待跑——D2 的
  实际影响面大于单条日志。D3/D4 风险收窄：D3 在禁用任务+内层门之后、D4 在本
  fork 中为死代码（get-items 统计栈无调用方），正常运行不会崩；.app 与 HEAD
  全量漂移普查仅 4 处且全部已知。
- **E 上游盲区**：1 条 memo 缺口（E2-1）+ memo 完备性复验（重跑 merge-tree 同
  树同 11 路径；STRATEGY_OPENED apply/revert/re-apply 净效应与 __main__ 调试
  块假设均证实）+ 干净并入语义清扫（SeasonTaskNameOcr 兼容、新测试导入全部
  存在）+ E4/E5 判定 CLOSE。

## 2. 双审仲裁表

| 候选 | 验真 | 证伪 | 裁决 |
|---|---|---|---|
| B2-1 第 1 轮 fixup「requirements.txt 逐字共享」失实 | ✔（blob 证据：HEAD 与上游 0 行相同） | SURVIVES（且**反转论点**：上游再改会响亮冲突转 PR，非静默进入） | **确认级** |
| B2-2 checklist「550 站点」 | ✔（工具实测 549） | SURVIVES（历史树复现亦 549，550 从未正确） | **确认级** |
| B2-3 R2 门禁清单缺 undefined-names | ✔ | BROKEN（拍板记录带日期锚定，门晚 41h 落地；登记表头部明示机器真值以 workflow 为准） | 关闭（可选的措辞刷新记为建议） |
| B2-4 flow/model.py docstring 机制 | ✔ | BROKEN（实质正确：pyright 静态 + import 时 NameError 均真实存在） | 关闭（措辞 nit） |
| C2 updater 惰性导入守卫 | ✔（修复形状定为 200+{ok:false}） | SURVIVES（SPA 只呈现 ok:false、吞掉 500；窄捕获 ModuleNotFoundError+e.name 校验；无测试破坏） | **确认级（代码修复）** |
| C2-1 launcher 探测依赖已删 installer.py | ✔ | SURVIVES（潜伏：当前仅 macOS 发行，Win/Linux 有文档承诺） | 确认级→launcher 侧（仅建议） |
| C2-2 menu_model.rs 过时引用 | ✔ | SURVIVES（doc-only，并入 C3 批次） | 确认级→launcher 侧（仅建议） |
| E2-1 上游金标套件合并后批量红 | ✔（FAIL/ERROR 标签修正） | SURVIVES（更糟：插件未注册，有数据也 ERROR；门禁可捕获，memo 补行为省排障） | **确认级（memo 补一行）** |
| B5 / B6 / E4-E5 关闭判定 | — | RATIFY ×3 | 关闭 |

## 3. 修正（每项单独 commit，均过门禁）

| Commit | 发现 | 内容 |
|---|---|---|
| `a1f4427cd` | C2 | updater.py：control_api 未注入时返回 200 `{"ok": false, "error": ...}`（SPA 渲染「Update failed」；仅捕获目标模块的 ModuleNotFoundError，注入损坏仍响亮抛出） |
| `204c3b5ba` | B2-1 | risk-register：requirements.txt 从「逐字共享」改为「例外：响亮冲突转 PR」 |
| `0f0115a92` | B2-2 | checklist：550 → 549 |
| `3e5b16299` | E2-1 | memo 增「预期红」条：~15 例 ERROR 属数据/基建缺口勿当回归 |

门禁：ruff ✔ / undefined-names ✔（2841）/ pyright `module/webui tests` 仅既有
macOS 假错 BELOW_NORMAL_PRIORITY_CLASS（任务简报名列的两条之一，CI 平台不出
现，updater.py 本身 0 错）/ pytest tests/test_webui_routing.py 6 passed。
审阅者独立实测：`e.name` 三分支语义（模块缺/内部依赖缺/符号缺）与守卫行为完全
一致；PasswordGate 不可绕过；响亮冲突经 scratch 三方合并复现。

## 4. diff 双审

两位审阅者独立全过（0 异议）。备注处置：
- round-1.md:68 保留的「逐字共享（复核属实）」历史记录——本文件即为其修正
  标注（见 §2 B2-1）；round-1.md 作为时点记录不改写。
- 非门禁级 nit 记录在案：C2 降级路径可不加日志（预期永久状态）；若日后想加
  `logger.warning` 以获得服务端痕迹，与 OSError 分支对称即可。

## 5. 遗留

- pending 清零：B5/B6/C2/E4-E5 全部裁决关闭或已修。
- 确认但修复在域外（累计）：C1、C2-1、C2-2、C3（launcher 仓）；D3/D4（.app
  重部署，紧急度降低——正常运行不可达）。
- 运维提醒（非本仓发现）：.app 核心调度自 10-25 18:50 起停摆，建议用户重启
  alas 核心（审计无权触 /Applications）。
