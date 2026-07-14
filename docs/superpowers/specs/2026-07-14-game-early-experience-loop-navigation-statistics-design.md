# 游戏前期体验 LOOP 跳转与去重统计设计

## 1. 背景与目标

当前寒霜 Viewer 已按时间展示 16 个事件级小 LOOP，但仍有三个可用性问题：

1. 时间片详情与下方 LOOP 主链之间缺少正向跳转。
2. LOOP 悬浮窗遮挡内容，且四段信息已直接显示在卡片中。
3. 页面只能看到事件级小 LOOP，无法判断去重后有多少种玩法闭环，以及同类闭环被强化了多少次。

本轮目标：

- 在详情中展示全部关联小 LOOP，并直接定位到对应卡片。
- 完全移除 LOOP 悬浮窗。
- 使用人工维护的玩法闭环类型去重，并展示出现次数与强化次数。
- 将“供暖生产”拆成“建筑生产”和“临时供暖强化”，使统计口径与实际行为一致。

本轮只修改本地 HTML、统一分析数据和 Skill 文档，不修改飞书页签。

## 2. 术语与统计规则

### 2.1 事件级小 LOOP

`micro_loop` 仍表示时间主链中的一次具体闭环：

`明确动机 → 连续行为 → 即时奖励 → 下一动机`

同一玩法闭环可以在不同时间再次出现，每次出现仍保留独立节点和证据。

### 2.2 去重小 LOOP 类型

新增 `loop_family`，用于表达多个事件级小 LOOP 共享的玩法闭环语义。归类依据是该轮闭环的主要行为和奖励，不按标题、文本相似度或所属大 LOOP 自动推断。

每个 `micro_loop` 必须且只能引用一个 `loop_family_id`。

### 2.3 统计

- 事件级小 LOOP 数：`micro_loop` 节点总数。
- 去重小 LOOP 数：至少被一个 `micro_loop` 引用的 `loop_family_id` 数。
- 某类型出现次数：引用该 `loop_family_id` 的节点数。
- 某类型强化次数：`max(出现次数 - 1, 0)`。
- 首次出现表示闭环建立，不计为强化。
- 统计始终基于完整分析数据，不随大 LOOP 淡化或时间片筛选变化。

## 3. 数据契约

`global_loops` 增加：

```json
{
  "loop_families": [
    {
      "id": "building_growth",
      "title": "建筑升级养成",
      "summary": "通过建设和升级提高聚落能力",
      "accent": "building_growth"
    }
  ]
}
```

每个 `micro_loop` 增加：

```json
{
  "loop_family_id": "building_growth"
}
```

固定要求：

- `loop_families` 必须为非空数组。
- 每项必须包含唯一非空 `id`、`title`、`summary` 和合法 `accent`。
- 类型配色只允许：
  - `building_growth`
  - `building_production`
  - `expedition_progression`
  - `hero_growth`
  - `law_system`
  - `heating_boost`
- `micro_loop.loop_family_id` 必须引用现有类型。
- 非 `micro_loop` 节点不得携带 `loop_family_id`。
- 不允许定义从未被任何小 LOOP 使用的类型。
- 旧分析缺少 `loop_families` 或 `loop_family_id` 时拒绝构建。

## 4. 寒霜归类与节点拆分

寒霜调整为 17 个事件级小 LOOP、6 个去重类型。

### 4.1 建筑升级养成

出现 8 次，强化 7 次：

- `settlement-survival-landing`
- `settlement-legacy-start`
- `settlement-build-queue`
- `settlement-infrastructure`
- `settlement-expedition-ready`
- `settlement-expedition-reinvest`
- `settlement-return-cleanup`
- `settlement-resource-sprint`

### 4.2 建筑生产

出现 2 次，强化 1 次：

- `settlement-production-unlock`
- `settlement-building-production`

### 4.3 推关玩法

出现 3 次，强化 2 次：

- `expedition-first-sortie`
- `expedition-second-launch`
- `expedition-ice-river-push`

### 4.4 英雄养成

出现 2 次，强化 1 次：

- `hero-recruit-and-deploy`
- `hero-post-battle-growth`

### 4.5 法令系统

出现 1 次，强化 0 次：

- `settlement-cold-policy`

### 4.6 临时供暖强化

出现 1 次，强化 0 次：

- `settlement-temporary-heating-boost`

### 4.7 拆分规则

删除原 `settlement-heating-production`，在同一关联时间片内按实际操作顺序替换为：

1. `settlement-building-production`
   - 主要行为：确认生产缺口、安排生产、领取或形成资源产出。
   - 类型：`building_production`。
2. `settlement-temporary-heating-boost`
   - 主要行为：面对极寒压力，开启临时供暖强化。
   - 类型：`heating_boost`。

两者的 `macro_loop_id` 均为 `settlement`，并按以下主链连接：

```text
settlement-return-cleanup
→ settlement-building-production
→ settlement-temporary-heating-boost
→ settlement-cold-policy
```

两节点可以引用同一时间片，但必须各自填写能证明主要闭环的直接证据。节点顺序用于解决同时间片内的阅读顺序。

## 5. 详情窗口的 LOOP 跳转

### 5.1 展示

