# 游戏前期体验情绪压力与整切线交互实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将情绪曲线升级为剧情主导、环境压力可见的结构化评分，并扩大图框、支持整条时间切线预览与点击。

**Architecture:** `analysis_model.py` 负责复算 70/30 剧情主体公式并校验刺激来源；`viewer.js` 继续消费统一 `analysis.json`，新增全高时间片命中带和子分 Tooltip；CSS 分别控制桌面与移动端高度。寒霜 28 片从主图和必要原视频重新取证后更新同一事实源，再重建本地 Viewer。

**Tech Stack:** Python 3 `unittest`、JavaScript/CommonJS、原生 SVG、CSS、OpenCV/ffmpeg、Chrome DevTools Protocol

---

### Task 1: 建立剧情主体情绪评分契约

**Files:**
- Modify: `.cursor/skills/game-early-experience-breakdown/tests/test_video_analysis_pipeline.py`
- Modify: `.cursor/skills/game-early-experience-breakdown/scripts/analysis_model.py`

- [ ] **Step 1: 写公式与字段失败测试**

新增测试数据：

```python
"emotion": {
    "narrative_score": 1,
    "supporting_score": 3,
    "intensity": 1.6,
    "valence": "negative",
    "drivers": ["narrative", "environment_pressure", "urgency"],
    "event": "暴风雪倒计时逼近",
    "reason": "剧情铺垫叠加持续环境压力",
}
```

覆盖剧情 5/其他 0 得 5、剧情 0/其他 5 得 1.5、剧情 1/其他 3 得 1.6，以及公式不一致、越界、
drivers 非法/重复、剧情来源缺失、其他来源缺失、零分却含来源等失败条件。

- [ ] **Step 2: 运行测试并确认旧契约失败**

Run:
```powershell
py -3 -m unittest discover -s ".cursor/skills/game-early-experience-breakdown/tests" -p "test_video_analysis_pipeline.py" -k "emotion" -v
```

Expected: FAIL，旧校验器未要求子分与 drivers，也不验证新公式。

- [ ] **Step 3: 实现公式和严格校验**

在 `analysis_model.py` 增加：

```python
EMOTION_DRIVERS = (
    "narrative",
    "environment_pressure",
    "urgency",
    "combat",
    "progression_reward",
    "relief",
)

def expected_emotion_intensity(narrative_score: float, supporting_score: float) -> float:
    raw = 0.7 * narrative_score + 0.3 * max(narrative_score, supporting_score)
    return math.floor(raw * 10 + 0.5) / 10
```

`_validate_global_curves()` 要求两个子分、最终分、方向、drivers、事件和原因，并校验公式、枚举、
去重及子分与来源一致性。

- [ ] **Step 4: 运行管线测试**

Run:
```powershell
py -3 -m unittest discover -s ".cursor/skills/game-early-experience-breakdown/tests" -p "test_video_analysis_pipeline.py" -v
```

Expected: PASS。

### Task 2: 实现全高时间片命中带

**Files:**
- Modify: `.cursor/skills/game-early-experience-breakdown/tests/test_viewer_builder.py`
- Modify: `.cursor/skills/game-early-experience-breakdown/assets/viewer.js`
- Modify: `.cursor/skills/game-early-experience-breakdown/assets/viewer.css`

- [ ] **Step 1: 写命中带几何失败测试**

新增 `curveSliceBands(model)` 的期望：

```javascript
[
  {index: 0, left: plotLeft, right: midpoint(x0, x1)},
  {index: 1, left: midpoint(x0, x1), right: midpoint(x1, x2)},
  {index: 2, left: midpoint(x1, x2), right: plotRight}
]
```

断言所有带宽大于 0、相邻边界相等、首尾覆盖完整绘图区，并生成与时间片同数的
`.curve-slice-hit-zone`。

- [ ] **Step 2: 运行并确认函数不存在**

Run:
```powershell
py -3 -m unittest discover -s ".cursor/skills/game-early-experience-breakdown/tests" -p "test_viewer_builder.py" -k "slice_hit" -v
```

