# 游戏前期体验分层 LOOP 流程设计

## 1. 目标

替换当前“聚落建设、战斗远征、英雄养成各一张巨型四格卡”的全局流程，改为参考图所表达的
“小节点组成小 LOOP，小 LOOP 串成大 LOOP”结构。

寒霜示例仍以 `0:00–25:00` 为主体范围，P8 完整主城解锁为主体终点；P9 进入 SLG 大地图只作
图外出口。本轮继续只修改本地 HTML 与统一分析数据，不修改飞书页签。

## 2. LOOP 分层口径

### 2.1 小 LOOP

只有同时满足以下条件的可观察体验才独立成小 LOOP：

1. 有明确的当前动机或压力。
2. 玩家执行一组连续、同目标的行为。
3. 行为产生即时可观察的奖励、反馈、能力或进度变化。
4. 奖励或新压力产生下一步目标，或推动玩家再次投入。

系统教学步骤作为环内行为，不按菜单、按钮或系统名称机械拆分。固定时间长度和任务步骤数量均不作为
拆环依据。

### 2.2 大 LOOP

大 LOOP 是多个小 LOOP 的共同系统归属，不再作为四格节点。寒霜固定包含：

- `settlement`：聚落建设。
- `expedition`：战斗远征。
- `hero_growth`：英雄成长。

每个小 LOOP 只能有一个主要 `macro_loop_id`。涉及其他系统的输入、输出和回投，通过跨环连线表达，
不得复制同一小 LOOP 到多个大 LOOP。

### 2.3 线性节点

一次性剧情高潮、模式切换、阶段里程碑和不产生再投入的揭示继续使用线性节点，不伪造成小 LOOP。

## 3. 寒霜时间主链

主体范围按真实时间顺序包含 16 个小 LOOP：

| 顺序 | ID | 时间片 | 小 LOOP | 大 LOOP |
|---|---|---|---|---|
| 1 | `settlement-survival-landing` | 0–1 | 暴风雪落脚 | 聚落建设 |
| 2 | `legacy-transition` | 2 | 比尔去世与遗志转换（线性） | 无 |
| 3 | `settlement-legacy-start` | 3 | 遗志建设启动 | 聚落建设 |
| 4 | `settlement-build-queue` | 4 | 建造队列运转 | 聚落建设 |
| 5 | `settlement-infrastructure` | 5 | 基础设施扩张 | 聚落建设 |
| 6 | `settlement-production-unlock` | 6 | 生产建筑解锁 | 聚落建设 |
| 7 | `settlement-expedition-ready` | 7 | 出征前集中扩建 | 聚落建设 |
| 8 | `expedition-first-sortie` | 8–9 | 首次出征 | 战斗远征 |
| 9 | `hero-recruit-and-deploy` | 10–11 | 英雄招募入队 | 英雄成长 |
| 10 | `settlement-expedition-reinvest` | 12–13 | 远征收益回投 | 聚落建设 |
| 11 | `expedition-second-launch` | 14 | 第二次远征开启 | 战斗远征 |
| 12 | `hero-post-battle-growth` | 15–16 | 战后养成整理 | 英雄成长 |
| 13 | `expedition-ice-river-push` | 17–18 | 冰河连续战斗 | 战斗远征 |
| 14 | `settlement-return-cleanup` | 19 | 战后返乡清理 | 聚落建设 |
| 15 | `settlement-heating-production` | 20 | 供暖生产 | 聚落建设 |
| 16 | `settlement-cold-policy` | 21 | 极寒法令决策 | 聚落建设 |
| 17 | `settlement-resource-sprint` | 22–23 | 资源门槛冲刺 | 聚落建设 |
| 18 | `main-city-end` | 24 | 完整主城解锁（主体终点） | 无 |
| 19 | `slg-outside-exit` | 25 | 进入 SLG 大地图（图外出口） | 无 |

