# 前期体验共享查看器设计

## 目标

使用一个 `index.html` 查看寒霜、三冰及后续游戏拆解，通过标题区数据集切换器选择项目；
删除无效的关键词筛选，仅保留阶段和关键节点筛选。

## 统一目录

默认本地交付改为：

```text
artifacts/early-experience/viewer/
  index.html
  data/
    datasets.json
    frost.json
    sanbing.json
  screenshots/
    frost/
    sanbing/
```

旧的 `artifacts/frost-early-experience/viewer/` 与
`artifacts/sanbing-early-experience/viewer/` 暂时保留兼容，不再作为默认查看入口。

## 数据集清单

`build_viewer.py` 在命名数据集构建成功时维护 `data/datasets.json`：

```json
{
  "datasets": [
    {"id": "frost", "label": "寒霜"},
    {"id": "sanbing", "label": "三冰"}
  ]
}
```

- 构建新 ID 时保留旧条目和旧数据。
- 重建同名 ID 时更新标签，不重复添加。
- ID 继续只允许小写字母、数字和连字符。
- 构建命令增加可选 `--dataset-name`；未提供时使用数据集 ID。

## 页面交互

- 标题区右上角显示“拆解项目”下拉切换器，位于统计卡左侧。
- 页面先读取 `data/datasets.json`，按清单渲染选项并选中当前 `?dataset=`。
- 切换时只修改 URL 的 `dataset` 参数并重新加载，避免残留上一项目的筛选、曲线和详情状态。
- 清单读取失败时至少显示当前已加载数据集，不阻塞单数据集查看。
- 完全删除关键词输入框、关键词搜索文本构建和对应监听。
- 阶段、关键节点、重置筛选继续保留；筛选栏由三列改为紧凑布局。

## 验收

- 同一本地 `index.html` 可在寒霜和三冰之间切换。
- 切换后的标题、时长、阶段数、时间片、曲线、截图和 LOOP 均来自目标数据集。
- 页面不存在关键词输入框，阶段和关键节点筛选无回归。
- 构建第三个数据集会自动加入清单并保留前两个数据集。
- 非法 dataset 参数不能形成路径注入。
