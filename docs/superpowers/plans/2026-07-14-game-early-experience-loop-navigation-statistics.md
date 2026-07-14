# 游戏前期体验 LOOP 跳转与去重统计 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为时间片详情增加关联小 LOOP 定位，移除 LOOP 悬浮窗，并按人工维护的玩法闭环类型展示去重数、出现次数和强化次数。

**Architecture:** `global_loops` 增加 `loop_families`，每个 `micro_loop` 通过唯一 `loop_family_id` 归类；寒霜把“供暖生产”拆为两个节点，形成 17 个事件级小 LOOP。Viewer 从统一图数据派生统计和详情导航，不维护手填计数；详情标签通过节点 ID 定位卡片，LOOP Tooltip 整体删除。

**Tech Stack:** Python 3 `unittest`、原生 JavaScript、HTML/CSS、现有 `analysis_model.py` 与 `build_viewer.py`。

**Execution note:** 在当前功能分支和现有未提交工作区内继续实施；除非用户明确要求，不创建 Git commit，不修改飞书。

---

### Task 1: 增加小 LOOP 类型数据契约

**Files:**
- Modify: `.cursor/skills/game-early-experience-breakdown/tests/test_video_analysis_pipeline.py`
- Modify: `.cursor/skills/game-early-experience-breakdown/scripts/analysis_model.py`

- [ ] **Step 1: 迁移测试夹具**

在 `valid_global_loops()` 中增加：

```python
"loop_families": [
    {
        "id": "building_growth",
        "title": "建筑升级养成",
        "summary": "通过建设和升级提高聚落能力",
        "accent": "building_growth",
    }
],
```

并给默认小 LOOP 增加：

```python
"loop_family_id": "building_growth",
```

- [ ] **Step 2: 写 RED 契约测试**

增加以下测试：

```python
def test_global_loop_requires_valid_used_loop_families(self):
    data = valid_analysis()
    del data["global_loops"]["loop_families"]
    with self.assertRaisesRegex(
        analysis_model.AnalysisValidationError, "loop_families"
    ):
        analysis_model.validate_analysis(data)

    data = valid_analysis()
    data["global_loops"]["loop_families"][0]["accent"] = "unknown"
    with self.assertRaisesRegex(
        analysis_model.AnalysisValidationError, "accent"
    ):
        analysis_model.validate_analysis(data)

    data = valid_analysis()
    data["global_loops"]["loop_families"].append(
        {
            "id": "unused",
            "title": "未使用",
            "summary": "没有节点引用",
            "accent": "law_system",
        }
    )
    with self.assertRaisesRegex(
        analysis_model.AnalysisValidationError, "未使用|引用"
    ):
        analysis_model.validate_analysis(data)
```

```python
def test_micro_loop_requires_single_existing_family(self):
    data = valid_analysis()
    del data["global_loops"]["nodes"][1]["loop_family_id"]
    with self.assertRaisesRegex(
        analysis_model.AnalysisValidationError, "loop_family_id"
    ):
        analysis_model.validate_analysis(data)

    data = valid_analysis()
    data["global_loops"]["nodes"][1]["loop_family_id"] = "missing"
    with self.assertRaisesRegex(
        analysis_model.AnalysisValidationError, "loop_family_id"
    ):
        analysis_model.validate_analysis(data)

    data = valid_analysis()
    data["global_loops"]["nodes"][0]["loop_family_id"] = "building_growth"
    with self.assertRaisesRegex(
        analysis_model.AnalysisValidationError, "micro_loop|loop_family_id"
    ):
        analysis_model.validate_analysis(data)
```

- [ ] **Step 3: 运行 RED**

```powershell
py -3 -m unittest discover -s ".cursor/skills/game-early-experience-breakdown/tests" -p "test_video_analysis_pipeline.py" -k "loop_famil" -v
```

Expected: FAIL，原因是校验器尚未识别新字段。

- [ ] **Step 4: 实现最小校验**

在 `analysis_model.py` 增加：

```python
GLOBAL_LOOP_FAMILY_ACCENTS = (
    "building_growth",
    "building_production",
    "expedition_progression",
    "hero_growth",
    "law_system",
    "heating_boost",
)
```

新增 `_validate_loop_families()`：