表中 16 个 `micro_loop` 加 2 个主体线性节点；图外出口不计入主体 LOOP 数量。

### 3.1 小 LOOP 内容

每个小 LOOP 必须分别填写：

- `motivation`：玩家此刻为何投入。
- `behaviors`：连续同目标行为，可为 1～4 项。
- `reward`：直接可观察的即时反馈。
- `next_motivation`：奖励或压力如何推动下一步。
- `slice_indices`：所有关联时间片。
- `evidence_frames`：直接证明环内关键步骤的现有图片。
- `confidence`：取关联时间片中的最低置信度。

禁止把“建设、战斗、养成”本身当作四段内容；四段必须描述具体事件。

### 3.2 跨环关系

寒霜至少表达以下关系：

- 出征前集中扩建 → 首次出征。
- 首次出征奖励 → 远征收益回投。
- 首次出征压力 → 英雄招募入队。
- 英雄招募入队 → 第二次远征。
- 第二次远征压力 → 战后养成整理。
- 战后养成整理 → 冰河连续战斗。
- 冰河战果 → 战后返乡清理。

同一大 LOOP 被其他内容打断后再次出现，使用 `macro_return`；不同大 LOOP 之间的输入输出使用
`cross_macro`。

## 4. 数据契约

`global_loops` 调整为：

```json
{
  "scope": {
    "start": 0,
    "end": 1500,
    "end_label": "完整主城解锁",
    "outside_exit_label": "进入SLG大地图"
  },
  "macro_loops": [
    {
      "id": "settlement",
      "title": "聚落建设",
      "accent": "settlement",
      "summary": "通过建设、生产与政策把生存压力转化为聚落成长。"
    }
  ],
  "nodes": [
    {
      "id": "settlement-build-queue",
      "type": "micro_loop",
      "title": "建造队列运转",
      "summary": "通过队列和派遣推进多建筑施工。",
      "macro_loop_id": "settlement",
      "slice_indices": [4],
      "evidence_frames": ["frames/slice-004-evidence-01-000245000.jpg"],
      "status": "confirmed",
      "confidence": 0.88,
      "motivation": "多建筑同时推进，不能空手等待。",
      "behaviors": ["配置建造队列", "安排幸存者"],
      "reward": "大熔炉与施工进度提升。",
      "next_motivation": "继续扩建功能建筑并补足资源。"
    }
  ],
  "edges": [
    {
      "from": "settlement-expedition-ready",
      "to": "expedition-first-sortie",
      "kind": "cross_macro",
      "label": "建设完成出征准备"
    }
  ]
}
```

### 4.1 `macro_loops`

- 必须是非空数组。
- `id` 全局唯一；`title`、`summary` 非空。
- `accent` 只允许 `settlement`、`expedition`、`hero_growth`。
- 寒霜三个枚举必须各出现一次。

### 4.2 `nodes`

节点类型调整为：

- `micro_loop`
- `transition`
- `end`
- `outside_exit`

`micro_loop` 必须包含合法 `macro_loop_id`、`motivation`、非空 `behaviors`、`reward`、
`next_motivation` 和 `confidence`。其他节点的 `macro_loop_id` 必须为空，且不得携带小 LOOP 四段字段。

全部主体节点必须按最早关联时间片排序。不同小 LOOP 可以引用同一时间片，但必须描述该时间片中不同且
有证据的闭环；不得复制同义内容。

### 4.3 `edges`

边类型调整为：

- `primary`：真实时间主链。
- `macro_return`：同一大 LOOP 的后续分段回归。
- `cross_macro`：不同大 LOOP 的输入输出。
- `conditional`：主体终点到图外出口。

校验规则：

- `primary` 必须从入口或首个主体节点连续覆盖到唯一主体终点。
- `macro_return` 两端必须属于同一大 LOOP，且中间至少存在其他大 LOOP 或线性节点。
- `cross_macro` 两端必须属于不同大 LOOP。
- `conditional` 只允许唯一主体终点指向唯一图外出口。
- 不允许悬空边、重复边、孤立主体节点、出口回流和时间逆序的 `primary`。

