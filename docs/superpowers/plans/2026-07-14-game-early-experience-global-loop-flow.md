# 游戏前期体验全局 LOOP 流程 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在游戏前期体验 HTML 最后增加可追溯、可交互的全局 LOOP 流程，用动机、行为、奖励和下一动机展示寒霜进入 SLG 大地图前的核心闭环。

**Architecture:** 在统一 `analysis.json` 根节点新增 `global_loops`，由 Python 校验器验证边界、节点、证据和图连通性。Viewer 使用纯函数生成 LOOP 视图模型与安全 HTML，再用 CSS Grid 和本地 SVG 连线实现响应式流程；事件层复用现有时间片筛选与详情选择。寒霜数据只基于已验证时间片和截图聚合，P8 为主体终点，P9 只作图外出口。

**Tech Stack:** Python 3 `unittest`、原生 JavaScript、HTML/CSS、内联 SVG、现有 `build_viewer.py`。

**Execution note:** 当前工作区包含本功能前序未提交改动，直接在现有工作区实施并避免覆盖无关文件。除非用户另行明确要求，本计划不创建 Git commit。

---

## File responsibility map

- `.cursor/skills/game-early-experience-breakdown/scripts/analysis_model.py`：`global_loops` 数据契约和图连通性校验。
- `.cursor/skills/game-early-experience-breakdown/tests/test_video_analysis_pipeline.py`：有效/无效 LOOP 契约测试。
- `.cursor/skills/game-early-experience-breakdown/assets/viewer.js`：LOOP 视图模型、安全标记、筛选状态、Tooltip、点击联动和 SVG 连线。
- `.cursor/skills/game-early-experience-breakdown/assets/viewer.html`：页面末尾 LOOP 区域、Tooltip 和错误容器。
- `.cursor/skills/game-early-experience-breakdown/assets/viewer.css`：色块语义、流程布局、响应式和可访问状态。
- `.cursor/skills/game-early-experience-breakdown/tests/test_viewer_builder.py`：纯函数、模板、CSS、交互和响应式测试。
- `.cursor/tmp/frost-breakdown/analysis.final.validated.json`：寒霜三个核心 LOOP 与线性入口/出口事实。
- `.cursor/skills/game-early-experience-breakdown/SKILL.md`、`reference.md`：固定分析和交付口径。
- `session/requirements/game-early-experience-breakdown.md`、`session/session.md`：需求与变更记录。
- `artifacts/frost-early-experience/viewer/`：重建后的本地交付。

### Task 1: 建立 `global_loops` 数据契约

**Files:**
- Modify: `.cursor/skills/game-early-experience-breakdown/tests/test_video_analysis_pipeline.py`
- Modify: `.cursor/skills/game-early-experience-breakdown/scripts/analysis_model.py`

- [ ] **Step 1: 在测试辅助数据中加入最小有效流程**

新增 `valid_global_loops(slices)`，使用一个入口、一个 LOOP 和一个终点；通用测试数据不强制制造
视频范围外出口，寒霜数据再单独覆盖该节点：

```python
def valid_global_loops(slices):
    frame0 = slices[0]["main_frame"]["path"]
    return {
        "scope": {
            "start": 0.0,
            "end": float(slices[-1]["end"]),
            "end_label": "教学完成",
            "outside_exit_label": "进入下一玩法",
        },
        "chapters": [],
        "nodes": [
            {
                "id": "entry",
                "type": "entry",
                "title": "进入教学",
                "summary": "建立初始目标",
                "chapter_id": "",
                "slice_indices": [0],
                "evidence_frames": [frame0],
                "status": "confirmed",
            },
            {
                "id": "core-loop",
                "type": "loop",
                "title": "基础循环",
                "summary": "完成一次闭环",
                "chapter_id": "",
                "slice_indices": [0],
                "evidence_frames": [frame0],
                "status": "confirmed",
                "motivation": "完成目标",
                "behaviors": ["执行核心操作"],
                "reward": "获得反馈",
                "next_motivation": "追求下一目标",
                "accent": "settlement",
            },
            {
                "id": "end",
                "type": "end",
                "title": "教学完成",
                "summary": "抵达主体终点",
                "chapter_id": "",
                "slice_indices": [len(slices) - 1],
                "evidence_frames": [slices[-1]["main_frame"]["path"]],
                "status": "confirmed",
            },
        ],
        "edges": [
            {"from": "entry", "to": "core-loop", "kind": "primary", "label": "进入循环"},
            {"from": "core-loop", "to": "end", "kind": "primary", "label": "完成教学"},
        ],
    }
```

在 `valid_analysis()` 返回值中加入 `"global_loops": valid_global_loops(slices)`。

