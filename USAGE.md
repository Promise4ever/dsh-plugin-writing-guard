# Writing Guard 使用说明（v2.2.0）

面向「已经装好插件」的用户。插件随宿主启动自动加载，核心能力是**在你写论文类文件时自动做写作纪律审计**，外加 13 个可手动调用的审计/Word 工具。

---

## 0. 在 DSH 里怎么调用

三种入口，按场合选。

### A. 斜杠技能（最直接）

在输入框打 `/`，菜单里会出现 `writing-guard`；或直接敲：

```
/writing-guard 检查 manuscript.md 的写作质量，只报高危问题
```

宿主会把 SKILL.md 全文注入到这一轮上下文，模型随即知道该调哪些工具。
判据是 `dsh-tool-skill/lib/index.js:1101` 的正则 `/(^|\s)\/([a-z0-9]+(?:-[a-z0-9]+)*)(?=\s|$)/g`：`/` 后面必须是 kebab-case 名字，且前后要有空白或行首/行尾。所以 `/writing-guard,` 这种贴着标点写不会命中。

**Git Bash / MSYS 注意**：`dsh --profile x "/writing-guard ..."` 会被 MSYS 的路径转换吃掉，变成 `C:/Program Files/Git/writing-guard`。命令行里要加 `MSYS2_ARG_CONV_EXCL='*'`，或改用自然语言（方式 B）。GUI 输入框不受影响。

### B. 自然语言（最省心）

不用记名字，直接说需求，模型会自己挑工具：

```
帮我检查 manuscript.md 有没有修改过程残留
把 word-case.docx 的表格改成三线表
改完这一版，检查有没有把数据改坏
```

自动审计（第 1 节）也是走这条路 —— 你正常写文件，插件自己介入。

### C. 手动点名工具

需要精确控制参数时，直接点工具名：

```
用 writing_audit 检查 D:/papers/draft.md，profile=manuscript，verbose=true
对 D:/papers/before.docx 和 D:/papers/after.docx 跑 writing_word_scope_check，范围限定在 Results 到 Discussion 之间
```

13 个工具名见第 2 节。注意 `writing_word_scope_check` 只吃 `.docx`，传 `.md` 会失败。

### 命令行（headless）

```bash
dsh --profile <profile> "用 writing_audit 检查 D:/papers/manuscript.md"
```

`<profile>` 换成你自己的 profile 名（首次使用会初始化）。headless 一次性跑完就退出；加 `--json` 输出机器可读事件流。

> 手动工具（`writing_audit` / `writing_style_profile` / `writing_journal_profile`）目前**不**按会话工作目录解析相对路径，
> 会直接把它交给文件系统。**请一律传绝对路径**，否则解析到哪个目录取决于宿主进程，容易读错文件。
> Word 工具（`writing_word_*`）会按会话工作目录解析，但同样建议写绝对路径。

---

## 1. 它会自动做什么

启用后（`autoAuditOnWrite`，默认 **开**），当你用 `write` / `edit` / `ops_write_file` / `ops_edit_file` / `ops_replace` 写入一个「论文类文件」时，插件会在工具返回结果后追加一段控制块：

```
<writing_guard_control version="2.2.0" target="...\manuscript.md">
CONTROL METADATA ONLY. Do not quote, paraphrase, or transfer wording ...
added=4; resolved=0; remaining=4

finding rule=revised-family; severity=high; kind=violation; action=CUT; paragraph=0
finding rule=as-requested; severity=high; kind=violation; action=CUT; paragraph=0
finding rule=we-have-changed; severity=high; kind=violation; action=CUT; paragraph=0
finding rule=we-do-not-claim; severity=high; kind=candidate; action=TIGHTEN; paragraph=1
</writing_guard_control>
```

要点：

- 控制块是**给模型看的元数据**，不是稿件正文来源。它刻意不含原文片段和改写建议，避免控制词汇被复述进正文。
- 只有**本次新增**的问题会注入；已存在且未变化的问题不会重复灌进来（增量指纹 diff）。
- 把问题全部修掉会收到一条一次性通知：`写作纪律问题已全部清零`。