Expected: FAIL，`curveSliceBands` 尚不存在。

- [ ] **Step 3: 实现纯几何函数**

在 `viewer.js` 新增 `curveSliceBands(model)`，使用相邻时间点横坐标中线计算左右边界；单点时覆盖
完整绘图区。导出该函数供 Node 测试。

- [ ] **Step 4: 替换狭小交互圆点**

SVG 为每片生成全高透明 `<rect>`：

```html
<rect class="curve-slice-hit-zone"
      data-curve-slice="0"
      x="..."
      y="..."
      width="..."
      height="..."
      tabindex="0"
      role="button"></rect>
```

每条命中带配套中心引导线。既有点击、pointerover、focusin、Enter/Space 委托继续使用
`[data-curve-slice]`。`renderSelected()` 改为恢复命中带的 selected、filtered-out 和 ARIA 状态。

- [ ] **Step 5: 增加交互样式**

命中带默认透明；hover/focus/selected 时显示低透明背景和中心引导线。filtered-out 降低透明度并禁用
指针跳转，视觉曲线圆点设为 `pointer-events:none`。

- [ ] **Step 6: 运行 Viewer 测试**

Run:
```powershell
py -3 -m unittest discover -s ".cursor/skills/game-early-experience-breakdown/tests" -p "test_viewer_builder.py" -v
```

Expected: PASS。

### Task 3: 展示子分、来源并扩大图框

**Files:**
- Modify: `.cursor/skills/game-early-experience-breakdown/tests/test_viewer_builder.py`
- Modify: `.cursor/skills/game-early-experience-breakdown/assets/viewer.js`
- Modify: `.cursor/skills/game-early-experience-breakdown/assets/viewer.css`

- [ ] **Step 1: 写 Tooltip 与高度失败测试**

断言 Tooltip 包含“剧情刺激”“其他刺激”“环境压力”等转义后的来源标签；CSS 桌面端包含：

```css
#emotion-curve-svg { height: clamp(480px, 42vw, 600px); }
```

移动端覆盖为 `clamp(320px, 82vw, 420px)`。

- [ ] **Step 2: 运行并确认旧展示失败**

Run:
```powershell
py -3 -m unittest discover -s ".cursor/skills/game-early-experience-breakdown/tests" -p "test_viewer_builder.py" -k "tooltip" -v
```

Expected: FAIL，旧 Tooltip 无子分和来源，桌面最大高度仍为 420px。

- [ ] **Step 3: 接入 ViewModel 与 Tooltip**

每个曲线点增加 `narrativeScore`、`supportingScore`、`emotionDrivers`。Tooltip 使用固定中文映射展示来源，
不得直接拼接未转义输入。

- [ ] **Step 4: 调整响应式高度和安全边界**

桌面绘图区使用 `clamp(480px, 42vw, 600px)`；≤540px 使用
`clamp(320px, 82vw, 420px)`。将 ViewModel 顶部 padding 提升到 36px，并让剧情菱形、心流星标、
圆点均限制在安全边界内。

- [ ] **Step 5: 运行 Viewer 测试**

Run:
```powershell
py -3 -m unittest discover -s ".cursor/skills/game-early-experience-breakdown/tests" -p "test_viewer_builder.py" -v
```

Expected: PASS。

### Task 4: 重新取证并重评寒霜 28 片

**Files:**
- Modify: `.cursor/tmp/frost-breakdown/analysis.final.validated.json`
- Read: `asset/recordings/寒霜前30分钟.mp4`
- Read: `.cursor/tmp/frost-breakdown/frames/**`

- [ ] **Step 1: 建立逐片复核表**

从现有 JSON 输出 28 片的时间、主图、证据图、剧情轴、任务链、当前情绪分，并逐片检查主图。

- [ ] **Step 2: 回看片段补足压力证据**

对出现暴风雪倒计时、严寒提示、资源告急、战斗、成长奖励或危机缓解的时间片，用 ffmpeg/OpenCV
查看片内必要画面和连续上下文。只记录可观察事实，不用模板补分。

