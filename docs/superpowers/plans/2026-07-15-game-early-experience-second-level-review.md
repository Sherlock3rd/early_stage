# 游戏前期体验秒级审阅实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复三冰 07:54 母亲死亡漏判，并将剧情发现从分钟中点抽样升级为分阶段秒级审阅。

**Architecture:** 保留既有展示时间片和曲线点，在抽帧阶段新增独立审阅时间轴；分析者依据密集审阅帧发现候选事件，再回看连续原视频并将精确秒级证据聚合进展示时间片。三冰事实源重建后同步本地包与 Pages 数据集。

**Tech Stack:** Python 3、OpenCV、JSON、现有 unittest 测试套件、静态 HTML 查看器。

## Global Constraints

- `00:00–10:00` 每 1 秒审阅，`10:00–20:00` 每 5 秒审阅，`20:00+` 每 10 秒审阅。
- 展示层继续使用 `0–30m` 每分钟、`30–60m` 每 5 分钟、`1h+` 每 10 分钟。
- 死亡等关键剧情必须连续查看原视频并精确到秒，不能仅凭中点图判断。
- 先写失败测试并确认 RED，再写最小实现。

---

### Task 1: 秒级审阅时间轴

**Files:**
- Modify: `.cursor/skills/game-early-experience-breakdown/scripts/video_timeline.py`
- Modify: `.cursor/skills/game-early-experience-breakdown/scripts/extract_frames.py`
- Test: `.cursor/skills/game-early-experience-breakdown/tests/test_video_analysis_pipeline.py`

**Interfaces:**
- Produces: `review_step_seconds(timestamp: float) -> float`
- Produces: `generate_review_points(duration: float) -> list[float]`

- [ ] **Step 1: Write the failing boundary and coverage tests**
- [ ] **Step 2: Run the focused test and confirm it fails because the review API is absent**
- [ ] **Step 3: Implement 1/5/10-second review point generation without changing display slices**
- [ ] **Step 4: Run focused and full pipeline tests**

### Task 2: 关键剧情证据契约

**Files:**
- Modify: `.cursor/skills/game-early-experience-breakdown/scripts/analysis_model.py`
- Modify: `.cursor/skills/game-early-experience-breakdown/reference.md`
- Test: `.cursor/skills/game-early-experience-breakdown/tests/test_video_analysis_pipeline.py`

**Interfaces:**
- Consumes: display slice boundaries and existing evidence frames.
- Produces: validated exact-second critical-event records associated with one display slice.

- [ ] **Step 1: Write failing tests for exact timestamp, slice ownership and evidence references**
- [ ] **Step 2: Confirm malformed or midpoint-only critical events fail validation**
- [ ] **Step 3: Implement the minimal optional critical-event contract**
- [ ] **Step 4: Run contract regression tests**

### Task 3: 修复三冰 07:54 数据

**Files:**
- Modify: `.cursor/tmp/extract_sanbing_evidence.py`
- Modify: `.cursor/tmp/generate_sanbing_analysis.py`
- Regenerate: `.cursor/tmp/sanbing-breakdown/analysis.validated.json`
- Regenerate: `artifacts/sanbing-early-experience/viewer/`

**Interfaces:**
- Consumes: 07:45–08:00 continuous-video evidence.
- Produces: mother-death narrative, climax judgement, narrative score 5, negative valence and exact-second event.

- [ ] **Step 1: Add a failing dataset regression asserting the 07:54 death climax**
- [ ] **Step 2: Confirm current Sanbing analysis fails the regression**
- [ ] **Step 3: Add 07:53/07:54/07:57 evidence and update the unified analysis source**
- [ ] **Step 4: Regenerate, validate and rebuild the named Sanbing dataset**

### Task 4: 防漏文档与最终验证

**Files:**
- Modify: `.cursor/skills/game-early-experience-breakdown/SKILL.md`
- Modify: `mistakes/game-early-experience-map-story-evidence.md`
- Modify: `session/requirements/game-early-experience-breakdown.md`
- Modify: `session/session.md`

**Interfaces:**
- Consumes: tested review cadence and corrected dataset.
- Produces: reusable process rule and published corrected viewer.

- [ ] **Step 1: Record the sampling-gap root cause and mandatory dense review cadence**
- [ ] **Step 2: Run all skill tests and lint checks**
- [ ] **Step 3: Verify local browser rendering at 07:00–08:00**
- [ ] **Step 4: Refresh the standalone repository, push only when authorized, and verify Pages**