在详情标题和上一片/下一片导航下增加“关联 LOOP”区域：

- 查找 `slice_indices` 包含当前时间片索引的全部 `micro_loop`。
- 每个关联小 LOOP 显示一个跳转标签，文案使用小 LOOP 标题。
- 同一时间片关联多个小 LOOP 时全部展示，不折叠为一个主项。
- 没有关联小 LOOP 时显示“当前时间片无关联 LOOP”。
- 线性节点、主体终点和图外出口不进入该区域。

### 5.2 交互

- 点击标签后调用对应小 LOOP 卡片的 `scrollIntoView`。
- 定位后给目标卡片增加短暂脉冲高亮；高亮自动消失，不形成常驻选中框。
- 若时间筛选导致该小 LOOP 所有关联片都不可见，标签置灰且不可激活。
- 键盘可聚焦跳转标签，Enter/Space 与点击行为一致。
- LOOP 卡片点击返回详情的现有行为保留。

## 6. 移除 LOOP 悬浮窗

完全删除：

- `#global-loop-tooltip` DOM。
- Tooltip 生成与定位函数。
- LOOP 的 `pointerover`、`pointerleave`、`focusin`、`focusout` 悬浮监听。
- Escape 关闭 LOOP Tooltip 的分支。
- `.global-loop-tooltip*` CSS。

四段内容继续直接显示在小 LOOP 卡片中。`evidence_frames` 继续保留在分析数据中，用于校验、审查和后续追溯，但本轮 Viewer 不展示 LOOP 证据悬浮图。

四段节点不再单独进入键盘 Tab 顺序；小 LOOP 卡片本身继续支持 Enter/Space。

## 7. 全局统计区

统计区放在全局 LOOP 标题下方、大 LOOP 筛选图例上方。

### 7.1 总览

显示：

```text
事件级小 LOOP 17
去重小 LOOP 6
```

### 7.2 类型统计

六个统计标签使用 `loop_family.accent` 区分，分别展示：

```text
建筑升级养成
出现 8 次 · 强化 7 次
```

排序按 `loop_families` 数据顺序，不按次数重新排序。

桌面统计标签自动换行；移动端统计标签在区块内部横向滚动，页面本身不得出现横向溢出。

## 8. 纯视图模型

新增或调整纯函数：

- `loopFamilyStatistics(graph)`：计算事件总数、去重总数、各类型出现次数和强化次数。
- `loopFamilyStatisticsMarkup(model)`：生成安全转义的统计区。
- `relatedMicroLoops(nodes, sliceIndex, visible)`：返回详情关联跳转项及禁用状态。
- `relatedLoopNavigationMarkup(items)`：生成跳转标签或空状态。

统计和详情导航均从同一 `global_loops.nodes` 派生，不维护第二套手填计数。

## 9. 错误处理

- 类型契约错误由 `analysis_model.py` 在构建前拒绝。
- Viewer 的统计区继续受 `renderGlobalLoops()` 局部错误隔离保护，不影响曲线、时间轴和详情。
- 详情导航在 LOOP 模型不可用时显示空状态，不阻断详情渲染。
- 所有类型名称、摘要和小 LOOP 标题进入 HTML 前必须转义。
- 点击跳转时目标 DOM 不存在则保持原位置，不抛出未捕获异常。

## 10. 测试与验收

### 10.1 数据与校验

- 缺少、重复或未使用的 `loop_family` 被拒绝。
- 非法配色被拒绝。
- 小 LOOP 缺少或引用不存在的 `loop_family_id` 被拒绝。
- 非小 LOOP 携带 `loop_family_id` 被拒绝。
- 寒霜为 17 个事件级小 LOOP、6 个去重类型。
- 六类出现次数严格为 `8/2/3/2/1/1`，强化次数为 `7/1/2/1/0/0`。
- 拆分后的两个供暖相关节点顺序和主链正确。

### 10.2 Viewer

- 统计纯函数不受大 LOOP 淡化状态影响。
- 统计与跳转动态文本全部安全转义。
- 普通片显示一个关联标签，供暖片显示两个，无关联片显示空状态。
- 筛选隐藏全部关联片时跳转标签禁用。
- 点击和键盘激活能定位正确卡片并触发短暂高亮。
- LOOP Tooltip DOM、函数、事件和 CSS 不再存在。
- LOOP 卡片点击、Enter/Space、关系线、显示全部和大 LOOP 淡化无回归。

### 10.3 浏览器

- 桌面确认 17 个小 LOOP、6 类统计、详情正向跳转和定位高亮。
- 移动端确认统计区、关联标签和 LOOP 主链无页面横向溢出。
- 供暖片可分别跳到“建筑生产”和“临时供暖强化”。
- 页面没有 LOOP 悬浮窗。

## 11. 文档与交付

同步更新：

- `.cursor/skills/game-early-experience-breakdown/SKILL.md`
- `.cursor/skills/game-early-experience-breakdown/reference.md`
- `session/requirements/game-early-experience-breakdown.md`
- `session/session.md`

重建：

- `artifacts/frost-early-experience/viewer/index.html`
- `artifacts/frost-early-experience/viewer/data.json`

本轮不修改飞书页签，不创建 Git commit。
