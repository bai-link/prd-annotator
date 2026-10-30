# prd-annotator · 原型 PRD 备注器

为已有 HTML 原型添加可交互的业务说明，并把备注保存成可维护、可追溯的 PRD 文档。

**当前版本：v1.3.0** · Python 3.8+ · 运行脚本仅使用标准库

适合产品经理给开发、测试和评审人员解释：谁能操作、字段什么时候必填、提交后怎么流转，以及哪些情况需要拦截。

## 能做什么

- 扫描 HTML，发现页面、按钮、弹窗、状态、字段等可标注对象。
- 维护 `notes.json`，统一存储功能、交互、业务规则、边界和验收要点。
- 生成带 `?` 角标的原型副本，点击组件旁的角标查看、编辑说明。
- 导出网页中的修改补丁，再合并回备注源并重新生成文档。
- 原型更新后检查锚点和源码指纹，提示哪些备注需要复核。
- 保留原型本体；重复注入替换已有备注面板，避免叠加。

**它不自动裁定业务制度，也不保证把任意 JavaScript 应用完整解析成需求。** 扫描结果是候选清单，复杂权限和动态流转仍需结合实际页面核对。

## v1.3.0 改进

- 角标独立定位，不再修改原型控件的内部结构，减少裁切和布局干扰。
- 弹窗／抽屉打开时只显示当前层内的标注，背景角标和工具条自动隐藏。
- 显式 CSS 落点优先，歧义不随意匹配；运行时挂载报告可用于排查错位。
- 支持 `replaces` 精确收起已经迁入旁注的静态规则，保留错误、实时结果与输入区。
- n/a 候选不再注入；新增浏览器回归测试，覆盖本轮实际使用中遇到的问题。

## 安装

下载本仓库 ZIP，解压后把包含 `SKILL.md` 的目录命名为 `prd-annotator`，放入所用 AI 工具的 skill 目录。

| 工具 | 常用用户级目录 |
| --- | --- |
| Codex | `~/.codex/skills/prd-annotator/` |
| WorkBuddy | `~/.workbuddy/skills/prd-annotator/` |
| 其他支持 SKILL.md 的工具 | 按该工具的安装说明配置 |

避免多嵌套一层，正确结构应为 `skills/prd-annotator/SKILL.md`。根据宿主要求刷新或重新打开会话后使用。也可以不安装 skill，直接运行仓库脚本。

## 交给 AI 使用

把原型和相关 PRD／制度资料一起提供，并明确本次要处理的版本。例如：

> 使用 prd-annotator，为这个 HTML 原型添加简洁的组件级 PRD 旁注。保留原型本体，另出带标注的副本和 Markdown 文档。以我确认的权限矩阵为依据，原型行为与制度冲突的地方标为待确认，不要自行确认为需求。重点说明条件必填、角色权限、状态流转和边界情况。

后续更新时：

> 原型已更新，请复用原有 notes.json，检查变化并增量维护，保留已确认且未受影响的备注。

AI 执行规范见 [SKILL.md](SKILL.md)。本 README 面向使用者，SKILL.md 面向执行任务的 AI。

## 手动使用

以下命令在仓库根目录运行。将 `prototype.html` 换成你的原型路径，包含空格时加引号；Python 命令也可按本机环境使用 `python3`。

### 1. 扫描并建立备注骨架

```bash
python scripts/prd_scan.py prototype.html -o .prd/scan.json
python scripts/prd_notes.py init --scan .prd/scan.json -o .prd/notes.json
```

默认初始化 page、action、dialog、state、rule 类型。扫描不等于自动撰写备注，接下来需要根据需求资料补充内容。纳管字段或控件时，可在 init 和 check 中使用一致的 `--kinds`。

### 2. 填写或合并备注

修改补丁格式示例：

```json
{
  "notes": [
    {
      "anchor": "action:save",
      "title": "保存",
      "req": "FR-SAVE-01",
      "func": "保存当前表单。",
      "rules": ["仅有编辑权限的用户可以保存。"],
      "edges": ["必填项缺失时提示，保留已填内容。"],
      "status": "draft"
    }
  ],
  "deleted": []
}
```

这是格式示意，`anchor` 应换成扫描清单中的实际锚点，文案也应按实际需求填写。未确认的内容保留 draft，不能仅因代码存在就标 confirmed。

