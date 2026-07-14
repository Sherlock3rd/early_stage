# 游戏前期体验分层 LOOP 流程 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将寒霜现有三个巨型 LOOP 改为按真实时间串联的 16 个小 LOOP，并通过分段背景带和具体节点连线表达三个大 LOOP。

**Architecture:** `global_loops` 增加 `macro_loops`，原 `loop` 节点迁移为带唯一 `macro_loop_id` 的 `micro_loop`。Viewer 使用纯视图模型生成时间主链、连续大 LOOP 分段和关系标签，桌面绘制具体奖励/动机之间的 SVG 连线，移动端保留完整方向文本。

**Tech Stack:** Python 3 `unittest`、原生 JavaScript、HTML/CSS、内联 SVG、现有 `build_viewer.py`。

**Execution note:** 在现有 `feature/global-loop-flow` 分支继续实施，保留全部前序未提交文件；除非用户明确要求，不创建 Git commit。

---

### Task 1: 迁移分层 LOOP 数据契约

**Files:**
- Modify: `.cursor/skills/game-early-experience-breakdown/tests/test_video_analysis_pipeline.py`
- Modify: `.cursor/skills/game-early-experience-breakdown/scripts/analysis_model.py`

- [ ] **Step 1: 将测试夹具迁移为 `macro_loops + micro_loop`**

`valid_global_loops()` 使用：

```python
"macro_loops": [
    {
        "id": "settlement",
        "title": "聚落建设",
        "accent": "settlement",
        "summary": "通过建设形成成长反馈",
    }
]
```

把 `core-loop` 改为：

```python
{
    "id": "core-loop",
    "type": "micro_loop",
    "title": "基础循环",
    "summary": "完成一次闭环",
    "macro_loop_id": "settlement",
    "slice_indices": [0],
    "evidence_frames": [first["main_frame"]["path"]],
    "status": "confirmed",
    "confidence": 0.8,
    "motivation": "完成目标",
    "behaviors": ["执行核心操作"],
    "reward": "获得反馈",
    "next_motivation": "追求下一目标",
}
```

线性节点统一包含空字符串 `"macro_loop_id": ""`。

- [ ] **Step 2: 写 RED 契约测试**

覆盖：

- 缺少 `macro_loops`。
- 大 LOOP ID/配色重复或非法。
- `micro_loop` 缺少主归属、四段、置信度或证据。
- 非小 LOOP 携带四段字段。
- `macro_return` 两端不是同一大 LOOP，或中间没有打断。
- `cross_macro` 两端属于同一大 LOOP。
- `primary` 时间逆序。
- 旧 `type: loop` 被拒绝。

Run:

```powershell
py -3 -m unittest discover -s ".cursor/skills/game-early-experience-breakdown/tests" -p "test_video_analysis_pipeline.py" -k "global_loop" -v
```

Expected: FAIL，原因是新字段和枚举尚未实现。

- [ ] **Step 3: 实现最小校验器**

将枚举调整为：

```python
GLOBAL_LOOP_NODE_TYPES = ("micro_loop", "transition", "end", "outside_exit")
GLOBAL_LOOP_EDGE_KINDS = ("primary", "macro_return", "cross_macro", "conditional")
```

新增 `_validate_macro_loops()`，并在 `_validate_global_loops()` 中：

- 强制 `scope/macro_loops/nodes/edges`。
- 验证大 LOOP 唯一 ID、合法 accent 和非空文案。
- `micro_loop` 必须引用大 LOOP，完整填写四段与 `confidence`。
- 其他节点禁止四段且 `macro_loop_id` 为空。
- 节点按最早时间片单调排列。
- `macro_return` 和 `cross_macro` 检查两端归属。
- 保留证据、主体边界、主路径、出口和孤立节点校验。

- [ ] **Step 4: 运行 GREEN 与完整模型测试**

执行 Step 2 命令，再运行：

```powershell
py -3 -m unittest discover -s ".cursor/skills/game-early-experience-breakdown/tests" -p "test_video_analysis_pipeline.py" -v
```

Expected: PASS。

### Task 2: 写入寒霜 16 个小 LOOP

**Files:**
- Modify: `.cursor/tmp/frost-breakdown/analysis.final.validated.json`
- Modify: `.cursor/skills/game-early-experience-breakdown/tests/test_video_analysis_pipeline.py`

- [ ] **Step 1: 写寒霜数量与顺序 RED 测试**