- [ ] **Step 2: 写契约失败测试**

增加测试覆盖：

```python
def test_global_loops_is_required_and_valid_graph_passes(self):
    data = valid_analysis(120.0)
    analysis_model.validate_analysis(data)
    del data["global_loops"]
    with self.assertRaisesRegex(analysis_model.AnalysisValidationError, "global_loops"):
        analysis_model.validate_analysis(data)

def test_global_loop_requires_complete_player_cycle(self):
    data = valid_analysis()
    loop = next(node for node in data["global_loops"]["nodes"] if node["type"] == "loop")
    loop["behaviors"] = []
    with self.assertRaisesRegex(analysis_model.AnalysisValidationError, "behaviors|行为"):
        analysis_model.validate_analysis(data)

def test_global_loop_rejects_dangling_edges_and_unreachable_nodes(self):
    data = valid_analysis()
    data["global_loops"]["edges"][0]["to"] = "missing"
    with self.assertRaisesRegex(analysis_model.AnalysisValidationError, "连线|节点"):
        analysis_model.validate_analysis(data)

def test_global_loop_evidence_must_belong_to_referenced_slice(self):
    data = valid_analysis(120.0)
    data["global_loops"]["nodes"][0]["evidence_frames"] = [
        data["slices"][1]["main_frame"]["path"]
    ]
    with self.assertRaisesRegex(analysis_model.AnalysisValidationError, "证据|时间片"):
        analysis_model.validate_analysis(data)
```

另加参数化用例覆盖重复 ID、非法枚举、章节越界/重叠、主体节点越过 scope、缺少入口到终点主路径、
孤立节点，以及在 120 秒双时间片数据中创建 `outside_exit` 后使用非 `conditional` 边。

- [ ] **Step 3: 运行 RED 测试**

Run:

```powershell
py -3 -m unittest discover -s ".cursor/skills/game-early-experience-breakdown/tests" -p "test_video_analysis_pipeline.py" -k "global_loop" -v
```

Expected: FAIL，提示缺少 `global_loops` 校验或测试辅助数据尚未满足新契约。

- [ ] **Step 4: 实现校验器**

在 `analysis_model.py` 增加：

```python
GLOBAL_LOOP_NODE_TYPES = ("entry", "transition", "loop", "end", "outside_exit")
GLOBAL_LOOP_STATUSES = ("confirmed", "pending_confirmation")
GLOBAL_LOOP_ACCENTS = ("settlement", "expedition", "hero_growth")
GLOBAL_LOOP_EDGE_KINDS = ("primary", "feedback", "conditional")
```

实现 `_validate_global_loops(value, slices, duration)`，按以下顺序校验：

1. `scope/chapters/nodes/edges` 必填且类型正确。
2. `scope.start/end` 位于视频内；标签非空。
3. 章节 ID 唯一、范围位于 scope 内、按时间排序且不重叠。
4. 节点公共字段完整；`slice_indices` 为非空、无重复、有效整数数组。
5. 主体节点关联时间片必须完全位于 scope；`outside_exit` 允许引用 scope 后首片。
6. 每条 `evidence_frames` 路径必须属于任一关联 slice 的主图或证据图。
7. LOOP 的四段闭环文本非空、`behaviors` 非空、`accent` 合法；非 LOOP 禁止这些字段。
8. 边起终点存在，枚举合法，不允许重复边；`outside_exit` 只接受从 `end` 发出的 `conditional` 边。
9. 从唯一入口沿 `primary` 边可到达唯一主体终点；所有主体节点可从入口经任意主体边到达。

在 `validate_analysis()` 中改为：

```python
_require_keys(root, ("video", "slices", "global_curves", "global_loops"), "analysis")
# 完成 slices 和 global_curves 校验后
_validate_global_loops(root["global_loops"], slices, duration)
```

- [ ] **Step 5: 运行 GREEN 与全模型测试**

Run:

```powershell
py -3 -m unittest discover -s ".cursor/skills/game-early-experience-breakdown/tests" -p "test_video_analysis_pipeline.py" -v
```

Expected: PASS。

### Task 2: 实现 LOOP 纯视图模型和安全标记

**Files:**
- Modify: `.cursor/skills/game-early-experience-breakdown/tests/test_viewer_builder.py`
- Modify: `.cursor/skills/game-early-experience-breakdown/assets/viewer.js`

- [ ] **Step 1: 写纯函数 RED 测试**

在 `ViewerJavascriptBehaviorTests` 中增加：