```python
def _validate_loop_families(value: Any) -> dict[str, dict[str, Any]]:
    families = value
    if not isinstance(families, list) or not families:
        _fail("global_loops.loop_families 必须是非空数组")
    family_by_id: dict[str, dict[str, Any]] = {}
    used_accents: set[str] = set()
    for index, raw_family in enumerate(families):
        location = f"global_loops.loop_families[{index}]"
        family = _require_object(raw_family, location)
        _require_keys(family, ("id", "title", "summary", "accent"), location)
        for field in ("id", "title", "summary"):
            _nonempty_text(family[field], f"{location}.{field}")
        if family["id"] in family_by_id:
            _fail(f"{location}.id 不允许重复")
        if family["accent"] not in GLOBAL_LOOP_FAMILY_ACCENTS:
            _fail(
                f"{location}.accent 只允许: "
                f"{', '.join(GLOBAL_LOOP_FAMILY_ACCENTS)}"
            )
        if family["accent"] in used_accents:
            _fail(f"{location}.accent 不允许重复")
        family_by_id[family["id"]] = family
        used_accents.add(family["accent"])
    return family_by_id
```

在 `_validate_global_loops()` 中：

- 根字段增加 `loop_families`。
- `micro_fields` 增加 `loop_family_id`。
- 小 LOOP 强制引用 `family_by_id`。
- 非小 LOOP 禁止 `loop_family_id`。
- 完成节点遍历后，比较已定义和已引用类型集合，拒绝未使用类型。

- [ ] **Step 5: 运行 GREEN 与完整模型测试**

执行 Step 3 命令，再运行：

```powershell
py -3 -m unittest discover -s ".cursor/skills/game-early-experience-breakdown/tests" -p "test_video_analysis_pipeline.py" -v
```

Expected: PASS。

### Task 2: 将寒霜迁移为 17 个事件级小 LOOP

**Files:**
- Modify: `.cursor/tmp/frost-breakdown/analysis.final.validated.json`
- Modify: `.cursor/skills/game-early-experience-breakdown/tests/test_video_analysis_pipeline.py`

- [ ] **Step 1: 写寒霜分类与拆分 RED 测试**

更新寒霜测试：

```python
micro_loops = [
    node for node in graph["nodes"] if node["type"] == "micro_loop"
]
self.assertEqual(17, len(micro_loops))
self.assertEqual(
    {
        "building_growth": 8,
        "building_production": 2,
        "expedition_progression": 3,
        "hero_growth": 2,
        "law_system": 1,
        "heating_boost": 1,
    },
    dict(Counter(node["loop_family_id"] for node in micro_loops)),
)
self.assertNotIn(
    "settlement-heating-production",
    [node["id"] for node in graph["nodes"]],
)
self.assertLess(
    [node["id"] for node in graph["nodes"]].index(
        "settlement-building-production"
    ),
    [node["id"] for node in graph["nodes"]].index(
        "settlement-temporary-heating-boost"
    ),
)
```

断言主链包含：

```python
expected_pairs = {
    ("settlement-return-cleanup", "settlement-building-production"),
    (
        "settlement-building-production",
        "settlement-temporary-heating-boost",
    ),
    ("settlement-temporary-heating-boost", "settlement-cold-policy"),
}
```

- [ ] **Step 2: 运行 RED**

```powershell
py -3 -m unittest discover -s ".cursor/skills/game-early-experience-breakdown/tests" -p "test_video_analysis_pipeline.py" -k "frost_global_loops" -v
```

Expected: FAIL，当前仍为 16 个节点且没有类型归类。

- [ ] **Step 3: 写入六个类型**

在 Frost `global_loops` 增加六个 `loop_families`，顺序固定为：

```text
building_growth
building_production
expedition_progression
hero_growth
law_system
heating_boost
```

按规格为现有 15 个保留节点写入 `loop_family_id`。

- [ ] **Step 4: 拆分供暖节点**

删除 `settlement-heating-production`，增加：

```json
{
  "id": "settlement-building-production",
  "type": "micro_loop",
  "title": "极寒下的建筑生产",
  "summary": "在低温压力下确认资源缺口并安排生产。",
  "macro_loop_id": "settlement",
  "loop_family_id": "building_production",
  "slice_indices": [20],
  "evidence_frames": [
    "frames/slice-020-evidence-02-001235000.jpg"
  ],
  "status": "confirmed",
  "confidence": 0.78,
  "motivation": "极寒持续消耗资源，聚落需要补足稳定产出。",
  "behaviors": [
    "检查生产缺口",
    "安排建筑生产"
  ],
  "reward": "形成新的资源产出并缓解建设缺口。",
  "next_motivation": "低温仍在恶化，需要开启临时供暖强化。"
}
```