### 什么算「论文类文件」（两个条件同时满足）

1. 扩展名属于 `.md` `.markdown` `.tex` `.txt` `.docx`；
2. 路径中含论文特征词之一：`manuscript` `paper` `thesis` `revision` `revised` `response` `rebuttal` `cover` `review` `reviewer`（按词边界匹配，不会误伤 newspaper / coverage / synthesis），或中文 论文 / 稿件 / 修订 / 返修 / 回复 / 审稿；或文件位于工作区根下的 `01_manuscript` `02_reviews` `03_evidence` `08_response` `09_wiki/writing` 目录。

> 所以 `script.py` 不会触发，普通目录下的 `notes.md` 也不会。这不是漏检，是刻意的低噪声设计；想强制检查就用手动工具 `writing_audit`。
>
> **注意**：不存在「notes.md 一律排除」的规则。判定只看路径特征——`paper/notes.md`、`01_manuscript/notes.md`
> 这类路径**仍然会被审计**。

### 什么情况下不注入

| 情况 | 行为 |
| --- | --- |
| 非论文类路径 / 扩展名 | 不审计 |
| `dryRun` 预览、`rejected` / `error` / 未落盘的结果 | 不审计（只有真实 `applied` 才审） |
| 被宿主 `block` 的工具调用 | 不附加自动通知。注意 `block` 只是「不挂这条通知」，**工具结果当时已经写到磁盘，不会被回滚** |
| 问题集合与上次完全相同 | 不注入（无 added 也无 resolved） |

---

## 2. 手动调用的工具（13 个）

### 文本审计

| 工具 | 主要参数 | 用途 |
| --- | --- | --- |
| `writing_audit` | `text` 或 `filePath`，`profile`，`verbose`，`original`，`styleProfile`，`journalProfile` | 主力扫描：修改过程残留、主张校准、修辞模式、LLM 关联词、学术文体、格式 |
| `writing_delivery_audit` | `text`，`surface`，`baseline`，`rejectedTerms`，`rejectedClaims` | CAL 检测：被否决方案 / 修改过程是否泄漏进标题、文件名、commit、PR 等交付物 |
| `writing_rules` | 无 | 打印写作纪律速查清单，写稿前加载 |
| `writing_style_profile` | `filePath` 或 `learnDir` | 从作者历史论文蒸馏「句长 / 段长节奏指纹」 |
| `writing_journal_profile` | `filePath` 或 `learnDir`，`journal`，`articleType`，`discipline` | 从目标期刊代表论文蒸馏期刊写作档案 |

`writing_audit` 的 `profile` 取值：`manuscript` / `rebuttal` / `cover_letter` / `review` / `notes`。
**rebuttal 很重要**：在 rebuttal 里 `as requested` 是正常用语，不会报警。

典型组合（先建档再比对）：

1. `writing_style_profile({ learnDir: "我的历史论文目录" })` → 得到 styleProfile JSON
2. `writing_journal_profile({ learnDir: "目标期刊论文目录", journal: "Nature" })` → 得到 journalProfile JSON
3. `writing_audit({ filePath: "draft.md", profile: "manuscript", styleProfile: <1>, journalProfile: <2> })`

`original` 传修改前原文会开启 **Scholarship Lock + Epistemic Lock**：数字 / 百分比 / p 值 / CI / 引用 / 图表编号被改动按 HIGH 报；主张强度漂移（`associated` → `caused`）、否定与零结果翻转、scope 边界消失也会被抓。

### Word 工具（需要 Python + python-docx）

**Python 是所有 DOCX 操作的硬依赖**：8 个 `writing_word_*` 工具，**以及**对 `.docx` 调用 `writing_audit` 都需要。
`.md` / `.tex` / `.txt` 的审计不经过 Python。插件不会自动安装 `python-docx`，缺它时这些工具直接报错，
`postinstall` 只会探测并打印一条 `pip install python-docx` 的提示。

