/**
 * v2.3.0：运行时 skill 自注册（替代 2.2.0 及以前的 postinstall 拷贝）。
 *
 * 为什么改：
 * - pnpm 11 默认 `strict-dep-builds=true`：依赖只要声明了 postinstall，`pnpm add`
 *   就以 ERR_PNPM_IGNORED_BUILDS 中止，必须先批准构建脚本。DSH 插件扩展页的
 *   Git URL 安装因此被"待批准构建"卡住，而 git 依赖的 allowBuilds 键是
 *   codeload tarball URL，每个 commit 都变一次——无法做到零交互安装。
 * - 宿主 skill 服务在 dsh-base 里恒挂载（cordis.patch.yml 的 skill /
 *   skill-filesystem / tool-skill），插件可以在 apply() 里注册 provider，
 *   正文直接读包内 skills/writing-guard/SKILL.md，安装期不需要写 DSH_HOME。
 *
 * 与 filesystem provider 的 rank 关系：bundled=600、user-dsh（DSH_HOME/skills）=400。
 * 同一层（global）内同名时 **rank 小的先赢**，所以旧 postinstall 留在
 * DSH_HOME/skills/writing-guard 的副本会压掉自注册条目——检测到就告警让用户删。
 *
 * 契约来源（宿主 0.2.1-rc.2）：
 * - @deepseek-ai/dsh-skill/lib/index.js registerProvider(create)：同步工厂，返回
 *   { name, list, get }；name 不能是保留名 "runtime"；返回 Cordis effect disposer。
 * - list() 返回 candidate 数组（视为 complete:true）；candidate 必填
 *   name/description/invocation{modelInvocable,userInvocable}/source/rank，
 *   且 provider 必须等于 provider.name。
 * - get() 返回 definition，额外要求 content 是字符串。
 * - 参考实现 @deepseek-ai/dsh-skill-badge/lib/index.js。
 */
import { existsSync } from 'node:fs';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
/** skill 名，必须与 SKILL.md frontmatter 的 name 一致（kebab-case） */
export const SKILL_NAME = 'writing-guard';
/** provider 名：kebab 字符串，不能是保留名 "runtime" */
export const SKILL_PROVIDER_NAME = 'writing-guard';
/** dsh-skill 对 bundled provider 的约定 rank（数值越大优先级越低；user-dsh=400） */
export const BUNDLED_SKILL_RANK = 600;
const SKILL_NAME_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
/**
 * 拆出 YAML frontmatter 的顶层标量。
 *
 * 只实现 dsh-skill-filesystem 实际用到的子集（name / description /
 * when-to-use / disable-model-invocation / user-invocable，都是顶层标量），
 * 不引入 YAML 依赖：插件不需要为四个字段背上解析器。
 */
