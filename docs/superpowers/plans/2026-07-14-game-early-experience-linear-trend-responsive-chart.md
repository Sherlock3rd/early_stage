# 游戏前期体验线性趋势与响应式图框实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将体验趋势从3节点移动平均改为按真实时间拟合的线性回归直线，并让曲线 SVG 在 320～420px 的响应式图框内完整显示。

**Architecture:** `analysis.json` 只保留人工双曲线原始分，不保存可派生的趋势窗口。`viewer.js` 通过独立纯函数计算线性回归、趋势摘要和容器尺寸，再由现有 SVG 渲染层消费；浏览器初始化时监听图框尺寸并重绘。CSS 负责响应式高度上限，构建器继续把同一套资源内联进本地查看器。

**Tech Stack:** Python 3 `unittest`、JavaScript/CommonJS、原生 SVG、CSS、`ResizeObserver`

---

### Task 1: 移除过时的移动平均数据契约

**Files:**
- Modify: `.cursor/skills/game-early-experience-breakdown/tests/test_video_analysis_pipeline.py`
- Modify: `.cursor/skills/game-early-experience-breakdown/scripts/analysis_model.py`
- Modify: `.cursor/tmp/frost-breakdown/analysis.final.validated.json`

- [ ] **Step 1: 写失败测试**

将 `valid_global_curves()` 中的 `trend_window` 删除，并把旧窗口校验测试改为验证仅含 `scale`、`points` 的数据可以通过；额外提供 `trend_window` 时不影响读取旧分析数据，但不再要求或解释该字段。

- [ ] **Step 2: 运行测试并确认因缺少 `trend_window` 失败**

Run:
```powershell
py -3 -m unittest discover -s ".cursor/skills/game-early-experience-breakdown/tests" -p "test_video_analysis_pipeline.py" -k "test_global_curve_scale_window_and_scores_are_strict" -v
```

Expected: FAIL，错误指出 `global_curves.trend_window` 缺失。

- [ ] **Step 3: 写最小实现**

在 `_validate_global_curves()` 中把：
```python
_require_keys(curves, ("scale", "trend_window", "points"), "global_curves")
```
改为：
```python
_require_keys(curves, ("scale", "points"), "global_curves")
```
并删除固定窗口值校验。同步删除寒霜分析 JSON 的 `trend_window`。

- [ ] **Step 4: 运行管线测试**

Run:
```powershell
py -3 -m unittest discover -s ".cursor/skills/game-early-experience-breakdown/tests" -p "test_video_analysis_pipeline.py" -v
```

Expected: PASS。

### Task 2: 用真实时间线性回归替换移动平均

**Files:**
- Modify: `.cursor/skills/game-early-experience-breakdown/tests/test_viewer_builder.py`
- Modify: `.cursor/skills/game-early-experience-breakdown/assets/viewer.js`

- [ ] **Step 1: 写线性回归失败测试**

测试期望的新接口：
```javascript
viewer.linearRegressionTrend(
  [{time: 30, score: 1}, {time: 90, score: 3}, {time: 150, score: 5}],
  0,
  5
)
```
应返回约 `slope=1/30`、`openingPrediction=1`、`endingPrediction=5`、`delta=4`、`direction="rising"`，并覆盖单点水平线、下降、持平和预测值截断。

- [ ] **Step 2: 运行测试并确认函数不存在**

Run:
```powershell
py -3 -m unittest discover -s ".cursor/skills/game-early-experience-breakdown/tests" -p "test_viewer_builder.py" -k "test_dual_curves_use_linear_regression_over_real_time" -v
```

Expected: FAIL，错误指出 `linearRegressionTrend` 不存在。

- [ ] **Step 3: 实现最小二乘纯函数**

新增 `linearRegressionTrend(observations, min, max)`：
```javascript
const meanX = observations.reduce((sum, item) => sum + item.time, 0) / observations.length;
const meanY = observations.reduce((sum, item) => sum + item.score, 0) / observations.length;
const denominator = observations.reduce((sum, item) => sum + (item.time - meanX) ** 2, 0);
const slope = denominator
  ? observations.reduce(
      (sum, item) => sum + (item.time - meanX) * (item.score - meanY),
      0
    ) / denominator
  : 0;
const intercept = meanY - slope * meanX;
```
预测值使用 `Math.min(max, Math.max(min, value))` 截断；首尾预测差沿用 `±0.5` 方向阈值。

- [ ] **Step 4: 接入 ViewModel 和 SVG**

`globalCurvesViewModel(data, width=1000, height=360)` 使用每片真实时间中点拟合回归；每个点的 `experienceTrend` 改为回归预测值。趋势 SVG 只用首尾两个趋势点生成直线路径，提示文本和阅读说明改称“线性回归预测值/整体趋势”。

- [ ] **Step 5: 运行查看器测试**

