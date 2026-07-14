# Early Stage Experience Breakdown

游戏前期体验拆解的独立备份与静态发布仓库。

## GitHub Pages

- 寒霜：<https://sherlock3rd.github.io/early_stage/?dataset=frost>
- 三国：冰河时代（三冰）：<https://sherlock3rd.github.io/early_stage/?dataset=sanbing>
- 寒霜数据：<https://sherlock3rd.github.io/early_stage/data/frost.json>
- 三冰数据：<https://sherlock3rd.github.io/early_stage/data/sanbing.json>

共享 `index.html` 只负责展示。每个拆解独占
`data/<dataset-id>.json` 与 `screenshots/<dataset-id>/`，避免不同游戏的数据和截图互相覆盖。

## 当前拆解

- 寒霜：28 个时间片，前期模拟求生至 SLG 大地图入口。
- 三国：冰河时代（三冰）：43:26、33 个时间片；主体流程分析到完整主城与出征准备完成，
  35–40 分钟片内确认世界坐标、行军队列和大地图讨伐。

## 内容

- `.cursor/skills/game-early-experience-breakdown/`：可复用 Skill、脚本和测试。
- `docs/superpowers/`：设计规格与实施计划。
- `session/requirements/`：需求记录。
- `mistakes/`：复盘规则。
- 根目录静态文件：共享查看器及各游戏独立分析数据库。