| 工具 | 主要参数 | 用途 |
| --- | --- | --- |
| `writing_word_scan` | `filePath` | 结构化扫描：标题层级、段落、表格、公式/图片等受保护节点，安全编辑第一步 |
| `writing_word_audit` | `filePath` | .docx 写作纪律检查（自动提取段落文本） |
| `writing_word_edit` | `filePath`，`replacements[{old,new}]`，`scopeConfig`，`mode`，`outputPath` | run-aware 局部替换，保留粗体/斜体/字体/颜色 |
| `writing_word_scope_check` | `fileBefore`，`fileAfter`，`scopeConfig` | 验证编辑没动到范围外内容 |
| `writing_word_format_tables` | `filePath`，`outputPath` | 全部表格转学术三线表（顶线 1.5pt / 表头底线 0.75pt / 底线 1.5pt） |
| `writing_word_fingerprint` | `filePath` | 生成基准格式指纹（styles/settings/numbering 哈希、math font、section geometry） |
| `writing_word_package_validate` | `filePath` | OOXML 包完整性：malformed XML、broken relationships、orphan media |
| `writing_word_audit_equations` | `filePath`，`baselinePath` | 原生 OMML 公式只读审计，可与基线比对格式漂移 |

Word 编辑推荐顺序：`scan` → `edit` → `scope_check` → `package_validate`。
默认**不改**页边距、页眉页脚、section break、页码、图片、参考文献、交叉引用、书签、脚注。

**两个必须知道的行为：**

1. **`writing_word_edit` 会对整篇文档统一默认学术格式**，不管 `mode` 是 `text_only` 还是 `structural`，也不管 `scopeConfig` 限定在哪一段。
   `scopeConfig` 只限制**文本替换**的范围，限制不了格式统一这一步。要求「只改文字、别碰格式」时，必须最后用
   `writing_word_scope_check` / `writing_word_fingerprint` 比对，不能只靠 `scopeConfig`。
2. **所有 Word 工具只吃 `.docx`**。`.doc`（旧版二进制）会被直接拒绝，先另存为 `.docx`。
   同理 `writing_word_scope_check` 的 `fileBefore` / `fileAfter` 也必须是 `.docx`——传 `.md` 会失败，
   要比较 Markdown 请用 `writing_audit` 的 `original` + `filePath`。

---

## 3. 配置

在 profile 的 `cordis.patch.yml` 里加：

```yaml
- id: dsh-plugin-writing-guard
  config:
    mode: balanced            # conservative | balanced | strict → 映射 high | medium | low（仅在没显式设 autoAuditMinSeverity 时生效）
    autoAuditOnWrite: true    # 写入论文类文件后自动审计（默认 true）
    autoAuditMinSeverity: high   # 显式设置永远优先于 mode：两者同时写，以这里为准
    maxAutoInjectPerTurn: 2   # 每轮最多注入几条通知（只限通知，状态照常跟踪）
    autoBrief: false          # 自动推纪律速查清单（默认关；机制见下）
    verboseByDefault: false   # 报告默认带修改建议
    projectResidueTerms:      # 追加的项目内部词表（命中按 medium 报）
      - my_internal_marker
    stateFile: ""             # 缺省 $DSH_HOME（或 ~/.dsh）/plugins/dsh-plugin-writing-guard/state.json
```

改完重启宿主，或在插件市场里关/开一次让 patch 层重载。

**mode 与 autoAuditMinSeverity 的优先级**：同时配置时 `autoAuditMinSeverity` 赢。
比如 `mode: balanced` + `autoAuditMinSeverity: high` → 实际门槛是 **high**（balanced 本来是 medium）。
上面示例里两行同时存在，等价于只用 high。

**autoBrief 不是「每轮」**：它在 agent 回合停止（turn-stopping）时按会话来判定，
只有**工作目录本身是论文路径**时才入队；第一次立刻入队，之后至少间隔 5 个回合；
消息在下一次模型请求前送达，不是当轮即时可见。