Run:
```powershell
py -3 -m unittest discover -s ".cursor/skills/game-early-experience-breakdown/tests" -p "test_viewer_builder.py" -v
```

Expected: PASS，且趋势路径只有一个 `M` 和一个 `L`。

### Task 3: 将 SVG 锁定在响应式图框中

**Files:**
- Modify: `.cursor/skills/game-early-experience-breakdown/tests/test_viewer_builder.py`
- Modify: `.cursor/skills/game-early-experience-breakdown/assets/viewer.css`
- Modify: `.cursor/skills/game-early-experience-breakdown/assets/viewer.js`

- [ ] **Step 1: 写响应式尺寸失败测试**

断言 CSS 包含：
```css
#emotion-curve-svg { height: clamp(320px, 30vw, 420px); }
.emotion-curve-chart { width: 100%; height: 100%; }
```
并断言 `globalCurvesViewModel(data, 1376, 420)` 返回同样的 `width/height`，所有点坐标均落在绘图区边界内。

- [ ] **Step 2: 运行测试并确认旧 `height:auto` 导致失败**

Run:
```powershell
py -3 -m unittest discover -s ".cursor/skills/game-early-experience-breakdown/tests" -p "test_viewer_builder.py" -k "test_curve_chart_uses_responsive_container_dimensions" -v
```

Expected: FAIL，CSS 仍为 `height:auto` 且 ViewModel 不接受尺寸。

- [ ] **Step 3: 实现响应式 CSS 和动态尺寸**

移除图表 `min-height`/`height:auto`，改为：
```css
#emotion-curve-svg { width: 100%; height: clamp(320px, 30vw, 420px); }
.emotion-curve-chart { display: block; width: 100%; height: 100%; }
```
`renderEmotionCurve()` 从 `#emotion-curve-svg.clientWidth/clientHeight` 读取实际尺寸并传给 ViewModel。

- [ ] **Step 4: 添加尺寸变化重绘**

初始化时用 `ResizeObserver` 监听 `#emotion-curve-svg`；仅在整数宽高发生变化时重新渲染，避免循环。环境没有 `ResizeObserver` 时保留首次渲染，不影响本地文件查看。

- [ ] **Step 5: 运行查看器测试**

Run:
```powershell
py -3 -m unittest discover -s ".cursor/skills/game-early-experience-breakdown/tests" -p "test_viewer_builder.py" -v
```

Expected: PASS。

### Task 4: 同步 Skill 文档并重建寒霜查看器

**Files:**
- Modify: `.cursor/skills/game-early-experience-breakdown/SKILL.md`
- Modify: `.cursor/skills/game-early-experience-breakdown/reference.md`
- Modify: `.cursor/skills/game-early-experience-breakdown/tests/test_skill_docs.py`
- Regenerate: `artifacts/frost-early-experience/viewer/index.html`
- Regenerate: `artifacts/frost-early-experience/viewer/data.json`

- [ ] **Step 1: 写文档失败测试**

将文档断言从“3节点移动平均”改为“线性回归”“真实时间中点”“响应式图框”，并断言 Skill/reference 不再出现 `trend_window` 或“移动平均”。

- [ ] **Step 2: 运行并确认失败**

Run:
```powershell
py -3 -m unittest discover -s ".cursor/skills/game-early-experience-breakdown/tests" -p "test_skill_docs.py" -v
```

Expected: FAIL，旧文档仍描述移动平均。

- [ ] **Step 3: 更新 Skill 与 reference**

同步已批准规格中的回归公式、`±0.5` 趋势阈值、预测值截断、320～420px 图框和尺寸变化重绘要求。

- [ ] **Step 4: 重建寒霜本地查看器**

Run:
```powershell
py -3 ".cursor/skills/game-early-experience-breakdown/scripts/build_viewer.py" ".cursor/tmp/frost-breakdown/analysis.final.validated.json" --output-dir "artifacts/frost-early-experience/viewer"
```

Expected: 成功生成 `index.html`、`data.json` 和截图资源。

### Task 5: 完整验证

**Files:**
- Verify: `.cursor/skills/game-early-experience-breakdown/**`
- Verify: `artifacts/frost-early-experience/viewer/**`

- [ ] **Step 1: 运行完整自动化测试**

Run:
```powershell
py -3 -m unittest discover -s ".cursor/skills/game-early-experience-breakdown/tests" -v
```

Expected: 全部 PASS（既有环境性跳过允许保留）。

- [ ] **Step 2: 浏览器验收**

在桌面宽屏和 ≤540px 窄屏检查：
- 图框高度始终位于 320～420px。
- SVG、坐标轴、曲线和标记均在边框内，无横向滚动。
- 青色趋势线为单一直线，开关正常。
- 趋势摘要、提示层均显示回归预测值。
- 时间片联动、Escape、筛选和图片轮播无回归。

- [ ] **Step 3: 检查改动范围**

确认未修改飞书页签，未覆盖用户其他未提交文件，且未创建 Git commit。
