# Game Early Experience Emotion Curve Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a validated seven-dimension global emotion curve to the offline early-experience viewer and rebuild the Frost example.

**Architecture:** Extend the single `analysis.json` contract with required `emotion_curve` weights and points aligned one-to-one with existing slices. Keep the viewer dependency-free: pure JavaScript computes weighted scores and SVG geometry, while DOM rendering adds interactive legend, tooltip, and slice selection.

**Tech Stack:** Python 3 validation and unittest, vanilla JavaScript, inline SVG, HTML/CSS, existing atomic viewer builder.

**Commit policy:** Do not create commits unless the user explicitly requests one.

---

### Task 1: Emotion Curve Data Contract

**Files:**
- Modify: `.cursor/skills/game-early-experience-breakdown/tests/test_video_analysis_pipeline.py`
- Modify: `.cursor/skills/game-early-experience-breakdown/scripts/analysis_model.py`

- [ ] **Step 1: Add valid emotion data to the shared test fixture**

Add `valid_emotion_curve(slices)` with the approved scale, weights, seven zero-valued scores, and non-empty summaries. Make `valid_analysis()` include it so downstream viewer and Feishu tests continue to use a contract-valid fixture.

- [ ] **Step 2: Add failing validation tests**

Cover:

```python
def test_emotion_curve_is_required(): ...
def test_emotion_weights_must_contain_exact_dimensions_and_sum_to_one(): ...
def test_emotion_scores_must_be_finite_and_between_minus_five_and_five(): ...
def test_emotion_points_must_align_with_slices(): ...
def test_emotion_summary_must_not_be_empty(): ...
def test_custom_emotion_weights_are_allowed(): ...
```

- [ ] **Step 3: Run contract tests and confirm RED**

Run:

```powershell
py -3 ".cursor\skills\game-early-experience-breakdown\tests\test_video_analysis_pipeline.py"
```

Expected: new emotion validation tests fail because `analysis_model.py` does not validate `emotion_curve`.

- [ ] **Step 4: Implement strict validation**

Add constants for score bounds and default weights. Add helpers that:

```python
require exact DIMENSION_KEYS
require every weight >= 0
require math.isclose(sum(weights.values()), 1.0, abs_tol=1e-9)
require -5 <= every score <= 5
require len(points) == len(slices)
require point start/end == corresponding slice start/end
require non-empty summary
```

Make root-level `emotion_curve` required and invoke validation after slice validation.

- [ ] **Step 5: Run contract and full existing tests**

Expected: contract tests pass and no existing fixture-based tests regress.

---

### Task 2: Viewer SVG Model and Static Layout

**Files:**
- Modify: `.cursor/skills/game-early-experience-breakdown/tests/test_viewer_builder.py`
- Modify: `.cursor/skills/game-early-experience-breakdown/assets/viewer.html`
- Modify: `.cursor/skills/game-early-experience-breakdown/assets/viewer.js`
- Modify: `.cursor/skills/game-early-experience-breakdown/assets/viewer.css`

- [ ] **Step 1: Add failing pure-function and static-hook tests**

Test:

```javascript
computeCompositeScore(scores, weights)
emotionCurveViewModel(data)
emotionCurveSvgMarkup(model, visibility)
emotionCurveLegendMarkup(weights, visibility)
emotionCurveTooltipMarkup(point)
```

Assertions cover `-5/0/+5` coordinate mapping, true-time horizontal placement, custom weights, escaped summaries, zero axis, positive/negative regions, and a final partial slice.

Require HTML hooks:

```text
emotion-curve-section
emotion-curve-svg
emotion-curve-legend
emotion-curve-tooltip
emotion-algorithm-details
```

- [ ] **Step 2: Run viewer tests and confirm RED**

Run:

```powershell
py -3 ".cursor\skills\game-early-experience-breakdown\tests\test_viewer_builder.py"
```

Expected: new hooks and functions are absent.

- [ ] **Step 3: Add the static section**

Insert the section after filters and before the overview timeline. Include:

```html
<section id="emotion-curve-section">
  <div id="emotion-curve-legend"></div>
  <div id="emotion-curve-svg"></div>
  <div id="emotion-curve-tooltip" hidden></div>
  <details id="emotion-algorithm-details"></details>
</section>
```

- [ ] **Step 4: Implement pure score and SVG functions**

Compute:

```javascript
E(t) = DIMENSIONS.reduce(
  (sum, dimension) => sum + scores[dimension] * weights[dimension],
  0
);
```

Map `start/end` to percentage x positions using video duration and map score `+5` to chart top, `0` to center, `-5` to bottom. Render a bold composite path plus seven stable-color paths and focusable point buttons.

- [ ] **Step 5: Add responsive styles**