## 5. HTML 视觉设计

### 5.1 阅读顺序

桌面端使用自上而下的真实时间主链。每个小 LOOP 占一行：

1. 左侧显示时间、名称和大 LOOP 标签。
2. 右侧直接展开四个紧凑节点：动机 → 行为 → 奖励 → 下一动机。
3. 点击整行跳转到首个当前可见关联时间片。

线性节点横跨主链显示，不绘制四段结构。

### 5.2 分段大 LOOP 背景带

连续属于同一大 LOOP 的小 LOOP 共享半透明色带：

- 聚落建设：青蓝。
- 战斗远征：橙红。
- 英雄成长：紫色。

同一大 LOOP 被打断后重新出现时创建新的同色分段，并通过同色虚线回流轨道连接。大 LOOP 色带只表达
归属，不替代具体小 LOOP 内容。

### 5.3 小 LOOP 四段色义

- 动机：黄色。
- 行为：紫蓝色。
- 奖励：绿色。
- 下一动机：黄色虚线。

四段之间使用短箭头。跨环箭头从具体奖励或下一动机连接到后续小 LOOP 的动机节点，不连接整张卡片。

### 5.4 筛选与交互

- 顶部提供三个大 LOOP 开关和“显示全部”。
- 关闭某一大 LOOP 时只淡化其小 LOOP、背景带和关系线，不移除节点，不改变时间顺序。
- 悬停或键盘聚焦四段节点时显示时间、解释和证据图。
- 点击小 LOOP 行跳转详情；筛选导致所有关联片不可见时置灰并禁用。
- Escape 关闭 Tooltip；Enter/Space 激活小 LOOP。

### 5.5 移动端

- 四段节点改为纵向排列。
- SVG 大范围回流线隐藏，改为每行底部的“来自／流向”关系标签，必须显示起点、终点和关系说明。
- 页面不得产生横向滚动；Tooltip 固定在视口底部。

## 6. 错误处理与兼容性

- 这是 `global_loops` 的严格契约升级；旧的三个巨型 `loop` 节点不再合法，必须迁移为
  `macro_loops + micro_loop`。
- Viewer 单独捕获分层流程渲染错误并显示局部错误，不影响情绪曲线、时间轴和详情。
- 手动选择 JSON 时，所有未知文本值仍必须 HTML 转义。
- 证据图片失败时显示占位说明，不隐藏小 LOOP 文本。
- 飞书写入继续忽略 `global_loops` 内容，但共享校验器会拒绝未迁移的旧 analysis。

## 7. 测试与验收

### 7.1 自动化

- 16 个寒霜主体小 LOOP、3 个大 LOOP、2 个主体线性节点和 1 个图外出口数量正确。
- 小 LOOP 四段完整、主归属唯一、置信度合法、证据属于关联时间片。
- `macro_return`、`cross_macro` 和 `conditional` 端点语义正确。
- 主链按时间递增，无孤立节点、重复边和出口回流。
- Viewer 安全转义所有文本并正确生成小 LOOP 四段。
- 大 LOOP 开关只淡化，不删除或重排节点。
- 移动端关系标签完整且无横向溢出。

### 7.2 浏览器

桌面 1440px：

- 16 个小 LOOP 按真实时间顺序可见。
- 聚落、远征、英雄形成分段色带，不再出现三张巨型四格卡。
- 跨环箭头连接具体奖励/动机节点。
- 点击、键盘、筛选和证据 Tooltip 正常。
- 无页面横向溢出。

移动 390px：

- 四段纵向排列。
- 关系标签可识别起点、终点和方向。
- Tooltip 位于视口内，无横向溢出。

## 8. 交付

重建：

`artifacts/frost-early-experience/viewer/index.html`

同时同步 Skill、reference、需求记录和会话记录。本轮不修改飞书。