```bash
python scripts/prd_notes.py merge --notes .prd/notes.json --patch patch.json --overwrite
```

`--overwrite` 覆盖补丁涉及的现有字段，未涉及的备注保留。补丁中的 `deleted` 将条目标为 deprecated，不物理删除历史条目。更多示例见 [examples/notes-patch.sample.json](examples/notes-patch.sample.json)。

### 3. 体检与生成交付物

```bash
python scripts/prd_notes.py check --notes .prd/notes.json --scan .prd/scan.json
python scripts/prd_notes.py render --notes .prd/notes.json --scan .prd/scan.json -o PRD备注.md
python scripts/prd_notes.py inject prototype.html --notes .prd/notes.json -o prototype-annotated.html
```

check 返回 0 表示本次静态体检通过，返回 1 表示仍有待处理项。体检不等于业务验收，draft 也不会因此自动变为 confirmed。

注入副本尽量放在原型同目录，避免图片、样式和脚本的相对路径失效。输入和输出不能是同一个文件。

### 4. 在网页中编辑并同步

打开 `prototype-annotated.html`：

1. 点击 `?` 查看规则卡；卡片内可编辑或删除备注。
2. 右下角可新增标注、显示／隐藏标注、导出修改。
3. 导出 `annotations-patch.json`，再合并回备注源。

```bash
python scripts/prd_notes.py merge --notes .prd/notes.json --patch annotations-patch.json --overwrite
```

然后重新执行 check、render 和 inject。**网页内的保存只暂存在当前浏览器，并未直接修改磁盘上的 notes.json。** 更换浏览器、迁移副本或重新生成前，先导出补丁；浏览器禁止存储时，不保证关闭后仍保留编辑。

### 5. 原型变更后复核

重新扫描并执行 check。指纹变化的条目先核对和修改备注，再逐条确认：

```bash
python scripts/prd_notes.py ack --notes .prd/notes.json --scan .prd/scan.json --anchor action:save
```

ack 更新该条源码指纹与定位，不代表批准需求，不应对未核对条目盲目执行。

## 文件说明

| 文件 | 用途 |
| --- | --- |
| `SKILL.md` | AI 的入口规范 |
| `scripts/prd_scan.py` | 原型元素扫描 |
| `scripts/prd_notes.py` | 初始化、增量合并、体检、渲染、注入与复核 |
| `references/anchor-rules.md` | 锚点及扫描能力边界 |
| `references/note-format.md` | 字段、状态和补丁约定 |
| `references/business-review.md` | 业务规则核对清单 |
| `examples/notes-patch.sample.json` | 补丁样例 |
| `tests/test_regressions.py` | 脚本回归测试 |
| `VERSION` | 当前版本 |

项目内产生的 `.prd/notes.json` 是备注源；Markdown 和旁注 HTML 是生成物，后续修改应回到备注源维护。

## 验证

```bash
python -m unittest discover -s tests -v
```

仓库已配置 GitHub Actions，在 Windows／Linux、Python 3.8／3.12 上运行回归测试。测试覆盖数组补丁、自定义落点保留、指纹复核、重复注入、原文件防覆盖、脚本文本转义及重复显式锚点等场景。网页视觉与复杂原型行为还需在实际浏览器中抽查。

## 已知边界

- 正则扫描可能识别到旧函数、演示代码或已被后续逻辑覆盖的候选，必须核实最终生效行为。
- 指纹是源码片段变化提示，不是完整语义分析；权限矩阵或被调用函数改变时也要主动复核。
- 自定义 CSS 落点可能随页面重构失效。可编辑原型时，优先使用唯一的 `data-prd-anchor`；不要未经授权修改原型本体。
- 浏览器暂存按副本路径隔离；同一路径的新版本仍可能读取旧补丁，重新生成前先导出并处理旧编辑。
- 发布 skill 时不要顺带上传客户原型、业务附件、生成备注或凭据。

### 可选浏览器回归

```bash
npm install --no-save playwright
npx playwright install chromium
node tests/browser-regressions.cjs
```

开发测试依赖不会影响 Python 脚本的标准库运行方式。可用 `PLAYWRIGHT_MODULE`、`CHROMIUM_PATH`、`PYTHON` 环境变量指定已有运行环境。自定义弹层和特殊布局仍需在真实宿主页面验收；合成测试通过不等于每个项目已经验证。
