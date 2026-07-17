# Early Stage Experience Breakdown

游戏前期体验拆解的独立备份与静态发布仓库。

## GitHub Pages

- 寒霜：<https://sherlock3rd.github.io/early_stage/?dataset=frost>
- 三国：冰河时代（三冰）：<https://sherlock3rd.github.io/early_stage/?dataset=sanbing>
- Dark War：<https://sherlock3rd.github.io/early_stage/?dataset=dark-war>
- AOO：<https://sherlock3rd.github.io/early_stage/?dataset=aoo>
- Beboo Bash：<https://sherlock3rd.github.io/early_stage/?dataset=beboo>
- Narco Empire：<https://sherlock3rd.github.io/early_stage/?dataset=narco-empire>
- Last War：<https://sherlock3rd.github.io/early_stage/?dataset=last-war>

共享 `index.html` 只负责展示。每个拆解独占
`data/<dataset-id>.json` 与 `screenshots/<dataset-id>/`，避免不同游戏的数据和截图互相覆盖。

## 当前拆解

- 寒霜：28 个时间片，前期模拟求生至 SLG 大地图入口。
- 三国：冰河时代（三冰）：43:26、33 个时间片；主体流程分析到完整主城与出征准备完成，
  35–40 分钟片内确认世界坐标、行军队列和大地图讨伐。
- Dark War：61:35、37 个时间片，约 47:00 进入 SLG 大地图。
- AOO：31:07.9、31 个时间片，28:58.5 进入 SLG 世界大地图。
- Beboo Bash：73:03.1、38 个时间片；22:17 进入普通开放探索地图，体验趋势覆盖完整录屏。
- Narco Empire：60:00.1、37 个时间片；53:19.5 首次进入 SLG 世界大地图，
  后续画面确认世界坐标、联盟入口与其他据点。
- Last War：43:40.1、33 个时间片；19:59.25 首次进入战区 #2297 世界大地图；
  录制启停产生的系统控制中心画面已从玩法证据与体验评分中排除。

## 内容

- `.cursor/skills/game-early-experience-breakdown/`：可复用 Skill、脚本和测试。
- `docs/superpowers/`：设计规格与实施计划。
- `session/requirements/`：需求记录。
- `mistakes/`：复盘规则。
- 根目录静态文件：共享查看器及各游戏独立分析数据库。