```python
def test_global_loop_view_model_keeps_semantics_and_filter_state(self):
    data = valid_analysis(120)
    model = self.run_node(
        f"viewer.globalLoopsViewModel({json.dumps(data, ensure_ascii=False)}, [true, false])"
    )
    loop = next(node for node in model["nodes"] if node["type"] == "loop")
    self.assertEqual(["动机", "行为", "奖励", "下一动机"], [part["label"] for part in loop["parts"]])
    self.assertFalse(loop["disabled"])

def test_global_loop_markup_escapes_text_and_has_semantic_colors(self):
    data = valid_analysis()
    loop = next(node for node in data["global_loops"]["nodes"] if node["type"] == "loop")
    loop["motivation"] = "<img src=x onerror=bad()>"
    html = self.run_node(
        f"viewer.globalLoopsMarkup(viewer.globalLoopsViewModel("
        f"{json.dumps(data, ensure_ascii=False)}, [true]))"
    )
    self.assertNotIn("<img", html)
    self.assertIn("&lt;img src=x onerror=bad()&gt;", html)
    for hook in ("loop-accent-settlement", "loop-part-motivation",
                 "loop-part-behavior", "loop-part-reward", "loop-part-next"):
        self.assertIn(hook, html)
```

增加断言覆盖 `entry/transition/end/outside_exit`、`feedback/conditional` 连线、关联时间、证据图、
被筛选时间片全部隐藏时的 `aria-disabled="true"`。

- [ ] **Step 2: 运行 RED 测试**

Run:

```powershell
py -3 -m unittest discover -s ".cursor/skills/game-early-experience-breakdown/tests" -p "test_viewer_builder.py" -k "global_loop" -v
```

Expected: FAIL，提示 `globalLoopsViewModel` 或 `globalLoopsMarkup` 不存在。

- [ ] **Step 3: 实现纯函数**

在 `viewer.js` 的 CommonJS 导出分支之前实现并导出：

```javascript
function globalLoopInteractionState(sliceIndices, visible) {
  const enabledIndex = sliceIndices.find((index) => visible[index]);
  return { disabled: enabledIndex === undefined, primarySlice: enabledIndex ?? sliceIndices[0] };
}

function globalLoopsViewModel(data, visible) {
  const graph = data.global_loops;
  return {
    ...graph,
    nodes: graph.nodes.map((node) => {
      const interaction = globalLoopInteractionState(node.slice_indices, visible);
      return {
        ...node,
        ...interaction,
        timeLabel: node.slice_indices
          .map((index) => `${formatTime(data.slices[index].start)}–${formatTime(data.slices[index].end)}`)
          .join(" / "),
        evidence: node.evidence_frames,
        parts: node.type === "loop" ? [
          { key: "motivation", label: "动机", values: [node.motivation] },
          { key: "behavior", label: "行为", values: node.behaviors },
          { key: "reward", label: "奖励", values: [node.reward] },
          { key: "next", label: "下一动机", values: [node.next_motivation] },
        ] : [],
      };
    }),
  };
}
```

实现 `globalLoopsMarkup(model)`、`globalLoopTooltipMarkup(node)` 和
`globalLoopConnectorModel(containerRect, nodeRects, edges)`。所有文本和路径属性使用 `escapeHtml`，
节点使用 `data-loop-node`、`data-loop-slice`、`tabindex`、`role="button"` 和 `aria-disabled`。

- [ ] **Step 4: 运行 GREEN 测试**

执行 Step 2 命令，Expected: PASS。

### Task 3: 增加页面末尾流程区、布局和事件联动

**Files:**
- Modify: `.cursor/skills/game-early-experience-breakdown/assets/viewer.html`
- Modify: `.cursor/skills/game-early-experience-breakdown/assets/viewer.css`
- Modify: `.cursor/skills/game-early-experience-breakdown/assets/viewer.js`
- Modify: `.cursor/skills/game-early-experience-breakdown/tests/test_viewer_builder.py`

- [ ] **Step 1: 写模板和 CSS RED 测试**

测试必须断言 LOOP section 位于 `detail-panel` 之后：

```python
template = (ROOT / "assets" / "viewer.html").read_text(encoding="utf-8")
self.assertLess(template.index('id="detail-panel"'), template.index('id="global-loop-section"'))
self.assertIn('id="global-loop-canvas"', template)
self.assertIn('id="global-loop-tooltip"', template)
```

CSS 断言必须覆盖：

- `.loop-accent-settlement`、`.loop-accent-expedition`、`.loop-accent-hero-growth`
- `.loop-part-motivation`、`.loop-part-behavior`、`.loop-part-reward`、`.loop-part-next`
- `.global-loop-tooltip { overflow: visible; }` 的外层策略
- `@media (max-width: 720px)` 下 LOOP parts 改为单列
- `body` 无横向溢出