- [ ] **Step 3: 为 28 片填写新情绪字段**

每片填写 `narrative_score`、`supporting_score`、公式计算后的 `intensity`、`drivers`、`valence`、
`event`、`reason`。比尔去世保持主要剧情峰值；纯环境压力不得超过最终 1.5。

- [ ] **Step 4: 校验寒霜数据**

Run:
```powershell
py -3 ".cursor/skills/game-early-experience-breakdown/scripts/analysis_model.py" ".cursor/tmp/frost-breakdown/analysis.final.validated.json"
```

Expected: exit 0。

### Task 5: 同步 Skill、参考和经验记录

**Files:**
- Modify: `.cursor/skills/game-early-experience-breakdown/SKILL.md`
- Modify: `.cursor/skills/game-early-experience-breakdown/reference.md`
- Modify: `.cursor/skills/game-early-experience-breakdown/tests/test_skill_docs.py`
- Add: `mistakes/game-early-experience-emotion-pressure-omission.md`
- Modify: `session/requirements/game-early-experience-breakdown.md`
- Modify: `session/session.md`

- [ ] **Step 1: 写文档失败测试**

断言 Skill/reference 包含剧情主体公式、两个子分、drivers、环境压力、全高命中带和桌面
480～600px；不得继续把情绪强度定义为纯剧情强度。

- [ ] **Step 2: 运行并确认失败**

Run:
```powershell
py -3 -m unittest discover -s ".cursor/skills/game-early-experience-breakdown/tests" -p "test_skill_docs.py" -v
```

Expected: FAIL。

- [ ] **Step 3: 更新 Skill 与 reference**

同步已确认规格中的评分、取证、布局、交互和验收规则。

- [ ] **Step 4: 记录错误与会话**

错误记录写明：旧规则把情绪限定为剧情刺激，导致环境压力被误记为 0；预防项要求逐片检查剧情与
非剧情刺激来源。会话文件记录本轮生效范围且注明飞书未修改。

- [ ] **Step 5: 运行文档测试**

Run:
```powershell
py -3 -m unittest discover -s ".cursor/skills/game-early-experience-breakdown/tests" -p "test_skill_docs.py" -v
```

Expected: PASS。

### Task 6: 重建并完整验收

**Files:**
- Regenerate: `artifacts/frost-early-experience/viewer/index.html`
- Regenerate: `artifacts/frost-early-experience/viewer/data.json`
- Verify: `artifacts/frost-early-experience/viewer/screenshots/**`

- [ ] **Step 1: 重建 Viewer**

Run:
```powershell
py -3 ".cursor/skills/game-early-experience-breakdown/scripts/build_viewer.py" ".cursor/tmp/frost-breakdown/analysis.final.validated.json" --output-dir "artifacts/frost-early-experience/viewer"
```

Expected: exit 0。

- [ ] **Step 2: 运行完整自动化测试**

Run:
```powershell
py -3 -m unittest discover -s ".cursor/skills/game-early-experience-breakdown/tests" -v
```

Expected: 全部 PASS；既有 Windows 符号链接权限跳过允许保留。

- [ ] **Step 3: Chrome 桌面与移动端验收**

1440px 桌面端验证绘图区高度为 600px、标记不裁切、命中带数量为 28；在同一命中带顶部、中部和
底部触发 pointerover/click 均显示并跳转同一时间片。390px 移动端验证高度 320～420px、
无横向溢出。两端 Tooltip 均展示最终分、剧情分、其他刺激分和来源。

- [ ] **Step 4: 最终审查**

审查重点：公式与舍入、来源一致性、28 片证据、命中带无缝几何、筛选/选中/ARIA 状态、图框边界、
构建产物同步。修复所有 Critical/Important 后重新运行完整测试和浏览器验收。

- [ ] **Step 5: 检查边界**

确认未修改飞书页签、未覆盖无关文件、未创建 Git commit。