```python
micro_loops = [
    node for node in data["global_loops"]["nodes"]
    if node["type"] == "micro_loop"
]
self.assertEqual(16, len(micro_loops))
self.assertEqual(
    {"settlement": 11, "expedition": 3, "hero_growth": 2},
    Counter(node["macro_loop_id"] for node in micro_loops),
)
self.assertEqual(
    [
        "settlement-survival-landing",
        "legacy-transition",
        "settlement-legacy-start",
        "settlement-build-queue",
        "settlement-infrastructure",
        "settlement-production-unlock",
        "settlement-expedition-ready",
        "expedition-first-sortie",
        "hero-recruit-and-deploy",
        "settlement-expedition-reinvest",
        "expedition-second-launch",
        "hero-post-battle-growth",
        "expedition-ice-river-push",
        "settlement-return-cleanup",
        "settlement-heating-production",
        "settlement-cold-policy",
        "settlement-resource-sprint",
        "main-city-end",
    ],
    [node["id"] for node in data["global_loops"]["nodes"][:-1]],
)
```

同时断言 `macro_return` 与 `cross_macro` 均存在，P8/P9 边界不变。

- [ ] **Step 2: 迁移真实数据**

按规格文件第 3 节写入：

- 11 个聚落小 LOOP。
- 3 个主体远征小 LOOP。
- 2 个英雄小 LOOP。
- 比尔遗志、主城解锁两个主体线性节点。
- 1 个 SLG 图外出口。

每个小 LOOP 使用已复核时间片中的直接图片；四段描述具体事件，不写系统级泛化词。

- [ ] **Step 3: 写入关系**

`primary` 串联完整时间主链；至少包含以下 `cross_macro`：

```text
出征前集中扩建 → 首次出征
首次出征 → 英雄招募入队
首次出征 → 远征收益回投
英雄招募入队 → 第二次远征
第二次远征 → 战后养成整理
战后养成整理 → 冰河连续战斗
冰河连续战斗 → 战后返乡清理
```

为聚落、远征和英雄被打断后的再次出现添加 `macro_return`。

- [ ] **Step 4: 校验 JSON**

```powershell
py -3 ".cursor/skills/game-early-experience-breakdown/scripts/analysis_model.py" `
  ".cursor/tmp/frost-breakdown/analysis.final.validated.json" `
  --output ".cursor/tmp/frost-breakdown/analysis.final.validated.json"
```

Expected: exit 0。

### Task 3: 实现分层纯视图模型

**Files:**
- Modify: `.cursor/skills/game-early-experience-breakdown/tests/test_viewer_builder.py`
- Modify: `.cursor/skills/game-early-experience-breakdown/assets/viewer.js`

- [ ] **Step 1: 写 RED 纯函数测试**

新增测试：

```python
model = self.run_node(
    f"viewer.hierarchicalLoopsViewModel({json.dumps(data, ensure_ascii=False)},"
    "[true,true],viewer.defaultMacroLoopVisibility())"
)
self.assertEqual(16, len([
    node for node in model["nodes"] if node["type"] == "micro_loop"
]))
self.assertEqual(
    ["动机", "行为", "奖励", "下一动机"],
    [part["label"] for part in model["nodes"][0]["parts"]],
)
```

另测：

- 连续同归属节点合成一个 segment。
- 被打断后形成新 segment。
- 大 LOOP 关闭后节点只 `dimmed`，不删除、不重排。
- 关系标签输出“起点 → 终点：说明”。
- 全部动态文本安全转义。

- [ ] **Step 2: 运行 RED**

```powershell
py -3 -m unittest discover -s ".cursor/skills/game-early-experience-breakdown/tests" -p "test_viewer_builder.py" -k "hierarchical_loop" -v
```

Expected: FAIL，函数不存在。

- [ ] **Step 3: 实现纯函数**

实现并导出：

```javascript
defaultMacroLoopVisibility()
updateMacroLoopVisibility(current, action)
hierarchicalLoopsViewModel(data, visibleSlices, macroVisibility)
macroLoopSegments(nodes)
hierarchicalLoopsMarkup(model)
hierarchicalLoopTooltipMarkup(node, partKey)
hierarchicalLoopConnectorSvg(model, anchors, width, height)
```

小 LOOP `parts` 固定为四段；行为数组在行为节点内分行显示。segment 只合并时间主链中连续且
`macro_loop_id` 相同的节点。

- [ ] **Step 4: 运行 GREEN**

执行 Step 2 命令，Expected: PASS。

### Task 4: 改造 HTML、CSS 与交互

**Files:**
- Modify: `.cursor/skills/game-early-experience-breakdown/assets/viewer.html`
- Modify: `.cursor/skills/game-early-experience-breakdown/assets/viewer.css`
- Modify: `.cursor/skills/game-early-experience-breakdown/assets/viewer.js`
- Modify: `.cursor/skills/game-early-experience-breakdown/tests/test_viewer_builder.py`