- [ ] **Step 2: 运行 RED 测试**

执行 Task 2 Step 2 命令，Expected: FAIL。

- [ ] **Step 3: 增加模板**

在 `</section><!-- detail-panel -->` 后、`</main>` 前加入：

```html
<section id="global-loop-section" class="global-loop-section" aria-labelledby="global-loop-title">
  <div class="section-heading">
    <div><p class="eyebrow">GLOBAL GAMEPLAY LOOPS</p><h2 id="global-loop-title">全局 LOOP 流程</h2></div>
    <p class="muted">动机 → 行为 → 奖励 → 下一动机</p>
  </div>
  <div id="global-loop-canvas" class="global-loop-canvas"></div>
  <div id="global-loop-tooltip" class="global-loop-tooltip" role="tooltip" hidden></div>
  <p id="global-loop-error" class="global-loop-error" hidden></p>
</section>
```

- [ ] **Step 4: 实现 CSS**

使用 CSS 自定义属性实现稳定语义：

```css
.global-loop-section { position: relative; min-width: 0; overflow: visible; }
.global-loop-canvas { position: relative; display: grid; gap: 18px; overflow: visible; }
.global-loop-card { border: 1px solid var(--loop-accent); border-radius: 14px; padding: 16px; }
.loop-accent-settlement { --loop-accent: #45c7d8; --loop-bg: #123841; }
.loop-accent-expedition { --loop-accent: #ff8a5b; --loop-bg: #40251f; }
.loop-accent-hero-growth { --loop-accent: #aa82ff; --loop-bg: #2d2445; }
.loop-part-motivation { --part-color: #f4c95d; }
.loop-part-behavior { --part-color: #818cf8; }
.loop-part-reward { --part-color: #58d68d; }
.loop-part-next { --part-color: #f4c95d; border-style: dashed; }
.global-loop-connectors { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }
```

桌面 LOOP parts 使用四列；`max-width: 720px` 改为单列并隐藏跨卡片 SVG 曲线，改用卡片间方向提示，
保证无横向页面滚动。

- [ ] **Step 5: 接入渲染和事件**

在 `initialize(data)` 和 `applyFilters()` 后调用 `renderGlobalLoops()`。实现：

- 使用 `state.visible` 生成模型。
- 渲染节点后读取 DOMRect，调用 connector model 生成 SVG。
- `ResizeObserver` 只在尺寸变化时重画连接线，并恢复当前键盘焦点。
- `pointerover/focusin` 显示流程 Tooltip；`pointerleave/focusout/Escape` 关闭。
- 点击或 Enter/Space 调用 `selectSlice(primarySlice)`，随后
  `byId("detail-panel").scrollIntoView({ block: "start", behavior: "smooth" })`。
- 禁用节点不响应点击，不清空筛选。
- 单个流程区错误写入 `global-loop-error`，不阻塞其他页面区域。

- [ ] **Step 6: 运行 Viewer 测试**

Run:

```powershell
py -3 -m unittest discover -s ".cursor/skills/game-early-experience-breakdown/tests" -p "test_viewer_builder.py" -v
```

Expected: PASS。

### Task 4: 写入寒霜真实流程数据

**Files:**
- Modify: `.cursor/tmp/frost-breakdown/analysis.final.validated.json`
- Test: `.cursor/skills/game-early-experience-breakdown/tests/test_video_analysis_pipeline.py`

- [ ] **Step 1: 增加寒霜数据回归测试**

读取寒霜 JSON 并断言：

```python
self.assertEqual(1500, data["global_loops"]["scope"]["end"])
loops = [node for node in data["global_loops"]["nodes"] if node["type"] == "loop"]
self.assertEqual(
    {"settlement", "expedition", "hero_growth"},
    {node["accent"] for node in loops},
)
self.assertTrue(any(
    edge["kind"] == "feedback"
    and edge["from"] == "expedition-loop"
    and edge["to"] == "settlement-loop"
    for edge in data["global_loops"]["edges"]
))
```

- [ ] **Step 2: 写入节点与证据**

写入以下主体结构，文案必须以现有时间片内容为准：

1. `survival-entry`：暴风雪求生和落脚。
2. `bill-legacy-transition`：比尔去世、继承避难所蓝图。
3. `settlement-loop`：建设、派遣、生产。
4. `expedition-loop`：编队出征和战斗。
5. `hero-growth-loop`：招募、编队、养成和奖励整理。
6. `cold-policy-transition`：极寒法令与设施升级。
7. `main-city-end`：P8 完整主城解锁。
8. `slg-outside-exit`：P9 进入 SLG 大地图，`pending_confirmation`。

