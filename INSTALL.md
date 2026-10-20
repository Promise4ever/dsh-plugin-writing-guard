# Writing Guard 安装与升级（v2.3.0）

面向 DSH 插件 `dsh-plugin-writing-guard` 的本 fork 版本。仓库：
[xmutfyh 上游](https://github.com/xmutfyh/dsh-plugin-writing-guard) → 本 fork
[Promise4ever/dsh-plugin-writing-guard](https://github.com/Promise4ever/dsh-plugin-writing-guard)。

> **这是 fork，不是上游原版。** 本 fork **不发布 npm 包**；npm 上的 `dsh-plugin-writing-guard` 是上游版本，
> `dsh plugin add dsh-plugin-writing-guard` 装到的也是上游版本（不含 rc.2 适配）。
> 要装这份适配版，只能用本仓库的 GitHub URL、git tag 或 release。

**v2.3.0 的主要安装方式：在 DSH 插件扩展页填入本仓库的 GitHub URL。**
该版本删掉了 `postinstall`，安装过程不再被 pnpm 的构建脚本审批拦住，
不需要手改 `pnpm-workspace.yaml`，也不需要 `allowBuilds`。

---

## 0. 一分钟版

```text
# ① GUI：插件扩展页 → 添加插件 → 安装源填 Git 地址
https://github.com/Promise4ever/dsh-plugin-writing-guard

# 或在 CLI 里
dsh plugin --profile <profile> add https://github.com/Promise4ever/dsh-plugin-writing-guard
```

装完**重启宿主**（DSH Desktop 重启应用；CLI 用 `dsh web` 重新起）。没有 hmr 的宿主会给出 restart-required 提示。

从 2.2.0 升级的**先做第 3 节**：删掉旧的 skill 副本，否则你看到的是 2.2.0 的旧技能正文。

---

## 1. 环境要求

- **DSH 0.2.1-rc.2**。peer 范围：`@deepseek-ai/dsh-tools` / `@deepseek-ai/dsh-llm` `^0.2.1-rc.2`、
  `@deepseek-ai/cordis` `^4.0.1`。本 fork **只在 0.2.1-rc.2 上验证过**，其他 DSH 版本未验证。
- **Node.js ≥ 22.19.0**（DSH 0.2.1 运行时要求）。
- **Python 3.10+ 与 `python-docx`**：只有 Word / DOCX 相关功能需要（`pip install python-docx`）。
  插件**不会替你装**；2.3.0 删掉 `postinstall` 后也没有安装期探测了，缺它时相关工具在调用时报错并提示安装。
  `.md` / `.tex` / `.txt` 的文本审计不需要 Python。

---

## 2. 三种安装方式

### 方式 ①：GitHub 仓库 URL（推荐）

DSH 插件扩展页 → **添加插件** → 安装源填 Git 地址：

```text
https://github.com/Promise4ever/dsh-plugin-writing-guard
```

或命令行：

```sh
dsh plugin --profile <profile> add https://github.com/Promise4ever/dsh-plugin-writing-guard
```

推荐它的原因（v2.3.0 的核心变化）：

- 包内 `lib/`（含 `lib/word_guard/*.py`）是入库的构建产物，git 安装不需要 build；
- `package.json` 里已经没有 `postinstall`，pnpm 11 的 `strict-dep-builds` 没有东西可拦，
  不会出现 `ERR_PNPM_IGNORED_BUILDS`，也就不需要批准构建、不需要改 profile 的 `pnpm-workspace.yaml`；
- skill 由插件在 `apply()` 里通过宿主的 skills 服务**运行时自注册**（正文读包内
  `skills/writing-guard/SKILL.md`），安装期不往 `DSH_HOME` 写任何文件。

> URL 形态装的是仓库默认分支上的代码（v2.3.0 发布后即对应 2.3.0 的提交）。
> 需要把版本钉死时用方式 ② 或 ③。

### 方式 ②：Release ZIP 解压到固定目录（离线）

从 [Releases](https://github.com/Promise4ever/dsh-plugin-writing-guard/releases/tag/v2.3.0)
下载 v2.3.0 的 ZIP，解压到一个**固定的**目录（例如 `D:/plugins/dsh-plugin-writing-guard`），
然后按目录安装：

```sh
dsh plugin --profile <profile> add "file:D:/plugins/dsh-plugin-writing-guard"
dsh web
```

插件扩展页的安装源也接受本地目录的**绝对路径**，效果相同。

### 方式 ③：git clone + file: 目录安装

```sh
git clone https://github.com/Promise4ever/dsh-plugin-writing-guard.git
cd dsh-plugin-writing-guard
git checkout v2.3.0

# 安装（Windows 路径示例）
dsh plugin --profile <profile> add "file:D:/path/to/dsh-plugin-writing-guard"

# 重启宿主
dsh web
```

> 路线 ②③ 装好后**不要移动或删除**那个目录：`file:` 依赖直接指向它，移走了就失效。

---

## 3. 从 2.2.0 升级：必须删掉旧 skill 副本

**为什么必须删。** 2.2.0 的 `postinstall` 会把 `skills/writing-guard` 复制到
`$DSH_HOME/skills/writing-guard/`（默认 `~/.dsh/skills/writing-guard`）。2.3.0 不再往这个位置写文件，
但旧副本还留在原地：它走 filesystem skill provider，rank=400，比插件自注册的 bundled（rank=600）优先；
同一层里同名 skill 时 rank 小的先赢，结果是「skill 还在，但正文是 2.2.0 的旧版」，宿主还会打一条 warn。
插件运行时会检测到这份残留并告警，但**不会替你删**。

删除命令：

Windows（cmd）：

```bat
rmdir /s /q "%USERPROFILE%\.dsh\skills\writing-guard"
```

Git Bash / macOS / Linux：

```sh
rm -rf ~/.dsh/skills/writing-guard
```

如果设过 `DSH_HOME`，把路径对应换成 `$DSH_HOME/skills/writing-guard`。

升级步骤：

1. 先执行上面的删除命令，清掉旧 skill 副本；
2. 更新插件：插件扩展页里把安装源重新指向本仓库 URL；CLI 可先
   `dsh plugin --profile <profile> remove dsh-plugin-writing-guard` 再重新 `add`；
3. 重启宿主。

---

## 4. 装完怎么验证

1. **插件列表**里出现 `dsh-plugin-writing-guard`；
2. **13 个工具**对模型可见：`writing_audit`、`writing_delivery_audit`、`writing_rules`、
   `writing_style_profile`、`writing_journal_profile`，以及 8 个 `writing_word_*`
   （`scan` / `edit` / `audit` / `scope_check` / `format_tables` / `audit_equations` /
   `package_validate` / `fingerprint`）；
3. **skill 可见**：输入框打 `/`，菜单里有 `writing-guard`；或 skill 列表里能查到同名条目；
4. 启动日志里**没有**「检测到旧版安装残留的 skill 副本」这条 warn（有就回第 3 节）；
5. Word 功能自检：`python -c "import docx"` 能跑通。

> 2.3.0 已在 DSH 0.2.1-rc.2 headless 宿主上实测：13 个 `writing_*` 工具全部注册（tools total 38）、
> 控制通知 `<writing_guard_control version="2.3.0">` 已送达 next-step、隔离 `DSH_HOME` 下 skill 自注册
> 正确解析到包内 `skills/writing-guard`。
> Desktop/GUI 里「插件扩展页 → 填 GitHub URL」这一键安装动作本身未单独记录实测结论。

---

## 5. 卸载

```sh
dsh plugin --profile <profile> remove dsh-plugin-writing-guard
```

- **`state.json` 不会随卸载删除**：它在 `$DSH_HOME`（默认 `~/.dsh`）下的
  `plugins/dsh-plugin-writing-guard/state.json`。里面除各文件指纹外，还存**论文正文的明文 baseline**；
  删掉会丢跨轮次比对（Scholarship Lock / Epistemic Lock 的原料），下次写入会重建基线，历史对比无法恢复。
  想保留就留着；想彻底清干净再删文件，而且**先退出宿主**——运行中的宿主可能把自己内存里的状态写回来。
- 该文件是**全局的，不按 profile 隔离**：多个 profile 共用同一份 state。
- 2.3.0 安装期不往 `DSH_HOME` 写文件，所以卸载后 `DSH_HOME/skills` 下不该有插件留下的副本；
  如果你从前面的版本装过，按第 3 节删掉 `skills/writing-guard`。

---

## 6. 限制与已知问题

- **本地 `.tgz` 不要用**：`dsh plugin add <某个路径>.tgz` 能装成功，但在**带孤儿插件清理行为的
  DSH Desktop 构建**上，桌面壳启动时会把 `file:` / `link:` 依赖里目标不是目录的当成悬挂依赖静默卸载
  （判据是 `is_dir()`，tgz 是文件，恒为 false），表现为「装完能用，重启后插件列表里没了」。
  受影响的只是**本地 `file:*.tgz` 装在这类 Desktop 构建上**；目录形态（`file:<目录>`）不受影响；
  从 registry / HTTPS tarball 安装、纯 CLI profile 的情况**没有被证实**存在这个问题，不要一概而论。
- **只在 DSH 0.2.1-rc.2 上验证过**，peer 范围见第 1 节，其他版本不承诺。
- **不发布 npm 包**：npm 上的同名包是上游原版。
- **`python-docx` 不代装**，也没有安装期探测（2.3.0 删除了 `postinstall`），Word 工具缺依赖时在调用报错。
- **装完必须重启宿主**：没有 hmr 时宿主会给 restart-required 提示。

---

相关文档：[README.md](README.md)（项目介绍与安装总览）、[USAGE.md](USAGE.md)（装好后的用法）、
[SECURITY.md](SECURITY.md)（数据流与隐私）、[CHANGELOG.md](CHANGELOG.md)（版本变化）。