- [ ] **Step 1: 写布局和交互 RED 测试**

断言：

- `global-loop-section` 仍位于详情后且为最后一部分。
- 顶部存在 `global-loop-legend`。
- 每个小 LOOP 行包含时间、宏标签和四段节点。
- CSS 有三种 segment 色带和 `.macro-loop-dimmed`。
- 桌面四段为七列网格（四段加三箭头）。
- `max-width:720px` 下改为一列。
- Escape、Enter/Space、筛选禁用和 ResizeObserver 保留。

- [ ] **Step 2: 运行 RED**

执行 Task 3 Step 2 命令，Expected: FAIL。

- [ ] **Step 3: 修改模板和样式**

在现有 LOOP section 中增加：

```html
<div id="global-loop-legend" class="global-loop-legend" aria-label="大 LOOP 筛选"></div>
```

桌面结构：

```text
时间/标题 | 动机 → 行为 → 奖励 → 下一动机
```

segment 使用同色半透明背景和左侧宏标签；`macro_return` 使用同色虚线轨道。跨环 SVG 位于背景与节点
之间，从奖励/下一动机锚点连接到目标动机锚点。

- [ ] **Step 4: 接入状态和事件**

`state` 增加 `macroLoopVisibility`。图例点击仅切换淡化状态并重绘，不修改 `state.visible`。
小 LOOP 行点击、Enter/Space 跳转首个可见关联片；四段节点悬停/聚焦显示对应解释与证据图。

移动端隐藏大范围 SVG，关系标签显示完整起终点。单区渲染错误不阻断页面其他部分。

- [ ] **Step 5: 运行完整 Viewer 测试**

```powershell
py -3 -m unittest discover -s ".cursor/skills/game-early-experience-breakdown/tests" -p "test_viewer_builder.py" -v
```

Expected: PASS。

### Task 5: 同步文档

**Files:**
- Modify: `.cursor/skills/game-early-experience-breakdown/SKILL.md`
- Modify: `.cursor/skills/game-early-experience-breakdown/reference.md`
- Modify: `session/requirements/game-early-experience-breakdown.md`
- Modify: `session/session.md`

- [ ] **Step 1: 更新 Skill 和 reference**

删除“三个大 LOOP 各一张四格卡”的旧口径，固定：

- 小 LOOP 可观察闭环判定。
- 每个小 LOOP 唯一主归属。
- 大 LOOP 分段色带与跨环关系。
- 16 个寒霜主体小 LOOP。
- 旧 analysis 需迁移。

- [ ] **Step 2: 更新需求与会话记录**

记录颗粒度错误原因、参考图层级含义、分层数据契约和飞书未修改。

- [ ] **Step 3: 运行文档测试**

```powershell
py -3 -m unittest discover -s ".cursor/skills/game-early-experience-breakdown/tests" -p "test_skill_docs.py" -v
```

Expected: PASS。

### Task 6: 重建、浏览器验收和最终审查

**Files:**
- Regenerate: `artifacts/frost-early-experience/viewer/index.html`
- Regenerate: `artifacts/frost-early-experience/viewer/data.json`

- [ ] **Step 1: 重建 Viewer**

```powershell
py -3 ".cursor/skills/game-early-experience-breakdown/scripts/build_viewer.py" `
  ".cursor/tmp/frost-breakdown/analysis.final.validated.json" `
  --output-dir "artifacts/frost-early-experience/viewer"
```

Expected: exit 0。

- [ ] **Step 2: 运行完整测试与 lints**

```powershell
py -3 -m unittest discover -s ".cursor/skills/game-early-experience-breakdown/tests" -v
```

Expected: 全部通过；只允许既有 Windows symlink 权限用例跳过，IDE 无新增诊断。

- [ ] **Step 3: 桌面浏览器验收**

1440px 验证：

- 16 个小 LOOP 和 2 个主体线性节点按时间排序。
- 不再出现三张巨型系统四格卡。
- 三种分段色带、`macro_return` 和 `cross_macro` 清晰。
- 图例只淡化，不删除或重排。
- Tooltip、点击、键盘、筛选禁用正常。
- 无横向溢出。

- [ ] **Step 4: 移动端验收**

390px 验证四段纵向排列、关系文本完整、Tooltip 在视口内且无横向溢出。

- [ ] **Step 5: 单次最终代码审查**

重点检查：

- 是否把系统步骤再次误拆为 LOOP。
- 16 个小 LOOP 是否均有即时奖励和下一动机证据。
- 大 LOOP 归属、回流和跨环端点是否正确。
- XSS、证据路径重写、筛选、键盘和移动端是否回归。
- 飞书是否保持未修改。

修复 Critical/Important 后重新执行 Steps 1–4。
