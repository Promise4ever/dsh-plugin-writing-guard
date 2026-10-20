# Writing Guard

[![Fork](https://img.shields.io/badge/fork-Promise4ever%2Fdsh--plugin--writing-guard-blue)](https://github.com/Promise4ever/dsh-plugin-writing-guard)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **这是 fork，不是上游原版。** 上游：[xmutfyh/dsh-plugin-writing-guard](https://github.com/xmutfyh/dsh-plugin-writing-guard)。
> 上游的 CI 徽章、npm 包都属于上游仓库；npm 上的 `dsh-plugin-writing-guard` 是上游版本，**不是**这份适配版，本 fork 没有发布 npm 包。
>
> 本 fork 把上游 2.0.2 适配到 **DSH 0.2.1-rc.2**（版本号 2.3.0，tag `v2.3.0`），**只在 DSH 0.2.1-rc.2 上验证过**，不承诺其他版本。
> 相对上游的改动：宿主适配（rc.2 的 peer 范围、消息来源 kind、工具结果协议、Word Python 路径）、控制通知在 rc.2 上被静默丢弃的回归修复、skill 改为运行时自注册（安装期不再写 DSH_HOME）、文档与安装方式。
> 判定规则、规则库与测试集沿用上游，署名见文末「致谢 / Credits」一节，许可见 [License](#license)。

## Scientific Writing & Document Integrity Guard for AI-assisted research

**Less explanation. More argument. Preserve the science.**

Writing Guard combines prompt-guided scientific prose discipline with deterministic integrity checks for AI-assisted research.
It protects your manuscript across five layers:

| Guard | Protects against | Risk |
|-------|------------------|------|
| **STYLE** | Argument economy | 防御性写作、过度解释、语义重复、模板腔 |
| **EVIDENCE** | Scientific drift | 数值、单位、引用、结论被改 |
| **JOURNAL** | Journal mismatch | scope/style/convention 不匹配 |
| **DELIVERY** | Context leakage | prompt、notes、workflow metadata 泄漏 |
| **DOCUMENT** 🆕 | Document corruption | Word 格式、公式、表格、OOXML 被破坏 |

**Prompt-guided writing · Deterministic integrity core · 459 Tests**

```
dsh plugin --profile <profile> add https://github.com/Promise4ever/dsh-plugin-writing-guard
```

> 本 fork 未发布 npm 包，`npm install dsh-plugin-writing-guard` 装到的是上游原版。
> **GitHub URL 是 2.3.0 的主要安装方式**；离线装目录（`file:<绝对目录>`）的两条备选路线见 [Installation](#installation)。
> 完整安装 / 升级 / 卸载步骤见 [INSTALL.md](INSTALL.md)，装完怎么用看 [USAGE.md](USAGE.md)。

> Writing Guard does not write your paper for you.
> It makes AI-assisted writing safer to ship.

---

## New in 2.0 — Argument Economy & Control-Plane Separation

Writing Guard 2.0 moves semantic style decisions **before generation** and keeps deterministic code focused on integrity.

- **Critique is not content** — reviewer/user/guard wording is control context, not manuscript evidence.
- **Prefer CUT over REWRITE** — if a sentence only prevents criticism, reassures reviewers, advertises importance, or repeats an obvious implication, delete it.
- **Do not close every semantic loop** — stop after evidence + necessary interpretation; keep non-obvious statistical interpretation and reproducibility detail.
- **Style-only revisions default to same length or shorter** — no explanatory inflation without new supported content.
- **Auto-audit no longer reinjects snippets or rewrite suggestions** — only structured rule/action metadata is sent back to the agent.
- New English/Chinese cues for defensive-purpose framing, semantic-closure markers, and content-free evaluation.

Example:

```text
Avoid:  To prevent data leakage, normalization was carefully performed using only the training data.
Prefer: Normalization parameters were estimated from the training data.
```

The second sentence states the method fact without importing the defensive reason for mentioning it.

---

## 🛡️ Word Document Guard (introduced in 1.8)

**Change what was requested. Verify what wasn't.**

AI-assisted document editing introduces a subtle risk: the requested text may improve while unrelated parts of the manuscript silently change.

When you ask an AI agent to "rewrite paragraph 3 only," it may inadvertently modify:

- equation structures
- table borders
- numbering
- styles
- section geometry
- relationships
- embedded media
- OOXML package parts

Writing Guard 1.8 introduces a **document-integrity layer** for Word manuscripts:

| Feature | What it does |
|---------|--------------|
| **Scoped text replacement** | 文本替换只发生在指定范围内；注意 CLI 仍会对**整篇文档**套一遍默认学术格式，范围限制管不到格式，需用 `scope_check` / `fingerprint` 验收 |
| **Package validation** | Verifies DOCX/OOXML package integrity after editing |
| **Structural fingerprinting** | Compares document structure before and after |
| **Equation integrity** | Checks equation structure, numbering continuity, math-font drift |
| **Scholarly table awareness** | Distinguishes data tables from layout/figure containers |
| **Pre/post integrity verification** | Deterministic verification, not "I think it's fine" |

### Before / After

**Without Writing Guard:**
```
"Please improve the wording in paragraph 3."
→ AI agent modifies DOCX.
→ Result: paragraph looks better.
→ Unknown: what else changed?
```

**With Writing Guard:**
```
"Please improve the wording in paragraph 3."
→ Writing Guard:
   ✓ scope validated
   ✓ package valid
   ✓ equations preserved
   ✓ protected structures unchanged
   ✓ document fingerprint checked
→ Result: paragraph changed — and unintended document drift is detected.
```

---

## Quick Start

```sh
# 1) 直接以 GitHub URL 安装（2.3.0 的主要方式，不需要批准构建脚本）
dsh plugin --profile <profile> add https://github.com/Promise4ever/dsh-plugin-writing-guard

# 2) 重启宿主让 patch 层生效
dsh web
```

离线或需要把版本钉死时，才取目录形态用 `file:` 安装（三步见 [Installation](#installation)）：
git clone 后 checkout tag v2.3.0，或下载 release 的 ZIP 解压到固定目录。

### Natural Language Usage

Once installed, you can use natural language:

| Say this | Writing Guard does this |
|----------|------------------------|
| "帮我检查论文写作质量" | `writing_word_audit` |
| "把表格改成三线表" | `writing_word_format_tables` |
| "扫描DOCX结构" | `writing_word_scan` |
| "修改第三章的XXX" | `writing_word_edit` |
| "编辑后验证范围" | `writing_word_scope_check` |
| "检查有没有AI味" | `writing_audit` |

---

## Five Guards — Detailed

### STYLE — Argument Economy & Prose Discipline

Guides the host model before writing, then uses deterministic cues to audit mechanical, defensive, and over-explained prose:

- Revision residue: `revised`, `as requested`, `本轮`, `审稿人要求`
- Defensive writing: concession stacking, limitation pre-emption
- Mechanical rhetoric: `不是X而是Y`, `rather than` abuse, triple parallelism
- LLM high-frequency words: `delve` / `tapestry` / `testament` (density-based)
- Chinese patterns and average sentence length anomalies

### EVIDENCE — Scholarship + Epistemic Lock

Protects scientific facts during AI editing:

- Numbers, percentages, p-values, confidence intervals, units
- Citations, Figure/Table numbers, DOI
- Causal strength: `associated with` cannot become `caused`
- Null findings: `no significant difference` cannot disappear
- Scope boundaries and evidence status

### JOURNAL — Target Journal Fit

Calibrates manuscript against target journal conventions:

- Syntax structure (sentence length, paragraph length)
- Voice and person (passive voice, first-person usage)
- Citations (bibliographic, figure/table references)
- Scientific claims (claim density, causal/evidential strength)
- Rhetorical moves (coverage, canonical order)

### DELIVERY — Context Leakage Detection

Stops workflow context from leaking into final artifacts:

- Rejected alternatives
- Revision process residue
- Provenance leakage
- Defensive hedge leakage

### DOCUMENT — Word Document Integrity 🆕

Safely edit Word manuscripts without breaking structure:

```
writing_word_scan → writing_word_edit → writing_word_scope_check
```

**13 tools** for complete document integrity:

| Tool | Purpose |
|------|---------|
| `writing_word_scan` | Structural scan |
| `writing_word_edit` | Safe scoped editing |
| `writing_word_audit` | Writing audit for .docx |
| `writing_word_scope_check` | Scope integrity verification |
| `writing_word_format_tables` | Three-line table formatting |
| `writing_word_audit_equations` | OMML equation audit |
| `writing_word_package_validate` | OOXML package validation |
| `writing_word_fingerprint` | Baseline formatting fingerprint |
| `writing_audit` | Text writing audit |
| `writing_rules` | Writing guidelines |
| `writing_style_profile` | Author style profile |
| `writing_journal_profile` | Journal profile |
| `writing_delivery_audit` | Delivery integrity audit |

---

## Installation

本 fork **不发布 npm 包**。npm 上的 `dsh-plugin-writing-guard` 是上游原版（不含 rc.2 适配），
`dsh plugin add dsh-plugin-writing-guard` 装到的也是上游原版。要装这份适配版，只能从本仓库的 GitHub URL、git tag 或 release 取。

**v2.3.0 的主要安装方式：把本仓库的 GitHub URL 交给插件扩展页（或 CLI）。**
2.3.0 删掉了 `postinstall`，skill 改为插件运行时自注册，安装期不再往 `DSH_HOME` 写文件，
因此这条路径不需要手改 `pnpm-workspace.yaml`、也不需要 `allowBuilds` 批准。

完整的安装 / 升级 / 卸载 / 验证清单见 **[INSTALL.md](INSTALL.md)**。

### 方式 1（推荐）：GitHub 仓库 URL

DSH 插件扩展页 → **添加插件** → 安装源填：

```text
https://github.com/Promise4ever/dsh-plugin-writing-guard
```

或命令行：

```sh
dsh plugin --profile <profile> add https://github.com/Promise4ever/dsh-plugin-writing-guard
dsh web   # 重启宿主让 patch 层生效
```

包内 `lib/`（含 `lib/word_guard/*.py`）是入库的构建产物，git 安装不需要 build。
URL 形态跟的是仓库默认分支；需要把版本钉死时用下面的目录形态。

### 方式 2：release ZIP 解压到固定目录（离线）

从 [Releases](https://github.com/Promise4ever/dsh-plugin-writing-guard/releases/tag/v2.3.0) 下载 v2.3.0 的 ZIP，
解压到一个**固定的**目录（如 `D:/plugins/dsh-plugin-writing-guard`），然后按目录安装：

```sh
dsh plugin --profile <profile> add "file:D:/plugins/dsh-plugin-writing-guard"
dsh web
```

### 方式 3：git clone + checkout tag

```sh
git clone https://github.com/Promise4ever/dsh-plugin-writing-guard.git
cd dsh-plugin-writing-guard
git checkout v2.3.0

# 安装（Windows 路径示例）
dsh plugin --profile <profile> add "file:D:/path/to/dsh-plugin-writing-guard"

# 重启宿主
dsh web
```

> clone / 解压出来的目录就是插件目录（里面直接有 `package.json`）。方式 2、3 装好后**不要移动或删除它**：
> `file:` 依赖指向这个目录，移走了就失效。

### 从 2.2.0 升级：先删掉旧的 skill 副本

2.2.0 的 `postinstall` 会把 skill 复制到 `$DSH_HOME/skills/writing-guard/`（默认 `~/.dsh/skills/writing-guard`）。
2.3.0 不再写这个位置，但旧副本还在：它走 filesystem provider（rank 400），会比插件自注册的
bundled skill（rank 600）优先，表现为「skill 还在但正文是旧版」。插件运行时会告警，但**不会替你删**：

```bat
:: Windows (cmd)
rmdir /s /q "%USERPROFILE%\.dsh\skills\writing-guard"
```

```sh
# Git Bash / macOS / Linux
rm -rf ~/.dsh/skills/writing-guard
```

删完再重装/更新插件并重启宿主。设过 `DSH_HOME` 的把路径换成 `$DSH_HOME/skills/writing-guard`。

### 如果报 `ERR_PNPM_IGNORED_BUILDS`

**2.3.0 已删除 `postinstall`，正常安装不会遇到这个错误，不需要任何构建批准。**
只有这两种情况才可能见到：装的是 2.2.0 及更早的版本；或者用本地 `.tgz` 等非推荐形态安装。

遇到时按 CLI 打印的提示，把 **pnpm 原样打印的那个键**加到 profile 的 `pnpm-workspace.yaml`：

```yaml
allowBuilds:
  dsh-plugin-writing-guard: true
```

然后重跑那条 `dsh plugin ... add` 命令。不要自己编 `allowBuilds` 的键名，抄 pnpm 打印的那一行
（对 git 依赖来说这个键是 codeload 的 tarball URL，每个 commit 都会变，这也是 2.3.0 干脆删掉 `postinstall` 的原因）。

### ⚠️ 本地 `.tgz` 不要用

`dsh plugin add <某个路径>.tgz` 能装成功，但在**有孤儿插件清理行为的 DSH Desktop 构建**上，
桌面壳启动时会把 `file:`/`link:` 依赖的目标不是目录的一律当成悬挂依赖静默卸载
（判据是 `is_dir()`，tgz 是文件，恒为 false）。表现为「装完能用，重启后插件列表里没了」。

- 受影响的只是：**本地 `file:*.tgz`** 装在**这类 Desktop 构建**上；
- 目录形态（`file:<目录>`）不受影响，GitHub URL 安装也不受影响；
- 从 registry / HTTPS tarball 安装、以及纯 CLI profile 的情况**没有被证实**存在这个问题，不要一概而论。

### Prerequisites

- **DSH 0.2.1-rc.2**（peer: `@deepseek-ai/dsh-tools` / `@deepseek-ai/dsh-llm` `^0.2.1-rc.2`、`@deepseek-ai/cordis` `^4.0.1`）。
  本 fork **只在 0.2.1-rc.2 上验证过**，其他版本未验证。
- Node.js ≥ 22.19.0（DSH 0.2.1 运行时要求）。
- Python 3.10+ 且装了 `python-docx`（`pip install python-docx`）：所有 DOCX 相关操作都需要，
  包括 8 个 `writing_word_*` 工具**以及**对 `.docx` 调用 `writing_audit`。插件**不会**替你安装它；
  2.3.0 没有 `postinstall`，安装期连探测都不做，缺依赖时相关工具在调用时报错提示。
  `.md` / `.tex` / `.txt` 的审计不需要 Python。

---

## Architecture

```
Writing Guard
├── STYLE (writing_audit)
│   ├── Revision residue detection
│   ├── AI style patterns
│   └── Density-based thresholds
├── EVIDENCE (Scholarship/Epistemic Lock)
│   ├── Number/unit preservation
│   ├── Citation integrity
│   └── Claim strength conservation
├── JOURNAL (Journal Profile)
│   ├── Corpus-aware analysis
│   ├── Section-level comparison
│   └── Rhetorical move matching
├── DELIVERY (CAL Detection)
│   ├── Rejected alternative leakage
│   ├── Process residue
│   └── Baseline reality check
└── DOCUMENT (Word Guard) 🆕
    ├── Structural scanning
    ├── Safe editing
    ├── Package validation
    ├── Fingerprinting
    └── Equation audit
```

**Design principle:** Baseline manuscript > journal/template > plugin defaults.

The LLM/agent decides *what* should change. Deterministic Word code decides *how* to make that change without silently altering unrelated formatting.

---

## Tests

```sh
npm test
```

测试集沿用上游并持续扩展，当前 **459 条确定性测试**（其中 27 条是 v2.3.0 新增的 skill 自注册回归）。**本 fork 没有配置 CI**，徽章里也不含 CI/npm 状态徽章；
需要自己在本地跑，构建 + 测试的命令见 [CHANGELOG.md](CHANGELOG.md)。

459 deterministic tests covering:
- STYLE, Scholarship Lock, Epistemic Lock
- Claim alignment, local citation integrity
- Journal Profile, Journal Fit
- DELIVERY (CAL detection)
- **Word Guard** (v1.8.2): OOXML validation, fingerprinting, equation audit
- **Skill self-registration** (v2.3.0, 27 assertions): bundled provider, frontmatter parsing, legacy skill-copy detection

---

## Security & Privacy

- Deterministic integrity checks run locally; semantic writing decisions are handled by the host model under the Writing Guard policy.
- **数据流（准确版）**：
  - 自动审计读取你刚写入的那个论文文件，以及同目录下找到的**第一个 `*.bib`**（用于本地引用完整性检查）；也可能读取其他被明确请求的本地文件。
  - 增量状态写在 `$DSH_HOME/plugins/dsh-plugin-writing-guard/state.json`；其中除指纹外，**还保存论文正文的明文 baseline**，用于跨轮次比对。
  - 手动工具读取你在参数里点名的文件或目录（`writing_audit` / `writing_style_profile` / `writing_journal_profile` 请传**绝对路径**）。
  - Word 工具会写入你指定的 `.docx`。
- 自动审计是**上下文注入**，不是沙箱。`src/host-adapter.ts` 里的写边界检查只是按宿主 sandbox 策略做的兼容性启发式（词法路径判断，不解析 symlink / junction；读不到策略或模式未知时直接放行），**不构成安全隔离**。
- 插件自身不上传、不收集稿件内容。
- See [SECURITY.md](SECURITY.md)

---

## Why Writing Guard?

| | Writing Guard | Humanizer | AI Detector |
|---|---|---|---|
| Pre-writing rules | ✅ | ❌ | ❌ |
| During-writing checks | ✅ | Usually ❌ | ❌ |
| Auto-monitor manuscript | ✅ | ❌ | ❌ |
| Full rewrite | ❌ | ✅ | ❌ |
| Explainable issues | ✅ | Partial | Partial |
| Deterministic integrity checks | ✅ | Usually no | Depends |

> Humanizer rewrites after writing. Writing Guard prevents during writing.

---

## Brand

```
                  WRITING GUARD
                       │
       Scientific Writing & Document Integrity
                       │
 ┌─────────┬──────────┬─────────┬──────────┬──────────┐
 STYLE   EVIDENCE   JOURNAL   DELIVERY   DOCUMENT
                                            │
                               Change what was requested.
                               Verify what wasn't.
```

**Classic slogan:** Less AI. More Evidence. Better Journal Fit. Clean Delivery.

**Document slogan:** Change what was requested. Verify what wasn't.

---

## CHANGELOG

See [CHANGELOG.md](CHANGELOG.md).

## 致谢 / Credits

本仓库是 [xmutfyh/dsh-plugin-writing-guard](https://github.com/xmutfyh/dsh-plugin-writing-guard) 的 fork。
规则库、工具设计与测试集均来自上游；本 fork 只做 DSH 0.2.1-rc.2 适配、一处控制通知回归修复，以及文档/安装方式的修订。
上游问题请反馈给上游仓库；本 fork 引入的问题请提到 [本仓库 Issues](https://github.com/Promise4ever/dsh-plugin-writing-guard/issues)。

## License

MIT（与上游一致，见 [LICENSE](LICENSE)）
