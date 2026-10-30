# 备注字段与文档格式规范

## notes.json 结构

```json
{
  "meta": {"schema": 1, "prototype": "…html", "prototype_sha1": "…", "version": 1,
           "updated": "2026-10-30 14:28", "generator": "prd-annotator"},
  "notes": [ … ]
}
```

## 单条备注字段（格式统一，全部条目一致）

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| anchor | ✅ | 唯一键，`类型:标识`，见 anchor-rules.md |
| id | 自动 | 可读编号（anchor 的点号形式），仅展示 |
| kind / page / title | ✅ | 类型 / 归属页面（跨页面留空）/ 元素标题 |
| req | ✅* | 需求编号 `FR-<模块>-<序号>`；操作加 OP、弹窗加 D；`n/a` 条目可留空 |
| func | ✅* | 功能描述：这个元素做什么，1–2 句 |
| interaction | 建议 | 交互逻辑：有序步骤列表 |
| rules | ✅* | 业务规则：可判定的规则列表（含权限、校验、口径） |
| edges | ✅* | 边界情况：空 / 错 / 越权 / 并发 / 超限，尽量引用原型真实提示语 |
| accept | 可选 | 验收要点（Given/When/Then 或检查项） |
| status | ✅ | `draft` / `confirmed` / `n/a`（演示辅助、二期占位）/ `deprecated` |
| version / updated | 自动 | 字段改变时递增；ack 与废弃操作也递增 |
| hash / source | 自动 | 元素指纹与源码定位（line + ref），供追溯 |

\* `status=confirmed` 的条目必填；`n/a` 条目豁免。

## 渲染文档（PRD备注-<项目>.md）固定结构

1. **文档头**：原型文件名 + sha1、备注版本、条目数、覆盖率（分母只计纳管类型 page/action/dialog/state/rule）；
2. **一、备注总览**：全量条目表（编号 / 需求编号 / 元素 / 类型 / 锚点 / 状态）；
3. **二、按页面详述**：每页先列页面级备注，再列「本页关联元素」（操作、弹窗、字段等）；
4. **三、跨页面组件**：弹窗 / 状态 / 规则等无页面归属的条目，按类型分组；
5. **四、追溯说明**：锚点规则、源码定位口径、增量维护口径、状态口径 + 合规声明。

每条备注渲染为固定字段表：锚点 / 功能描述 / 交互逻辑 / 业务规则 / 边界情况 / 验收要点 / 源码定位 / 版本。

## 体检（check）口径

- 覆盖率 = 有备注的纳管元素 ÷ 纳管元素总数（默认纳管 page,action,dialog,state,rule，`--kinds` 可调）；
- 「需复核」：备注 hash ≠ 当前元素 hash（原型改动，文案可能过期）；
- 「孤儿」：备注锚点在原型中已找不到（保留不删，人工确认后标 deprecated）；
- 「待补」：confirmed/draft 条目缺 req、func、rules 或 edges；
- 结论「通过，可交付评审」需：无孤儿、无需复核、无待补。

## 团队协作约定

- notes.json 是唯一事实源：改备注走 `upsert / merge`，不要手编 JSON；
- 渲染出的 md 是交付物，不手改，重渲染即更新；
- 评审通过后把草稿条目 `--status confirmed`，保留版本号连续递增；
- 原型迭代后先 `check` 再补内容，保证备注与原型始终同源。

## 修改补丁 annotations-patch.json（旁注副本导出）

在旁注副本里增删改标注后，点「导出修改」得到的补丁格式如下，用 `merge --overwrite` 合并回 notes.json：

```json
{
  "updated": "2026-10-30 15:00",
  "notes": [
    {"anchor": "action:initial", "title": "…", "func": "…", "rules": ["…"], "edges": ["…"]},
    {"anchor": "custom:m1abc", "kind": "custom", "page": "dept-review", "title": "…",
     "req": "（自定义）", "func": "…", "rules": ["…"], "css": "…选择器…"}
  ],
  "deleted": ["action:delete"]
}
```

- `notes`：新增或修改的条目（`custom:*` 为页面上新增的自定义标注，`css` 字段是落点选择器，inject 后按它挂 `?`）；
- `deleted`：被删除的锚点，merge 时自动标 `deprecated`（保留不物理删除，可追溯）；
- 同一锚点以补丁为准覆盖；补丁未涉及的条目不受影响。


## v1.2 补充

- 可选 `evidence` 与 `decision` 字段用于记录依据及冲突决定，merge 保留这些字段；当前旁注卡与 Markdown 表不展示，评审时查 notes.json。不要将代码行为直接确认为正式规则。
- 数组补丁及 `{notes: [], deleted: []}` 均支持；`css` 自定义落点在合并和注入时保留。
- check 返回 0 表示本次静态体检通过，返回 1 表示有缺项/孤儿/变更/重复或非法状态；不证明运行行为与业务制度一致。
- deprecated 不再要求补齐，不注入副本；custom 锚点不因静态扫描缺失被判为孤儿，需浏览器核验 css。
- 浏览器缓存按副本路径隔离；同路径重新生成前应先导出旧补丁，防止旧编辑覆盖新备注。
