# Game Early Experience Dual Curves Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the seven-dimension weighted emotion chart with explainable manual emotion-intensity and gameplay-experience curves plus a real three-point experience trend.

**Architecture:** `analysis.json` replaces `emotion_curve` with required `global_curves` points aligned to slices. Python validates manual scores and evidence, while dependency-free JavaScript derives the moving average/trend summary and renders all three lines in one SVG.

**Tech Stack:** Python 3 validation and unittest, vanilla JavaScript, inline SVG, HTML/CSS, existing atomic viewer builder.

**Commit policy:** Do not create commits unless the user explicitly requests one.

---

### Task 1: Replace the Curve Data Contract

**Files:**
- Modify: `.cursor/skills/game-early-experience-breakdown/tests/test_video_analysis_pipeline.py`
- Modify: `.cursor/skills/game-early-experience-breakdown/scripts/analysis_model.py`

- [ ] **Step 1: Replace the shared fixture**

Change `valid_emotion_curve()` to `valid_global_curves()`:

```python
{
    "scale": {"min": 0, "max": 5},
    "trend_window": 3,
    "points": [{
        "start": item["start"],
        "end": item["end"],
        "emotion": {
            "intensity": 0,
            "valence": "neutral",
            "event": "",
            "reason": "",
        },
        "experience": {
            "score": 3,
            "basis": {
                "gameplay_concentration": "存在连续有效操作",
                "feedback_density": "操作后有明确反馈",
                "goal_challenge": "目标清晰且挑战适中",
                "interruption": "未观察到明显打断",
            },
            "summary": "体验投入程度稳定",
        },
    } for item in slices],
}
```

- [ ] **Step 2: Add failing validation tests**

Cover missing `global_curves`, retained legacy `emotion_curve`, invalid scale/window, score ranges, valence enum, conditional emotion text, four required basis fields, and exact slice alignment.

- [ ] **Step 3: Run the contract test and confirm RED**

```powershell
py -3 ".cursor\skills\game-early-experience-breakdown\tests\test_video_analysis_pipeline.py"
```

- [ ] **Step 4: Implement strict `global_curves` validation**

Require root keys `video`, `slices`, and `global_curves`; reject the legacy root key. Validate:

```python
scale == {"min": 0, "max": 5}
trend_window == 3
0 <= emotion.intensity <= 5
emotion.valence in ("positive", "negative", "mixed", "neutral")
0 <= experience.score <= 5
```

Require emotion event/reason only when intensity is above zero. Require non-empty gameplay concentration, feedback density, goal/challenge, interruption, and experience summary for every point.

- [ ] **Step 5: Run contract tests and confirm GREEN**

---

### Task 2: Implement Trend and Chart Pure Functions

**Files:**
- Modify: `.cursor/skills/game-early-experience-breakdown/tests/test_viewer_builder.py`
- Modify: `.cursor/skills/game-early-experience-breakdown/assets/viewer.js`

- [ ] **Step 1: Add failing JavaScript behavior tests**

Test:

```javascript
movingAverage3([1, 3, 5, 3]) // [2, 3, 11/3, 4]
experienceTrendSummary([1, 2, 2, 4, 4, 5])
globalCurvesViewModel(data)
globalCurvesSvgMarkup(model, visibility)
globalCurvesTooltipMarkup(point)
```

Cover one/two/many points, rise/flat/fall thresholds, shared `0～5` geometry, valence colors, climax diamonds, flow stars, HTML escaping, and absence of legacy weights/formula.

- [ ] **Step 2: Run viewer tests and confirm RED**

- [ ] **Step 3: Implement derived trend functions**

`movingAverage3()` uses adjacent two-point averages at endpoints and centered three-point averages internally. `experienceTrendSummary()` compares the first and last three raw experience scores and returns opening average, ending average, delta, and `rising/flat/falling`.

- [ ] **Step 4: Replace the old weighted view model**

Build points containing emotion intensity, experience score, experience trend, valence, structured reasons, climax/flow flags from the corresponding slice, and true-time x positions.

- [ ] **Step 5: Render three SVG lines and semantic markers**

Render emotion intensity, raw experience, and experience trend. Use valence-colored emotion nodes, diamond climax markers, and star flow markers. Keep point nodes focusable and slice-linked.

- [ ] **Step 6: Run viewer behavior tests and confirm GREEN**

---

### Task 3: Replace Chart Layout, Legend, and Interaction