```json
{
  "id": "settlement-temporary-heating-boost",
  "type": "micro_loop",
  "title": "临时供暖强化",
  "summary": "面对失温风险开启临时供暖增益。",
  "macro_loop_id": "settlement",
  "loop_family_id": "heating_boost",
  "slice_indices": [20],
  "evidence_frames": [
    "frames/slice-020-main-001230000.jpg"
  ],
  "status": "confirmed",
  "confidence": 0.78,
  "motivation": "零下70度使幸存者面临失温风险。",
  "behaviors": [
    "查看低温警告",
    "开启临时供暖强化"
  ],
  "reward": "短期供暖能力提高，失温压力得到缓解。",
  "next_motivation": "继续通过法令和核心设施处理长期极寒。"
}
```

将主链改为：

```text
settlement-return-cleanup
→ settlement-building-production
→ settlement-temporary-heating-boost
→ settlement-cold-policy
```

- [ ] **Step 5: 校验 Frost 数据**

```powershell
py -3 ".cursor/skills/game-early-experience-breakdown/scripts/analysis_model.py" `
  ".cursor/tmp/frost-breakdown/analysis.final.validated.json" `
  --output ".cursor/tmp/frost-breakdown/analysis.final.validated.json"
```

Expected: exit 0。

- [ ] **Step 6: 运行 GREEN**

执行 Step 2 命令，Expected: PASS。

### Task 3: 实现 LOOP 去重统计与详情关联模型

**Files:**
- Modify: `.cursor/skills/game-early-experience-breakdown/tests/test_viewer_builder.py`
- Modify: `.cursor/skills/game-early-experience-breakdown/assets/viewer.js`

- [ ] **Step 1: 写统计 RED 测试**

```python
statistics = self.run_node(
    f"viewer.loopFamilyStatistics("
    f"{json.dumps(data['global_loops'], ensure_ascii=False)})"
)
self.assertEqual(17, statistics["eventCount"])
self.assertEqual(6, statistics["uniqueCount"])
self.assertEqual(
    [
        ["building_growth", 8, 7],
        ["building_production", 2, 1],
        ["expedition_progression", 3, 2],
        ["hero_growth", 2, 1],
        ["law_system", 1, 0],
        ["heating_boost", 1, 0],
    ],
    [
        [item["id"], item["occurrences"], item["reinforcements"]]
        for item in statistics["families"]
    ],
)
```

另测恶意标题被统计 markup 转义，且传入大 LOOP 可见性变化不会改变统计。

- [ ] **Step 2: 写详情关联 RED 测试**

```python
items = self.run_node(
    f"viewer.relatedMicroLoops("
    f"{json.dumps(model['nodes'], ensure_ascii=False)},20,"
    f"{json.dumps(visible)})"
)
self.assertEqual(
    [
        "settlement-building-production",
        "settlement-temporary-heating-boost",
    ],
    [item["id"] for item in items],
)
```

覆盖：

- 普通片返回一个关联小 LOOP。
- 供暖片返回两个。
- 比尔过渡片返回空数组。
- 所有关联片不可见时 `disabled: true`。
- 导航 markup 有标签和“当前时间片无关联 LOOP”空状态。

- [ ] **Step 3: 运行 RED**

```powershell
py -3 -m unittest discover -s ".cursor/skills/game-early-experience-breakdown/tests" -p "test_viewer_builder.py" -k "loop_family" -v
py -3 -m unittest discover -s ".cursor/skills/game-early-experience-breakdown/tests" -p "test_viewer_builder.py" -k "related_loop" -v
```

Expected: FAIL，纯函数不存在。

- [ ] **Step 4: 实现纯函数**

```javascript
function loopFamilyStatistics(graph) {
  const microLoops = graph.nodes.filter((node) => node.type === "micro_loop");
  const counts = microLoops.reduce((result, node) => {
    result[node.loop_family_id] = (result[node.loop_family_id] || 0) + 1;
    return result;
  }, {});
  const families = graph.loop_families
    .filter((family) => counts[family.id])
    .map((family) => ({
      ...family,
      occurrences: counts[family.id],
      reinforcements: Math.max(counts[family.id] - 1, 0)
    }));
  return {
    eventCount: microLoops.length,
    uniqueCount: families.length,
    families
  };
}
```

```javascript
function relatedMicroLoops(nodes, sliceIndex, visible) {
  return nodes
    .filter((node) =>
      node.type === "micro_loop" && node.slice_indices.includes(sliceIndex)
    )
    .map((node) => ({
      id: node.id,
      title: node.title,
      disabled: !node.slice_indices.some((index) => visible[index])
    }));
}
```

实现 `loopFamilyStatisticsMarkup()` 与 `relatedLoopNavigationMarkup()`，所有动态文本使用 `escapeHtml()`。

- [ ] **Step 5: 导出并运行 GREEN**

从 CommonJS 导出四个纯函数，执行 Step 3 命令，Expected: PASS。

