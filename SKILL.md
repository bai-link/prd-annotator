---
name: prd-annotator
description: 为现有 HTML 原型添加组件级 PRD 旁注，维护结构化备注、增量补丁和可追溯文档。在用户要求原型标注、业务规则说明、备注同步或增量维护时使用；不代替业务制度裁定，不默认重做原型。
---

# 原型 PRD 备注器

基于原型与用户提供的需求资料，维护 `scan.json` 候选清单、`notes.json` 备注源、Markdown 文档及交互旁注副本。保留原型行为、布局和原文件。

## 先界定事实

- 用户本次明确要求优先于旧稿与原型。用户已确认的制度、权限矩阵和流程为需求依据；代码只证明“当前实现”，不能把 bug 自动写成规则。
- 冲突时记录“依据 / 当前行为 / 待确认点”，标 draft。对未影响当前任务的冲突继续工作，仅就阻断问题提问。只有用户或评审确认的内容标 confirmed。
- 默认分析一期、当前有效页面与最终生效函数。扫描器是正则和 HTML 解析的候选发现器，不能证明动态权限或最终状态；覆盖率不是业务正确率。
- 不将某个项目的角色名称、状态、金额算法、日期门槛、按钮字数或演示缓存方式固化为其他项目要求。

## 执行

脚本使用 Python 3.8+ 标准库。以下 `S` 指本 skill 的 `scripts` 目录；Windows 使用实际路径并为含空格路径加引号。安装目录由宿主决定，不限定 WorkBuddy。

```text
python <S>/prd_scan.py prototype.html -o .prd/scan.json
python <S>/prd_notes.py init --scan .prd/scan.json -o .prd/notes.json
python <S>/prd_notes.py merge --notes .prd/notes.json --patch patch.json --overwrite
python <S>/prd_notes.py check --notes .prd/notes.json --scan .prd/scan.json
python <S>/prd_notes.py render --notes .prd/notes.json --scan .prd/scan.json -o PRD备注.md
python <S>/prd_notes.py inject prototype.html --notes .prd/notes.json -o prototype-annotated.html
```

1. 读原型、明确版本及业务资料。扫描并核实候选；已删除的组织环节、演示专用按钮不能成为新需求。
2. 对复杂动态原型，顺着最终 `actions/guard/move` 覆盖链读权限与迁移；必要时用可用浏览器验证最终角色、状态和按钮。工具不可用时如实注明未验证。
3. 备注尽量短：谁能做、前提、必填与条件字段、成功后状态/待办、失败与只读行为。弹窗、抽屉标注明确打开、提交、取消、关闭行为。金额算法区分手填、试算、批准与实际值。
4. 按需读 [字段与补丁](references/note-format.md)、[锚点规则](references/anchor-rules.md)、[业务核对清单](references/business-review.md)。不要为填满栏目而编造规则。
5. check 非零说明未通过；修正或说明剩余差距，不能宣称“已全部验证”。抽查注入后原按钮、角色切换、动态重渲染与弹层正常，原文件哈希不变。

## 锚点与增量

优先复用稳定标识。允许编辑副本时可使用 `data-prd-anchor="action:account"`，页面归属用 `data-prd-page`。显式锚点须唯一；不要依赖标题文案、行号或 DOM 顺序。未获原型修改授权时使用现有 id 或备注 css，不强行向原文件加属性。

重新扫描后，init 只补缺失骨架；旧条目不丢失。源码指纹改变只提示复核，不自动改规则。复核单条后更新指纹：

```text
python <S>/prd_notes.py ack --notes .prd/notes.json --scan .prd/scan.json --anchor action:account
```

先更新备注内容再 ack；不能批量盲目确认。消失项人工核实后标 deprecated。自定义 css 在重渲染后可能失效，应现场核验；静态扫描不验证 css 是否匹配。

## 副本编辑与同步

角标 ? 打开规则卡，可编辑、新增、删除并导出 `annotations-patch.json`。本地编辑只暂存于当前浏览器的当前副本路径，**尚未写回 notes.json 或正式 PRD**。导出后 merge，再 check/render/inject。跨版本、迁移路径或交给别人前先导出补丁；存储被禁用时不承诺持久化。

- inject 默认输出原型同目录的 `*-annotated.html`，保持相对资源路径；换目录须复制资源或验证链接。
- 重复 inject 会替换已有面板；禁止覆盖输入文件。渲染文档不代表新需求已获批准，也不会凭空给文档版本 +1。
- 仅上传 skill、合成测试资料；不自动上传客户原型、业务附件、个人路径、缓存或凭据。发布目标和授权以用户当前请求为准。

## 旁注呈现与迁移验收（v1.3）

- 逐一核对标题、内容和落点的语义：工作台标题只解释整体用途，演示日期／刷新说明挂在演示入口；队列说明挂队列标题，不挂首条记录。动作说明挂对应动作或字段，不能用宽泛的容器凑位置。
- CSS 显式落点优先；有多个可见匹配时不猜测。通过 `window.__PRD_ANNOTATION_AUDIT__` 查看当前挂载结果；不在当前角色/状态下的节点应标为未匹配或隐藏，不能据此直接判丢失。
- 默认角标作为 body 下的独立浮动按钮定位，不插入业务 DOM，不修改按钮子节点、网格布局及 `:last-child` 关系。滚动容器中不能留半截或脱离目标的角标。
- 打开真实弹窗/抽屉时只保留最上层内部旁注，隐藏背景角标及工具条；关闭后恢复。内联表单不是遮罩弹窗；自定义弹层应有 dialog/aria-modal 或提供适配，不能假设所有宿主类名一样。
- 规则文字迁入旁注时，明确选中静态说明，填写 `replaces` 的精确选择器和原文；注入后只在单一匹配且文字一致时收起。不得按“所有蓝色提示框”或“所有 small 标签”批量隐藏，校验错误、退回理由、试算结果、记录数据必须保留。
- 抽查紧凑按钮和页眉，角标与主按钮分别可点，工具条不遮住提交/关闭。检测原文件哈希、重渲染后锚点、滚动/缩放、打开关闭弹层后的恢复。宿主特有问题用项目适配解决，不将其业务状态固化进通用 skill。

浏览器回归测试见 [tests/browser-regressions.cjs](tests/browser-regressions.cjs)；开发环境可安装 Playwright 后运行，日常 Python 命令仍只需标准库。
