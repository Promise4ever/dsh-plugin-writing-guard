# DSH Writing Guard

[![Fork](https://img.shields.io/badge/fork-Promise4ever%2Fdsh--plugin--writing-guard-blue)](https://github.com/Promise4ever/dsh-plugin-writing-guard)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **This is a fork, not upstream.** Upstream: [xmutfyh/dsh-plugin-writing-guard](https://github.com/xmutfyh/dsh-plugin-writing-guard).
> The npm package named `dsh-plugin-writing-guard` is the **upstream** build, not this adapted fork —
> this fork publishes no npm package and has no CI of its own.
>
> This fork adapts upstream 2.0.2 to **DSH 0.2.1-rc.2** (version 2.3.0, tag `v2.3.0`) and has been
> **tested only on DSH 0.2.1-rc.2**; other versions are unverified. Changes vs upstream: host adaptation
> (rc.2 peer ranges, message-source kind, tool-result protocol, Word Python paths), the regression fix for
> control notices being silently dropped on rc.2, runtime skill self-registration (no install-time writes to
> `DSH_HOME`) with the GitHub URL as the primary install route, and corrected docs/install instructions.
> Rules, rule corpus and test suite come from upstream — see [Credits](#credits) and [License](#license).

**Less explanation. More argument. Preserve the science.**

Writing Guard is a research-paper writing guard for DeepSeek Harness:
it guides the host model toward economical, evidence-bound prose and audits mechanical, templated and defensive writing,
protects research facts and scientific commitments during AI-assisted revision,
calibrates a manuscript's writing distributions against representative target-journal papers,
and detects context-to-artifact leakage in final deliverables.

> **Language can change. Evidence cannot. Rejected alternatives should not leak.**

**Prompt-guided writing · Deterministic integrity core**

---

## New in 2.0 — Argument Economy & Control-Plane Separation

Writing Guard 2.0 moves semantic style decisions before generation while keeping deterministic code focused on integrity.

- **Critique is not content:** reviewer comments, user edit instructions and guard findings are control context, not manuscript evidence.
- **Prefer CUT over REWRITE:** delete sentences that only pre-empt criticism, reassure reviewers, advertise importance or restate an obvious implication.
- **Do not close every semantic loop:** stop after evidence plus the necessary interpretation; retain non-obvious statistics, reproducibility detail and genuine epistemic boundaries.
- **Style-only revisions default to the same length or shorter:** no explanatory inflation without new supported content.
- **Auto-audit no longer reinjects snippets or rewrite suggestions:** it returns structured rule/action metadata only.

Example:

```text
Avoid:  To prevent data leakage, normalization was carefully performed using only the training data.
Prefer: Normalization parameters were estimated from the training data.
```

---

## Five guards: STYLE / EVIDENCE / JOURNAL / DELIVERY / DOCUMENT

1. **Less AI / STYLE**
   Detect and reduce mechanical, templated, over-defensive AI writing — revision residue, defensive writing, hollow buzzwords and structural tells. We do not hide AI use; we remove bad AI writing.
   > Stronger AI models increasingly write “correct but unnecessary” sentences.

2. **More Evidence / EVIDENCE**
   Numbers, p-values, citations and DOIs must not silently drift during polishing; null findings must not disappear; correlation must not become causation; scope and evidence status must not be silently changed. Language can change. Evidence cannot.

3. **Better Journal Fit / JOURNAL**
   Distill section-level writing distributions, scientific claim patterns and rhetorical moves from representative target-journal papers. It is not only about wording — it compares what each section typically says and in what order.

4. **Clean Delivery / DELIVERY**
   Detects context-to-artifact leakage: rejected alternatives, revision history, or working-context residue that leaks into final deliverables without support from the authoritative baseline. CAL = Context-to-Artifact Leakage (an engineering term, not academic).
   > Language can change. Evidence cannot. Rejected alternatives should not leak.

5. **Safe Document Editing / DOCUMENT**
   Verify edit scope and preserve Word/OOXML structures, equations, tables and package integrity.

## Quick Start

```sh
# 1) Install straight from the GitHub URL (the primary route in 2.3.0 — no build approval needed)
dsh plugin --profile <profile> add https://github.com/Promise4ever/dsh-plugin-writing-guard

# 2) Restart the host so the patch layer loads
dsh web
```

Offline, or when you need the version pinned, install a directory with `file:` instead — see
[Full install](#full-install) for both directory routes.

This fork is **not published on npm**. `dsh plugin add dsh-plugin-writing-guard` resolves to the
upstream package, which does not contain the rc.2 adaptation. Use the GitHub URL, git tag or release ZIP.

---

## How it works

```text
writing rules → Agent revision → automatic guard → targeted revision
```

Writing Guard is not a one-shot humanizer. It works continuously inside the DSH paper workflow:

- Load `writing_rules` before writing
- Check while writing / editing with `writing_audit`
- Compare before/after revisions to protect Scholarship / Epistemic invariants

## STYLE — argument economy and prose discipline

Detects:

- Revision residue: `revised`, `as requested`, `本轮`, `审稿人要求`
- Defensive writing: concession stacking, limitation pre-emption, generic value claim, unnecessary epistemic retreat
- Mechanical rhetoric: `not X but Y`, `rather than` overuse, rule of three, em-dash / colon abuse
- LLM-associated words: `delve` / `tapestry` / `testament` / `leverage` (density-based, a single use is fine)
- Chinese filler chains, average sentence-length anomalies, etc.

Density thresholds are language-aware: English by word count, Chinese by CJK character count, with a double gate to avoid false positives on domain terms.

## EVIDENCE — Scholarship + Epistemic Lock

Writing Guard compares before/after AI revision and protects:

- Numbers, percentages, p-values, confidence intervals, units
- `\cite` / `\ref`, Figure/Table numbers, DOIs
- Causal and evidential force: `associated with` must not silently become `caused`
- Negation / null findings: `no significant difference` must not disappear or flip
- Scope boundaries and evidence status: “observed / reported” must not become direct claims

Each finding is tagged `INVARIANT / VIOLATION / CANDIDATE / ADVISORY` and an integrity regression report is produced.

## JOURNAL — target-journal calibration

Writing Guard builds a corpus-aware Journal Profile from multiple representative target-journal papers, each parsed independently.

It currently compares five signal groups:

- **Structure**: sentence length, paragraph length
- **Voice**: passive voice, first-person usage
- **Citations**: bibliographic citations, figure/table references
- **Scientific claims**: claim density, causal/evidential strength, hedging, scope, null findings
- **Rhetoric**: rhetorical move coverage, canonical order, section-bound transition fit

Journal Fit is reported per section, together with corpus size and confidence.

> **Scientific Integrity > Journal Fit**

Journal Fit uses grouped weights: Structure 20% / Voice 10% / Citations 15% / Epistemics 35% / Rhetoric 20%.

## Five DSH Tools

| Tool | Purpose |
|---|---|
| `writing_rules` | Returns the writing-discipline cheat sheet before writing |
| `writing_audit` | Main audit entry: checks STYLE issues, compares Scholarship / Epistemic invariants, and can load Style Profile / Journal Profile |
| `writing_style_profile` | Learns an author's style from previous papers and returns JSON for audit |
| `writing_journal_profile` | Distills a Journal Profile from target-journal papers and returns JSON for audit |
| `writing_delivery_audit` | DELIVERY layer: detects rejected alternatives, revision-process residue, and provenance leakage that lack factual support in the authoritative baseline (CAL detection) |

### writing_delivery_audit example

```js
auditDelivery({
  text: 'Remove Toast from the login form',
  surface: 'commit',
  baseline: 'export default function LoginForm() { return <div><Input /></div>; }',
  rejectedTerms: ['Toast'],
})
// → findings: [REJECTED_ALTERNATIVE_LEAKAGE, UNJUSTIFIED_NEGATIVE_REFERENCE]
// Toast was rejected and is absent from baseline → both fire
```

## Document-aware auditing

The same sentence can mean different things in different document types:

| profile | meaning | e.g. `as requested by the reviewer` |
|---|---|---|
| `manuscript` | paper body | 🔴 revision residue, flagged |
| `rebuttal` | point-by-point response | ✅ normal, not flagged |
| `cover_letter` | submission letter | 🔴 residue, flagged |
| `review` / `notes` / `unknown` | other | conservative handling |

`writing_audit` accepts a `profile` argument, or auto-detects it from the file path.

## Automatic / incremental audit

The plugin listens to `tools/post-execute`: when the agent writes/edits paper files (`.md` / `.markdown` / `.tex` / `.txt` / `.docx`), it automatically audits and injects results into the next model request.

- Audit state is persisted per file; only **incremental** changes are injected (new / resolved / still present)
- No repeated injection when nothing changed
- Before/after text is captured automatically, so Scholarship Lock + Epistemic Lock run without manually passing `original`
- The notice is attached through `decision.additionalContexts`. When the host blocks the call the plugin attaches no notice — and a block does **not** undo anything: the file was already written to disk
- `.docx` targets are read through the Python bridge, so they need `python-docx` exactly like the Word tools
- The auto-audit is context injection, not a sandbox — see [Security & Privacy](#security--privacy)

## Full install

**The primary route in 2.3.0 is the GitHub repository URL.** 2.3.0 removed `postinstall` and registers the
skill at runtime instead, so installing writes nothing into `DSH_HOME` and needs no `pnpm-workspace.yaml`
edit and no `allowBuilds` approval.

A directory install (`file:<absolute directory>`) remains the offline / pinned-version alternative.

See **[INSTALL.md](INSTALL.md)** for the full install / upgrade / uninstall / verification checklist.

### Route 1 (recommended) — GitHub repository URL

In the DSH plugin page: **Add plugin** → install source:

```text
https://github.com/Promise4ever/dsh-plugin-writing-guard
```

or from the CLI:

```sh
dsh plugin --profile <profile> add https://github.com/Promise4ever/dsh-plugin-writing-guard
dsh web   # restart the host so the patch layer loads
```

`lib/` (including `lib/word_guard/*.py`) is committed build output, so a git install needs no build step.
The URL tracks the repository's default branch; use a directory route when you need a pinned version.

### Route 2 — release ZIP unpacked to a permanent directory (offline)

Download the v2.3.0 ZIP from
[Releases](https://github.com/Promise4ever/dsh-plugin-writing-guard/releases/tag/v2.3.0), unpack it to a
stable directory (e.g. `D:/plugins/dsh-plugin-writing-guard`), then install that directory:

```sh
dsh plugin --profile <profile> add "file:D:/plugins/dsh-plugin-writing-guard"
dsh web
```

### Route 3 — git clone + checkout the tag

```sh
git clone https://github.com/Promise4ever/dsh-plugin-writing-guard.git
cd dsh-plugin-writing-guard
git checkout v2.3.0

dsh plugin --profile <profile> add "file:D:/path/to/dsh-plugin-writing-guard"
dsh web
```

The cloned / unpacked folder *is* the plugin directory (it contains `package.json`). For routes 2 and 3,
**do not move or delete it afterwards** — the `file:` dependency points at it.

### Upgrading from 2.2.0 — delete the old skill copy first

2.2.0's `postinstall` copied the skill to `$DSH_HOME/skills/writing-guard/` (default
`~/.dsh/skills/writing-guard`). 2.3.0 no longer writes there, but the leftover copy stays: it comes from the
filesystem provider (rank 400) and outranks the plugin's self-registered bundled skill (rank 600), so you keep
seeing the old skill body. The plugin warns about the leftover but **will not delete it for you**:

```bat
:: Windows (cmd)
rmdir /s /q "%USERPROFILE%\.dsh\skills\writing-guard"
```

```sh
# Git Bash / macOS / Linux
rm -rf ~/.dsh/skills/writing-guard
```

Then reinstall/update the plugin and restart the host. With a custom `DSH_HOME`, use
`$DSH_HOME/skills/writing-guard`.

### If you hit `ERR_PNPM_IGNORED_BUILDS`

**2.3.0 removed `postinstall`, so a normal install never hits this and needs no build approval.**
You only see it when installing 2.2.0 or earlier, or when using a non-recommended form such as a local `.tgz`.

In that case copy **the exact key pnpm printed** into the profile's `pnpm-workspace.yaml`:

```yaml
allowBuilds:
  dsh-plugin-writing-guard: true
```

Then re-run the same `dsh plugin ... add` command. Do not invent the key name — for git dependencies the key
is the codeload tarball URL, which changes with every commit; that is exactly why 2.3.0 dropped `postinstall`.

### ⚠️ Do not install a local `.tgz`

`dsh plugin add <some-path>.tgz` installs fine, but on **DSH Desktop builds that run the orphan-plugin
cleanup at startup**, a `file:`/`link:` dependency whose target is not a directory is treated as dangling
and silently uninstalled (the test is `is_dir()`; a tarball is a file, so it always fails). Symptom:
it works after install and is gone from the plugin list after a restart.

- Scope: **local `file:*.tgz` installs on those Desktop builds**.
- Directory installs (`file:<directory>`) are not affected, and neither is the GitHub URL install.
- Registry installs, HTTPS-tarball installs and plain CLI profiles are **not proven** to be broken by this;
  do not generalise the warning.

### Prerequisites

- **DSH 0.2.1-rc.2** (peers: `@deepseek-ai/dsh-tools` / `@deepseek-ai/dsh-llm` `^0.2.1-rc.2`,
  `@deepseek-ai/cordis` `^4.0.1`). This fork is verified **only** on 0.2.1-rc.2.
- Node.js ≥ 22.19.0 (DSH 0.2.1 runtime requirement).
- Python 3.10+ with `python-docx` (`pip install python-docx`) for **every DOCX operation** — the eight
  `writing_word_*` tools *and* `writing_audit` called on a `.docx`. The plugin **does not install it**;
  2.3.0 has no `postinstall`, so there is not even an install-time probe — the tools fail with a hint when the
  dependency is missing. `.md` / `.tex` / `.txt` audits need no Python.

Repository: https://github.com/Promise4ever/dsh-plugin-writing-guard

## Why not Humanizer / AI Detector?

| | Writing Guard | Humanizer | AI Detector |
|---|---|---|---|
| Rules before writing | ✅ | ❌ | ❌ |
| Checks while writing | ✅ | usually ❌ | ❌ |
| Auto-audits paper edits | ✅ | ❌ | ❌ |
| Full-text rewrite | ❌ | ✅ | ❌ |
| Explainable issue location | ✅ | partial | partial |
| Deterministic integrity checks | ✅ | usually no | varies |

> A humanizer fixes the text after it is written; Writing Guard guards it as you write.

## Security & Privacy

- Deterministic integrity checks run locally; semantic writing decisions are handled by the host model under the Writing Guard policy.
- **Data flow, accurately:** the automatic audit reads the paper file you just wrote/edited plus the
  **first `*.bib`** in the same directory (for local citation integrity), and may read other local files
  that were explicitly requested. Its incremental state lives at
  `$DSH_HOME/plugins/dsh-plugin-writing-guard/state.json` and — besides fingerprints — stores
  **plaintext baselines of the paper text** for cross-run comparison. Manual tools read the files or
  directories you name in their arguments (`writing_audit` / `writing_style_profile` /
  `writing_journal_profile` take an **absolute path**). Word tools write the requested `.docx`.
- Auto-audit is **context injection, not a sandbox**. The write-boundary check in `src/host-adapter.ts` is a
  compatibility heuristic over the host sandbox policy (lexical path boundary only, no symlink/junction
  resolution; a missing policy or unknown mode passes through). It is **not** a security fence.
- The plugin itself does not collect or upload paper content.
- See [SECURITY.md](SECURITY.md)

## Tests

```sh
npm test
```

459 deterministic TP / TN / boundary / regression tests (27 of them are the v2.3.0 skill self-registration regressions) covering:

- STYLE, Scholarship Lock, Epistemic Lock
- Claim alignment, local citation integrity
- Journal Profile, Journal Fit
- Rhetorical semantics (Chinese / medoid / transition)
- **DELIVERY (CAL detection)**: rejected alternative / process residue / baseline reality / provenance / defensive hedge / counterfactual pair / NFKC / stopwords / scientific TN / safety TN / real-migration TN

This fork has **no CI configured**; the badge row above carries repo and license badges only. Run the suite locally (`pnpm install --ignore-scripts && pnpm build && pnpm test`).

> Deterministic rules (regex + normalization) cannot cover every semantic paraphrase. DELIVERY-layer detection is limited to leakage patterns expressible via regular expressions; manual review remains necessary.

## FAQ

### Is this a DSH “remove AI flavor” plugin?

You can think of it that way, but Writing Guard is not a traditional humanizer. It detects common AI writing patterns during paper writing and revision instead of rewriting the whole text with another model.

### Does it support Chinese papers?

Yes. Rules cover both Chinese and English academic writing patterns, with language-aware density thresholds (CJK characters vs. English words).

### Does it support SCI / English academic writing?

Yes. `writing_audit` checks English manuscripts for revision residue, defensive writing, LLM-overused expressions, and common AI-style sentence patterns.

### What is the difference from academic-humanizer?

academic-humanizer focuses on rewriting existing text into a more natural style; Writing Guard focuses on continuous checking and prevention inside the DSH paper workflow. They can be used together.

## CHANGELOG

Full changelog and implementation details are in [CHANGELOG.md](CHANGELOG.md).

## Credits

This repository is a fork of [xmutfyh/dsh-plugin-writing-guard](https://github.com/xmutfyh/dsh-plugin-writing-guard).
The rule corpus, tool design and test suite come from upstream; this fork only adapts them to DSH 0.2.1-rc.2,
fixes one control-notice regression, and corrects the docs/install instructions.
Upstream bugs belong upstream; fork-specific issues go to
[this repository's issues](https://github.com/Promise4ever/dsh-plugin-writing-guard/issues).

## License

MIT (same as upstream, see [LICENSE](LICENSE))
