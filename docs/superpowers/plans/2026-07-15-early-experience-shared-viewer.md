# 前期体验共享查看器实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用一个本地 `index.html` 切换寒霜、三冰及后续拆解，并删除关键词筛选功能。

**Architecture:** 构建器在共享输出目录维护数据集 JSON、截图目录和 `datasets.json` 清单；查看器从清单生成标题区切换器，通过安全的 `dataset` URL 参数重载目标数据。筛选逻辑只保留阶段和关键节点。

**Tech Stack:** Python 3、原生 JavaScript、HTML/CSS、unittest、静态 GitHub Pages。

## Global Constraints

- 数据集 ID 只允许小写字母、数字和连字符。
- 一个共享输出目录保留所有已构建数据集。
- 标题区使用“拆解项目”下拉切换器。
- 完全删除关键词输入框及关键词匹配逻辑。
- 旧独立查看器保留兼容，共享查看器成为默认入口。

---

### Task 1: 构建数据集清单

**Files:**
- Modify: `.cursor/skills/game-early-experience-breakdown/scripts/build_viewer.py`
- Modify: `.cursor/skills/game-early-experience-breakdown/tests/test_viewer_builder.py`

**Interfaces:**
- Consumes: `dataset_id: str`、`dataset_name: str | None`
- Produces: `data/datasets.json`

- [ ] **Step 1: 写入清单创建、同名更新、旧数据保留的失败测试**
- [ ] **Step 2: 运行测试并确认因清单缺失而失败**
- [ ] **Step 3: 实现 `--dataset-name` 与原子清单维护**
- [ ] **Step 4: 运行构建器测试**

### Task 2: 标题区数据集切换

**Files:**
- Modify: `.cursor/skills/game-early-experience-breakdown/assets/viewer.html`
- Modify: `.cursor/skills/game-early-experience-breakdown/assets/viewer.css`
- Modify: `.cursor/skills/game-early-experience-breakdown/assets/viewer.js`
- Modify: `.cursor/skills/game-early-experience-breakdown/tests/test_viewer_builder.py`

**Interfaces:**
- Consumes: `data/datasets.json` 与当前安全 dataset ID。
- Produces: 标题区下拉选项和安全切换 URL。

- [ ] **Step 1: 写入清单解析、当前项选择、URL 切换与失败回退测试**
- [ ] **Step 2: 确认当前查看器没有切换器并且测试失败**
- [ ] **Step 3: 实现标题区控件、清单加载和切换重载**
- [ ] **Step 4: 运行 JavaScript 行为测试**

### Task 3: 删除关键词筛选

**Files:**
- Modify: `.cursor/skills/game-early-experience-breakdown/assets/viewer.html`
- Modify: `.cursor/skills/game-early-experience-breakdown/assets/viewer.css`
- Modify: `.cursor/skills/game-early-experience-breakdown/assets/viewer.js`
- Modify: `.cursor/skills/game-early-experience-breakdown/tests/test_viewer_builder.py`

**Interfaces:**
- Consumes: 阶段和关键节点筛选值。
- Produces: 不含关键词输入框的筛选状态。

- [ ] **Step 1: 写入关键词控件和匹配逻辑必须不存在的失败测试**
- [ ] **Step 2: 运行测试并确认旧关键词功能触发失败**
- [ ] **Step 3: 删除关键词 UI、搜索文本函数、状态和监听**
- [ ] **Step 4: 验证阶段、关键节点和重置筛选仍可用**

### Task 4: 构建共享本地包并发布

**Files:**
- Create/Regenerate: `artifacts/early-experience/viewer/`
- Modify: `.cursor/skills/game-early-experience-breakdown/SKILL.md`
- Modify: `.cursor/skills/game-early-experience-breakdown/reference.md`
- Modify: `session/requirements/game-early-experience-breakdown.md`
- Modify: `session/session.md`

**Interfaces:**
- Consumes: 寒霜与三冰已校验分析文件。
- Produces: 同一入口下的两个可切换数据集。

- [ ] **Step 1: 依次构建 frost 与 sanbing 到共享输出目录**
- [ ] **Step 2: 运行全部 172+ 项测试和 lint**
- [ ] **Step 3: 浏览器验证双向切换、筛选和图片隔离**
- [ ] **Step 4: 同步 standalone 仓库并验证 Pages**