主路径按上述顺序连接；另加：

- `settlement-loop → expedition-loop`：建设支撑出征。
- `expedition-loop → settlement-loop`：战利回投建设，`feedback`。
- `expedition-loop → hero-growth-loop`：强敌触发养成。
- `hero-growth-loop → expedition-loop`：强化后再出征，`feedback`。
- `main-city-end → slg-outside-exit`：`conditional`。

每个节点引用实际关联 slice 的主图或证据图，不新增无来源路径。

- [ ] **Step 3: 校验寒霜 JSON**

Run:

```powershell
py -3 ".cursor/skills/game-early-experience-breakdown/scripts/analysis_model.py" `
  ".cursor/tmp/frost-breakdown/analysis.final.validated.json" `
  --output ".cursor/tmp/frost-breakdown/analysis.final.validated.json"
```

Expected: exit 0，UTF-8 JSON 原子写回。

### Task 5: 同步 Skill 和需求文档

**Files:**
- Modify: `.cursor/skills/game-early-experience-breakdown/SKILL.md`
- Modify: `.cursor/skills/game-early-experience-breakdown/reference.md`
- Modify: `session/requirements/game-early-experience-breakdown.md`
- Modify: `session/session.md`

- [ ] **Step 1: 更新 Skill 固定规则**

明确：

- `global_loops` 必填。
- LOOP 只用于完整玩家闭环，不把一次性教学或剧情强行循环化。
- HTML 最后一部分固定展示全局 LOOP 流程。
- 主体边界由项目分析确定；寒霜以 P8 主城解锁结束，SLG 入口在图外。

- [ ] **Step 2: 更新 reference 契约**

写入 `scope/chapters/nodes/edges` 的字段、枚举、证据和连通性规则，并记录色块语义与响应式要求。

- [ ] **Step 3: 更新需求与会话记录**

记录本次新增数据契约、三个寒霜 LOOP、页面末尾布局和飞书未修改。

- [ ] **Step 4: 运行文档测试**

Run:

```powershell
py -3 -m unittest discover -s ".cursor/skills/game-early-experience-breakdown/tests" -p "test_skill_docs.py" -v
```

Expected: PASS。

### Task 6: 重建交付并完整验收

**Files:**
- Regenerate: `artifacts/frost-early-experience/viewer/index.html`
- Regenerate: `artifacts/frost-early-experience/viewer/data.json`
- Regenerate: `artifacts/frost-early-experience/viewer/screenshots/`

- [ ] **Step 1: 重建 Viewer**

Run:

```powershell
py -3 ".cursor/skills/game-early-experience-breakdown/scripts/build_viewer.py" `
  ".cursor/tmp/frost-breakdown/analysis.final.validated.json" `
  --output-dir "artifacts/frost-early-experience/viewer"
```

Expected: exit 0。

- [ ] **Step 2: 运行完整测试**

Run:

```powershell
py -3 -m unittest discover -s ".cursor/skills/game-early-experience-breakdown/tests" -v
```

Expected: 全部通过；Windows 无符号链接权限时只允许既有 symlink 用例跳过。

- [ ] **Step 3: 检查修改文件诊断**

对 `analysis_model.py`、`viewer.js`、`viewer.css`、`viewer.html` 和两份测试读取 IDE lints。
Expected: 不新增诊断。

- [ ] **Step 4: 桌面浏览器验收**

通过本地 HTTP 服务打开 Viewer，在 1440px 宽度验证：

- LOOP section 位于详情之后且为页面最后一部分。
- 三个 LOOP 色块、四类内部角色和跨 LOOP 箭头均清晰。
- Tooltip 文本和证据图不裁切。
- 点击三个 LOOP 分别跳转正确时间片详情。
- 应用筛选后，无可见关联片的节点置灰且不能跳转。
- P8 是金色主体终点，P9 是图外虚线出口。
- `document.documentElement.scrollWidth === document.documentElement.clientWidth`。

- [ ] **Step 5: 移动端浏览器验收**

在 390px 宽度验证 LOOP parts 纵向排列、文本完整、无横向滚动、Tooltip 在视口内、键盘/点击状态无回归。

- [ ] **Step 6: 最终单次代码审查**

使用代码审查检查：

- 契约是否允许悬空、孤立或越界图。
- 寒霜动机/行为/奖励是否有现有证据。
- Viewer 是否存在未转义文本、遮挡连线、ResizeObserver 循环或筛选绕过。
- 本轮是否意外修改飞书输出。

修正明确问题后重新执行 Steps 1–5；不扩展到未请求功能。
