# Security Policy

This repository is a fork of
[xmutfyh/dsh-plugin-writing-guard](https://github.com/xmutfyh/dsh-plugin-writing-guard).
The fork adapts upstream 2.0.2 to **DSH 0.2.1-rc.2**, released here as **2.2.0**; it has been tested
**only** on DSH 0.2.1-rc.2.

## Supported versions

| Version | Supported |
|---|---|
| 2.2.x (this fork) | ✅ — only on DSH 0.2.1-rc.2 |
| 2.0.x (upstream) | upstream only — see the upstream repository |
| 1.9.x (upstream) | upstream only (maintenance) |
| 1.8.x (upstream) | upstream only (maintenance) |
| < 1.8 | ❌ (upgrade to the latest release) |

Fork releases are cut from this repository; upstream releases are supported by upstream.
Do not assume a fix made here is present upstream, or the other way round.

## Reporting a vulnerability

Please **do not** open a public issue for security problems. Report privately via
[GitHub Security Advisories](https://github.com/Promise4ever/dsh-plugin-writing-guard/security/advisories/new)
or open a private issue in this repository.

If the problem also affects upstream 2.0.2 and is not introduced by this fork's DSH adaptation,
please also notify upstream at
[xmutfyh/dsh-plugin-writing-guard](https://github.com/xmutfyh/dsh-plugin-writing-guard) —
they own the rules engine and the DOCX tooling this fork inherits.

Include:

- the plugin version and DSH version you are using
- a minimal reproducer (config + document text)
- the impact you observed

You should receive an acknowledgment within 3 business days; fixes land in a patch release, and
the issue is disclosed after the fix is out.

## Security notes for this plugin

- Deterministic integrity checks run locally. Semantic style decisions are performed by the host model using Writing Guard policy instructions; the plugin does not make a separate model/API call for those decisions.
- **Data flow — what the plugin actually reads and writes:**
  - *Automatic audit* (on `tools/post-execute` after a successful write): reads the paper file the agent
    just wrote/edited, and the **first `*.bib` file** it finds in the same directory (used for local
    citation-integrity checks). It may also read other local files that were explicitly requested in the
    tool call being audited.
  - *Manual tools* (`writing_audit`, `writing_style_profile`, `writing_journal_profile`,
    `writing_delivery_audit`): read only the file or directory you name in the arguments. The first three
    treat `filePath` / `learnDir` as given — pass an **absolute path**; they do not resolve against the
    session working directory.
  - *Word tools* (`writing_word_*`): read the given `.docx` and **write** the `.docx` you requested
    (in place, or to `outputPath`). Only `.docx` is accepted; `.doc` is rejected.
- **Persisted state contains plaintext manuscript text.** The incremental state file lives under
  `$DSH_HOME/plugins/dsh-plugin-writing-guard/state.json` (falling back to
  `~/.dsh/plugins/dsh-plugin-writing-guard/state.json`). Besides per-file fingerprints it stores
  **plaintext baselines of the paper text** so the next write can be compared against the previous version.
  Caps: 20 files, 512 KB per file, 4 MB total, pruned by timestamp. Deleting the file discards those
  baselines and therefore cross-run comparison; a running host may write cached state back, so stop it first.
- **The auto-audit is context injection, not a sandbox.** The write-boundary check in
  `src/host-adapter.ts` is a best-effort compatibility heuristic over the host's sandbox policy: it does a
  lexical path-boundary comparison (`path.resolve` + `path.relative`), does not resolve symlinks or
  junctions, and passes through when the policy is missing or the mode is unknown. It is not and must not be
  treated as a security boundary. The plugin runs with whatever privileges the DSH host grants it.
- Manuscript privacy therefore also depends on the privacy and data-handling settings of the host model/runtime in which Writing Guard is used.
- If you install this plugin from an untrusted source, the DSH host grants it the same privileges
  as any other third-party plugin — review the code, or install only from this repository.
