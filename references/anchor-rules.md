# 锚点与扫描规则

## 锚点命名

| 类型 | 锚点格式 | 绑定的代码标识 | 稳定性依据 |
| --- | --- | --- | --- |
| 页面 | `page:<key>` | `<section class="page" id="p-<key>">` + TITLES 映射 | 页面 id 由导航与渲染派发共用，重构不易改 |
| 操作 | `action:<key>` | `actions()` 中 `a.push(['<key>', label])` | key 同时驱动按钮、权限、角标计数 |
| 弹窗 | `dialog:<标题>` | `showModal('<标题>', …)` 的标题字面量 | 弹窗标题即用户可见语义 |
| 状态 | `state:<名称>` | `const FLOW=[…]` 状态集合 | 状态机词汇表 |
| 规则 | `rule:<函数名>` | guard / move / log / final / own / canSee / late | 系统级横切函数 |
| 卡片 | `card:<标题>` | `div.card > h3` 标题文本 | 页面区块语义 |
| 字段 | `field:<id>` | `field('<id>', '<label>')` | 表单字段 id |
| 控件 | `control:<id>` | 静态 HTML 元素 id | 静态原型兜底 |

## 为什么不用行号和 DOM 顺序做锚点

- 行号随格式化、增删代码漂移；
- 这类原型的 DOM 由 JS 渲染，静态解析拿不到运行时结构；
- 代码标识（id / key / 标题 / 状态值）同时被渲染逻辑引用，是天然稳定的语义锚点。

行号与 hash 仍然记录在 scan.json 中，仅用于辅助定位与变更检测：hash = 元素上下文片段（±110 字符）的 SHA1 前 8 位。

## 扫描器识别策略

1. **配置驱动单页应用**（主路径）：识别 `const TITLES`、`const FLOW`、`function actions()`、`showModal(`、`function guard/move/log/…` 等特征后按上表抽取；
2. **静态 HTML 兜底**：无上述特征时，抽取 `[id]` 控件、卡片标题等；
3. 模板字符串里的假标题（含 `'`、`+`、`$`、`{`）自动过滤；弹窗标题末尾装饰符（·）自动去除；
4. scan.json 结构：

```json
{
  "tool": "prd_scan/1.0",
  "scanned_at": "…",
  "prototype": {"path": "…", "sha1": "…", "bytes": 0, "lines": 0},
  "counts": {"page": 13, "action": 19, "dialog": 27, "state": 20, "rule": 7},
  "elements": [
    {"kind": "action", "key": "account", "anchor": "action:account",
     "title": "财务核算", "page": "", "line": 636, "hash": "a1b2c3d4",
     "ref": "actions(): a.push(['account', …])"}
  ]
}
```

## 多层补丁原型的注意点

终版原型常有多层覆写（如 `move` 被重定义、`PAGE_RULES.<page>` 多次赋值）。扫描器只负责定位锚点；**撰写备注时以最后一层生效逻辑为准**，必要时追溯调用链确认真实迁移目标，并把补丁行为写进「业务规则」。

## v1.2 扫描能力边界

- 显式 `data-prd-anchor` 优先，支持单/双引号属性、跨行标签；同页重复显式锚点报错。控件 id 是兜底，普通 input 不要求结束标签。
- actions 追加分支会在整个源码中发现，但已被过滤的操作、旧定义及测试文字也可能成为候选；扫描不会执行 JavaScript，也不推断最终有效权限。必须分析最终函数或浏览器核验后再纳管。
- 指纹是片段变化提示，不是完整语义差异分析。外围变量、被调用函数或权限矩阵变化未必改变该指纹；业务规则变动时仍应主动核对相关备注。
- 标题、中文状态和自定义 css 均可能随迭代改变。长期稳定锚点由调用方维护；标注不能承诺自动追踪任意重构。