**Files:**
- Modify: `.cursor/skills/game-early-experience-breakdown/assets/viewer.html`
- Modify: `.cursor/skills/game-early-experience-breakdown/assets/viewer.css`
- Modify: `.cursor/skills/game-early-experience-breakdown/assets/viewer.js`
- Modify: `.cursor/skills/game-early-experience-breakdown/tests/test_viewer_builder.py`

- [ ] **Step 1: Add failing static and interaction tests**

Require hooks for trend summary and reading guidance. Test independent toggles for emotion, experience actual, and experience trend; show-all behavior; Escape dismissal; filtered nodes; and click linkage.

- [ ] **Step 2: Replace chart copy and controls**

Rename the section to “全局情绪与体验曲线”. Add visible reading guidance:

```text
情绪曲线用于定位剧情情绪高点；体验曲线用于判断玩法沉浸与心流强度；趋势线用于观察前期体验是否整体提升。
```

Add opening, ending, delta, and trend conclusion values above the chart.

- [ ] **Step 3: Replace legend and tooltip behavior**

Legend entries are only “情绪强度”“体验实际值”“体验趋势” plus “显示全部”. Tooltip shows both manual scores, emotion direction/event/reason, four experience basis texts, experience summary, and derived trend value.

- [ ] **Step 4: Update CSS**

Use one shared plot with distinct emotion/experience/trend strokes, semantic valence node colors, clear climax/flow marker shapes, responsive legend/tooltip, and no page-level horizontal overflow.

- [ ] **Step 5: Run viewer tests and confirm GREEN**

---

### Task 4: Update Skill Documentation

**Files:**
- Modify: `.cursor/skills/game-early-experience-breakdown/tests/test_skill_docs.py`
- Modify: `.cursor/skills/game-early-experience-breakdown/SKILL.md`
- Modify: `.cursor/skills/game-early-experience-breakdown/reference.md`
- Modify: `session/requirements/game-early-experience-breakdown.md`
- Modify: `session/session.md`

- [ ] **Step 1: Add failing documentation tests**

Require `global_curves`, both `0～5` scoring rubrics, valence enum, four experience basis fields, three-point trend, trend thresholds, shared chart semantics, and explicit removal of seven-dimension weighting.

- [ ] **Step 2: Run documentation tests and confirm RED**

- [ ] **Step 3: Update Skill and reference**

Replace all operational instructions for `emotion_curve`, seven weights, `-5～+5`, and weighted formulas with the approved manual dual-curve contract.

- [ ] **Step 4: Update session records**

Record why the old chart was misleading and the approved manual dual-curve replacement. Keep Feishu explicitly out of scope.

- [ ] **Step 5: Run documentation tests and confirm GREEN**

---

### Task 5: Rescore Frost and Verify the Deliverable

**Files:**
- Modify: `.cursor/tmp/frost-breakdown/analysis.final.validated.json`
- Rebuild: `.cursor/tmp/frost-breakdown/analysis.dual-curves.validated.json`
- Rebuild: `artifacts/frost-early-experience/viewer/index.html`
- Rebuild: `artifacts/frost-early-experience/viewer/data.json`

- [ ] **Step 1: Replace all 28 legacy points**

For every slice, remove legacy seven scores and add:

```text
emotion intensity + valence + event + reason
experience score + four evidence texts + summary
```

Use existing verified narrative/flow judgements and slice facts. Ensure the grandfather death is a negative emotion peak, first expedition and continuous combat are experience peaks, management menus are experience lows, and city/world-map unlocks produce late recovery.

- [ ] **Step 2: Validate the updated analysis**

```powershell
py -3 ".cursor\skills\game-early-experience-breakdown\scripts\analysis_model.py" `
  ".cursor\tmp\frost-breakdown\analysis.final.validated.json" `
  --output ".cursor\tmp\frost-breakdown\analysis.dual-curves.validated.json"
```

- [ ] **Step 3: Rebuild atomically**

```powershell
py -3 ".cursor\skills\game-early-experience-breakdown\scripts\build_viewer.py" `
  ".cursor\tmp\frost-breakdown\analysis.dual-curves.validated.json" `
  --output-dir "artifacts\frost-early-experience\viewer"
```

- [ ] **Step 4: Verify in Edge**

Check all three lines, valence colors, climax/flow markers, simultaneous tooltip, slice linkage, trend conclusion, no legacy formula, no overflow, and existing carousel navigation/aspect ratio.

- [ ] **Step 5: Run the complete suite**

```powershell
py -3 -m unittest discover `
  -s ".cursor\skills\game-early-experience-breakdown\tests" `
  -p "test_*.py"
```

Expected: all tests pass except the existing documented skip; changed files have no new linter diagnostics.