export function splitFrontmatter(markdown) {
    const normalized = markdown.replace(/^﻿/, '');
    const match = /^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/.exec(normalized);
    if (!match)
        return { values: {}, body: normalized.trim() };
    const values = {};
    for (const line of match[1].split(/\r?\n/)) {
        const kv = /^([A-Za-z0-9_-]+):\s*(.*)$/.exec(line.trim());
        if (!kv)
            continue;
        const key = kv[1].toLowerCase();
        values[key] = unquote(kv[2].trim());
    }
    return { values, body: normalized.slice(match[0].length).trim() };
}
/** 去掉 YAML 标量的引号并还原转义（只处理单行标量，够用且不会误伤正文） */
function unquote(raw) {
    if (raw.length >= 2 && raw.startsWith('"') && raw.endsWith('"')) {
        return raw.slice(1, -1).replace(/\\(["\\])/g, '$1');
    }
    if (raw.length >= 2 && raw.startsWith("'") && raw.endsWith("'")) {
        return raw.slice(1, -1).replace(/''/g, "'");
    }
    return raw;
}
function parseBoolean(raw, fallback) {
    if (raw === undefined)
        return fallback;
    const value = raw.trim().toLowerCase();
    if (['true', 'yes', 'on', '1'].includes(value))
        return true;
    if (['false', 'no', 'off', '0'].includes(value))
        return false;
    return fallback;
}
/**
 * 解析 SKILL.md。返回 null 表示 frontmatter 不合法（缺 name/description）。
 *
 * invocation 语义与 dsh-skill-filesystem 的 parseSkillFile 对齐：
 * disable-model-invocation 缺省 false、user-invocable 缺省 true。
 */
export function parseSkillFrontmatter(markdown) {
    const { values, body } = splitFrontmatter(markdown);
    const name = (values.name ?? '').trim();
    const description = (values.description ?? '').trim();
    if (!name || !description || !SKILL_NAME_PATTERN.test(name))
        return null;
    const whenToUse = (values['when-to-use'] ?? '').trim();
    return {
        frontmatter: {
            name,
            description,
            ...(whenToUse ? { whenToUse } : {}),
            modelInvocable: !parseBoolean(values['disable-model-invocation'], false),
            userInvocable: parseBoolean(values['user-invocable'], true),
        },
        content: body,
    };
}
/** 插件安装目录（lib/）→ 包内 skill 目录（../skills/writing-guard） */
export function resolveSkillSource(pluginDir) {
    const skillDir = path.resolve(path.join(pluginDir, '..', 'skills', SKILL_NAME));
    return { skillDir, skillFile: path.join(skillDir, 'SKILL.md') };
}
/** candidate：rank/locator 只在注册侧使用，宿主 toSummary 不会外泄给模型 */
export function buildSkillCandidate(frontmatter, source) {
    return {
        name: frontmatter.name,
        description: frontmatter.description,
        ...(frontmatter.whenToUse ? { whenToUse: frontmatter.whenToUse } : {}),
        invocation: {
            modelInvocable: frontmatter.modelInvocable,
            userInvocable: frontmatter.userInvocable,
        },
        provider: SKILL_PROVIDER_NAME,
        source: 'bundled',
        resourceBase: { kind: 'directory', path: source.skillDir },
        rank: BUNDLED_SKILL_RANK,
        locator: source.skillFile,
    };
}
/** definition：宿主 validateDefinition 要求 content 是字符串；不要带 rank/locator */
export function buildSkillDefinition(frontmatter, content, source) {
    return {
        name: frontmatter.name,
        description: frontmatter.description,
        ...(frontmatter.whenToUse ? { whenToUse: frontmatter.whenToUse } : {}),
        invocation: {
            modelInvocable: frontmatter.modelInvocable,
            userInvocable: frontmatter.userInvocable,
        },
        provider: SKILL_PROVIDER_NAME,
        source: 'bundled',
        resourceBase: { kind: 'directory', path: source.skillDir },
        content,
    };
}
/**
 * 创建 provider。正文按需读取并缓存一次：技能正文只在真正被加载时才需要，
 * list() 阶段读文件也会拖慢 catalog 发现。
 */
export function createWritingGuardSkillProvider(source, options = {}) {
    const read = options.readFile ?? ((file) => fs.readFile(file, 'utf8'));
    let cached = null;
    async function load() {
        if (cached)
            return cached;
        const parsed = parseSkillFrontmatter(await read(source.skillFile));
        if (!parsed) {
            throw new Error(`skill frontmatter must declare name and description: ${source.skillFile}`);
        }
        cached = parsed;
        return parsed;
    }
    return {
        name: SKILL_PROVIDER_NAME,
        async list() {
            const parsed = await load();
            return [buildSkillCandidate(parsed.frontmatter, source)];
        },
        async get() {
            const parsed = await load();
            return buildSkillDefinition(parsed.frontmatter, parsed.content, source);
        },
    };
}
/** DSH_HOME（与插件状态文件同一套口径） */
export function dshHomeOf(env = process.env) {
    const configured = env.DSH_HOME?.trim();
    if (configured)
        return configured;
    return path.join(os.homedir(), '.dsh');
}
/** 2.2.0 及以前 postinstall 拷贝 skill 的位置 */
export function legacySkillDir(dshHome) {
    return path.join(dshHome, 'skills', SKILL_NAME);
}
/**
 * 检测旧版 postinstall 留下的 skill 副本。
 *
 * 该副本走 filesystem provider（source user-dsh，rank 400），会压掉本插件
 * 自注册的 bundled（rank 600）同名条目并打 warn，表现为"skill 还在但内容
 * 是旧版"。插件不替用户删文件，只告警。
 */
export function detectLegacySkillDir(exists = existsSync, dshHome = dshHomeOf()) {
    const dir = legacySkillDir(dshHome);
    return exists(dir) ? dir : null;
}
/**
 * 注册 writing-guard skill provider。
 *
 * @returns true 表示已注册；false 表示宿主没有 skills 服务或注册失败
 *          （插件其余功能不受影响，所以只 warn 不抛）。
 */
export function registerWritingGuardSkill(ctx, source, options = {}) {
    let registry;
    try {
        registry = ctx.get?.('skills');
    }
    catch {
        // 服务未挂载或未激活（strict get 会抛）：当作没有
        registry = undefined;
    }
    if (!registry || typeof registry.registerProvider !== 'function') {
        ctx.logger?.warn('dsh-plugin-writing-guard: 宿主未提供 skills 服务，skill 自注册已跳过（13 个工具仍可用）');
        return false;
    }
    try {
        registry.registerProvider(() => createWritingGuardSkillProvider(source, options));
        return true;
    }
    catch (error) {
        ctx.logger?.warn(`dsh-plugin-writing-guard: skill 自注册失败：${error instanceof Error ? error.message : String(error)}`);
        return false;
    }
}