**state.json 不是缓存，删了会丢基线**：它在 `$DSH_HOME`（或 `~/.dsh`）下
`plugins/dsh-plugin-writing-guard/state.json`，除了各文件的**指纹集合**，还存**论文正文的明文 baseline**。
删掉它，跨轮次的「修改前 / 修改后」比对（Scholarship Lock / Epistemic Lock 的原料）就没了：
下次写入会重新建立基线，但已有的历史对比结果无法恢复。
另外，**正在运行的宿主可能在自己内存里缓存了状态并再次写回**——删文件前先退出宿主，否则可能被写回来。
（上限：20 个文件、单文件 512KB、总计 4MB，超出按时间淘汰。）

---

## 4. 安装 / 卸载

本 fork **没有发布 npm 包**；npm 上的 `dsh-plugin-writing-guard` 是上游原版，不含 rc.2 适配。

**唯一推荐形态：目录安装（`file:<绝对目录>`）**，目录里直接有 `package.json`。两种拿目录的方式：

1. `git clone https://github.com/Promise4ever/dsh-plugin-writing-guard.git` → `git checkout v2.2.0`
2. 下载 release ZIP，解压到一个**固定**目录

```bash
# 安装（<profile> 换成你自己的）
dsh plugin --profile <profile> add "file:D:/path/to/dsh-plugin-writing-guard"

# 重启宿主让 patch 层生效
dsh web

# 卸载
dsh plugin --profile <profile> remove dsh-plugin-writing-guard
```

> 装好后**不要移动或删除**这个目录：`file:` 依赖直接指向它，移走了就失效。

**报 `ERR_PNPM_IGNORED_BUILDS` 时**：pnpm 默认拦依赖的构建脚本（本插件的 `postinstall` 要装 skill、复制 Python 资源）。
把 **pnpm 原样打印的那个键**抄到 profile 的 `pnpm-workspace.yaml`，然后重跑：

```yaml
allowBuilds:
  dsh-plugin-writing-guard: true
```

**关于 tarball 的准确说法**：`dsh plugin add <某路径>.tgz` 能装成功，但在**带孤儿插件清理行为的 DSH Desktop 构建**上，
桌面壳启动时会把「`file:`/`link:` 依赖且目标不是目录」的插件当悬挂依赖静默卸载（判据 `is_dir()`，tgz 是文件恒为 false），
表现为「装完能用，重启后插件列表里就没了」。范围仅限**本地 `file:*.tgz`** 装在这类构建上；
目录形态不受影响。registry / HTTPS tarball 安装、纯 CLI profile 的情况**没有被证实**有问题，不要一概而论。

安装后 `postinstall` 会做三件事，但**都只在本机写文件，不装 Python 包**：

1. 把 skill 复制到 `$DSH_HOME/skills/writing-guard/`（无 `DSH_HOME` 时回退 `~/.dsh/skills/`）；
2. 把 Python 资源从 `src/word_guard` 复制到已安装包内的 `lib/word_guard`；
3. 探测 `python-docx`（跑 `python -c "import docx"`），**只打印 `pip install python-docx` 的提示，从不代为安装**。

缺 `python-docx` 时，所有 DOCX 相关操作（8 个 `writing_word_*` 工具 + 对 `.docx` 调 `writing_audit`）会报错；
对 `.md` / `.tex` / `.txt` 的审计不受影响。

---

## 5. 常见问题

**Q：我写了一个 .md，为什么没有注入？**
A：路径不含论文特征词。改名让路径里带 manuscript / paper / review 等，或直接手动调 `writing_audit`。

**Q：控制块里的问题，模型该怎么处理？**
A：`action=CUT` 优先删；`action=TIGHTEN` 收紧措辞；`REFRAME_TO_FACT` 表示去掉防御 / 审稿动机，只保留稿件本身支持的事实。需要的事实不在材料里就问作者，不要编。

**Q：kind 的 violation / candidate 有什么区别？**
A：`violation` 是明确的纪律违规；`candidate` 是防御性候选，可能承担正当的 scope 边界（比如 `we do not claim` 有时是必要的），**不要机械删除**，先判断它在句中有没有实际作用。

**Q：Word 工具报 Python 相关错误？**
A：确认 `python -c "import docx"` 能跑通。`.doc`（旧版）不支持，python-docx 只能读 `.docx`，需先另存。