### Task 4: 接入统计区、详情跳转并移除悬浮窗

**Files:**
- Modify: `.cursor/skills/game-early-experience-breakdown/assets/viewer.html`
- Modify: `.cursor/skills/game-early-experience-breakdown/assets/viewer.css`
- Modify: `.cursor/skills/game-early-experience-breakdown/assets/viewer.js`
- Modify: `.cursor/skills/game-early-experience-breakdown/tests/test_viewer_builder.py`

- [ ] **Step 1: 写结构与交互 RED 测试**

断言模板包含：

```html
<div id="related-loop-navigation" class="related-loop-navigation"></div>
<div id="global-loop-statistics" class="global-loop-statistics"></div>
```

断言不再包含：

```text
id="global-loop-tooltip"
global-loop-tooltip
hierarchicalLoopTooltipMarkup
showGlobalLoopTooltip
hideGlobalLoopTooltip
```

断言脚本包含：

```text
data-related-loop
scrollIntoView
loop-location-pulse
```

CSS 断言桌面统计可换行、移动端统计容器自身横向滚动、页面不增加横向溢出规则。

- [ ] **Step 2: 运行 RED**

```powershell
py -3 -m unittest discover -s ".cursor/skills/game-early-experience-breakdown/tests" -p "test_viewer_builder.py" -k "loop_navigation" -v
py -3 -m unittest discover -s ".cursor/skills/game-early-experience-breakdown/tests" -p "test_viewer_builder.py" -k "loop_statistics" -v
py -3 -m unittest discover -s ".cursor/skills/game-early-experience-breakdown/tests" -p "test_viewer_builder.py" -k "tooltip_removed" -v
```

Expected: FAIL。

- [ ] **Step 3: 修改模板**

详情 header 后增加：

```html
<div id="related-loop-navigation" class="related-loop-navigation"></div>
```

全局 LOOP 标题后、图例前增加：

```html
<div id="global-loop-statistics" class="global-loop-statistics"></div>
```

删除：

```html
<div id="global-loop-tooltip" class="global-loop-tooltip"
  role="tooltip" hidden></div>
```

- [ ] **Step 4: 接入渲染**

在 `renderGlobalLoops()` 成功路径中：

```javascript
byId("global-loop-statistics").innerHTML =
  loopFamilyStatisticsMarkup(loopFamilyStatistics(state.data.global_loops));
```

在 `renderSelected()` 的空结果和正常结果路径都调用：

```javascript
renderRelatedLoopNavigation();
```

新增：

```javascript
function renderRelatedLoopNavigation() {
  const container = byId("related-loop-navigation");
  if (!state.data || state.selectedIndex < 0 || !state.loopModel) {
    container.innerHTML = relatedLoopNavigationMarkup([]);
    return;
  }
  container.innerHTML = relatedLoopNavigationMarkup(
    relatedMicroLoops(
      state.loopModel.nodes,
      state.selectedIndex,
      state.visible
    )
  );
}
```

- [ ] **Step 5: 实现定位交互**

```javascript
function focusLoopNode(nodeId) {
  const target = document.querySelector(
    `[data-loop-node="${CSS.escape(nodeId)}"]`
  );
  if (!target) return;
  target.scrollIntoView({ behavior: "smooth", block: "center" });
  target.classList.remove("loop-location-pulse");
  requestAnimationFrame(() => target.classList.add("loop-location-pulse"));
  window.setTimeout(
    () => target.classList.remove("loop-location-pulse"),
    1400
  );
}
```

给 `related-loop-navigation` 增加点击与 Enter/Space 委托；禁用标签不激活。

- [ ] **Step 6: 完全移除 LOOP Tooltip**

删除：

- `hierarchicalLoopTooltipMarkup()`。
- `showGlobalLoopTooltip()` 与 `hideGlobalLoopTooltip()`。
- LOOP canvas 的悬停、聚焦、离开监听。
- document Escape 中 LOOP Tooltip 分支。
- `.global-loop-tooltip*` 与移动端 Tooltip CSS。

从 `globalLoopPartsMarkup()` 移除 `tabindex="0"`；小 LOOP article 的键盘激活保留。

- [ ] **Step 7: 添加样式**

增加：

```css
.related-loop-navigation { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
.related-loop-link { border: 1px solid var(--accent); border-radius: 999px; padding: 6px 10px; background: #18312f; color: var(--text); }
.related-loop-link[aria-disabled="true"] { cursor: not-allowed; opacity: .38; }
.loop-location-pulse { animation: loop-location-pulse 1.4s ease-out; }
@keyframes loop-location-pulse {
  0%, 35% { box-shadow: 0 0 0 4px #66e3c488, 0 0 28px #66e3c466; }
  100% { box-shadow: 0 0 0 0 transparent; }
}
.global-loop-statistics { display: grid; gap: 10px; margin: 14px 0; }
.loop-stat-summary { display: flex; flex-wrap: wrap; gap: 10px; }
.loop-family-stat-list { display: flex; flex-wrap: wrap; gap: 8px; }
```