Use no external assets. Add positive/negative plot bands, a visible zero axis, stable dimension colors, scrollable legend on narrow screens, and no page-level horizontal overflow.

- [ ] **Step 6: Run viewer tests and confirm GREEN**

---

### Task 3: Viewer Interaction and Slice Linking

**Files:**
- Modify: `.cursor/skills/game-early-experience-breakdown/tests/test_viewer_builder.py`
- Modify: `.cursor/skills/game-early-experience-breakdown/assets/viewer.js`
- Modify: `.cursor/skills/game-early-experience-breakdown/assets/viewer.css`

- [ ] **Step 1: Add failing interaction tests**

Cover:

```text
toggle one dimension
show all dimensions
show composite only
hover/focus tooltip
click curve point -> select matching slice
selected slice -> selected curve point
render failure -> visible curve error while detail remains usable
```

- [ ] **Step 2: Run interaction tests and confirm RED**

- [ ] **Step 3: Extend viewer state and render lifecycle**

Add `curveVisibility` and use `initialize()` to render the chart. Make `renderSelected()` update the selected curve point. Curve click must call the existing `selectSlice(index)` rather than introducing a second selection state.

- [ ] **Step 4: Implement delegated legend, hover, focus, and click events**

Keep keyboard navigation compatible with the existing timeline and gallery. Hide the tooltip on pointer leave and Escape.

- [ ] **Step 5: Add algorithm note rendering**

Render the actual weights from `analysis.json`, the `-5～+5` scale, and:

```text
综合情绪值 = Σ(维度分 × 维度权重)
```

- [ ] **Step 6: Run viewer tests and confirm GREEN**

---

### Task 4: Skill and Contract Documentation

**Files:**
- Modify: `.cursor/skills/game-early-experience-breakdown/tests/test_skill_docs.py`
- Modify: `.cursor/skills/game-early-experience-breakdown/SKILL.md`
- Modify: `.cursor/skills/game-early-experience-breakdown/reference.md`
- Modify: `session/requirements/game-early-experience-breakdown.md`
- Modify: `session/session.md`

- [ ] **Step 1: Add failing documentation tests**

Require documentation for:

```text
emotion_curve
-5～+5 signed emotional contribution
approved seven weights
weighted formula
time-slice alignment
SVG interaction and algorithm note
negative plot emotion is not negative plot quality
```

- [ ] **Step 2: Run documentation tests and confirm RED**

- [ ] **Step 3: Update Skill and reference**

Add emotion scoring to fixed analysis rules, data contract, HTML rules, execution flow, and completion gate. State that Feishu layout is unchanged in this iteration.

- [ ] **Step 4: Update session records**

Record the approved feature scope, weighting algorithm, and affected files without changing unrelated project rules.

- [ ] **Step 5: Run documentation tests and confirm GREEN**

---

### Task 5: Frost Scores and Rebuilt Deliverable

**Files:**
- Modify: `.cursor/tmp/frost-breakdown/analysis.final.validated.json`
- Rebuild: `artifacts/frost-early-experience/viewer/index.html`
- Rebuild: `artifacts/frost-early-experience/viewer/data.json`

- [ ] **Step 1: Score all 28 Frost slices**

For each slice, add seven `-5～+5` scores and one concise summary. Base scores on the existing verified seven-dimensional facts, climax/low/flow markers, screenshots, and previously reviewed video evidence. Use `0` for neutral/no clear contribution; do not infer unsupported events.

- [ ] **Step 2: Validate the updated analysis**

Run:

```powershell
py -3 ".cursor\skills\game-early-experience-breakdown\scripts\analysis_model.py" `
  ".cursor\tmp\frost-breakdown\analysis.final.validated.json" `
  --output ".cursor\tmp\frost-breakdown\analysis.emotion.validated.json"
```

Expected: exit 0 and 28 aligned emotion points.

- [ ] **Step 3: Rebuild the viewer atomically**

Run:

```powershell
py -3 ".cursor\skills\game-early-experience-breakdown\scripts\build_viewer.py" `
  ".cursor\tmp\frost-breakdown\analysis.emotion.validated.json" `
  --output-dir "artifacts\frost-early-experience\viewer"
```

- [ ] **Step 4: Verify in a real browser**

Check:

```text
chart renders
composite and seven lines are visible/toggleable
tooltip values and formula are correct
positive/negative direction is sensible
point click selects the same timeline slice
existing carousel still switches and contains images
no horizontal page overflow
```

- [ ] **Step 5: Run the full suite and lints**

Run:

```powershell
py -3 -m unittest discover `
  -s ".cursor\skills\game-early-experience-breakdown\tests" `
  -p "test_*.py"
```

Expected: all tests pass except any pre-existing documented skip; changed files have no new linter diagnostics.