移动端：

```css
.loop-family-stat-list {
  flex-wrap: nowrap;
  overflow-x: auto;
  padding-bottom: 4px;
}
.loop-family-stat { flex: 0 0 auto; }
```

- [ ] **Step 8: 运行完整 Viewer 测试**

```powershell
py -3 -m unittest discover -s ".cursor/skills/game-early-experience-breakdown/tests" -p "test_viewer_builder.py" -v
```

Expected: PASS。

### Task 5: 同步 Skill 与需求文档

**Files:**
- Modify: `.cursor/skills/game-early-experience-breakdown/SKILL.md`
- Modify: `.cursor/skills/game-early-experience-breakdown/reference.md`
- Modify: `session/requirements/game-early-experience-breakdown.md`
- Modify: `session/session.md`

- [ ] **Step 1: 更新 Skill 与 reference**

记录：

- `loop_families + loop_family_id` 严格契约。
- 人工语义去重，不做文本相似度推断。
- 出现次数和强化次数公式。
- 详情关联标签与多 LOOP 时间片。
- LOOP 悬浮窗已取消。
- 寒霜 17 个事件小 LOOP、6 类及固定统计。

- [ ] **Step 2: 更新需求与会话记录**

记录用户对分类的修正：

- 生产建筑归入建筑生产。
- 法令独立为法令系统。
- 临时供暖强化独立成环。
- 详情支持全部关联 LOOP 的正向跳转。

明确飞书未修改。

- [ ] **Step 3: 运行文档测试**

```powershell
py -3 -m unittest discover -s ".cursor/skills/game-early-experience-breakdown/tests" -p "test_skill_docs.py" -v
```

Expected: PASS。

### Task 6: 重建、浏览器验收与最终审查

**Files:**
- Regenerate: `artifacts/frost-early-experience/viewer/index.html`
- Regenerate: `artifacts/frost-early-experience/viewer/data.json`

- [ ] **Step 1: 校验并重建**

```powershell
py -3 ".cursor/skills/game-early-experience-breakdown/scripts/analysis_model.py" `
  ".cursor/tmp/frost-breakdown/analysis.final.validated.json" `
  --output ".cursor/tmp/frost-breakdown/analysis.final.validated.json"
```

```powershell
py -3 ".cursor/skills/game-early-experience-breakdown/scripts/build_viewer.py" `
  ".cursor/tmp/frost-breakdown/analysis.final.validated.json" `
  --output-dir "artifacts/frost-early-experience/viewer"
```

Expected: 两条命令 exit 0。

- [ ] **Step 2: 运行完整测试和 lints**

```powershell
py -3 -m unittest discover -s ".cursor/skills/game-early-experience-breakdown/tests" -v
```

Expected: 全部通过；只允许既有 Windows symlink 权限用例跳过。IDE 不新增诊断。

- [ ] **Step 3: 桌面浏览器验收**

1440px 验证：

- 17 个事件级小 LOOP、6 个去重类型。
- 总览显示 `17 / 6`。
- 六类次数为 `8/2/3/2/1/1`，强化为 `7/1/2/1/0/0`。
- 普通片显示一个关联标签。
- 供暖片显示两个关联标签，可分别定位两个卡片。
- 比尔过渡片显示无关联状态。
- 定位后短暂高亮，无常驻框。
- LOOP 悬浮窗不存在。
- 卡片反向跳转、键盘、大 LOOP 淡化、显示全部和关系线正常。

- [ ] **Step 4: 移动端浏览器验收**

390px 验证：

- 统计标签只在自身容器横向滚动。
- 页面无横向溢出。
- 详情关联标签可换行并可键盘激活。
- LOOP 主链和关系文字正常。

- [ ] **Step 5: 单次最终代码审查**

重点检查：

- 小 LOOP 类型是否按用户语义而非标题自动推断。
- 供暖节点拆分是否有直接证据和完整四段。
- 统计是否完全派生、未手填。
- 详情跳转是否处理多节点、无节点、筛选禁用和目标缺失。
- Tooltip 是否从 DOM、JS、CSS 和键盘路径完整删除。
- XSS、移动端溢出、关系线和飞书边界是否回归。

修复 Critical/Important 后重新执行 Steps 1–4。
