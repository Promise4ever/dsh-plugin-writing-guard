/**
 * DSH 宿主边界适配层（目标宿主 0.2.1-rc.2）。
 *
 * 这里只放"与宿主契约耦合"的纯函数，便于单元测试：
 * - 文本写工具的目标识别（含官方 write/edit 与 dsh-ops 的 ops_* 工具）
 * - 相对路径按会话工作目录解析
 * - 执行结果分层（applied / dry-run / failed / unknown），避免把 dryRun、
 *   rejected、error、部分失败当成"写成功"去审计
 * - 执行键（exec.token 是 branded symbol，不能 String() 化——所有 token 的
 *   String 结果相同，必须用 WeakMap 分配稳定 id）
 * - 沙箱政策软取与写入边界判断（read-only / workspace-write / danger-full-access）
 */
import path from 'node:path';
/** 本插件注入通知时使用的消息来源（含 form:'notice' 摘要，UI 可折叠显示） */
export const NOTICE_SOURCE = {
    kind: 'writing-guard',
    form: 'notice',
    summary: 'writing guard control metadata',
};
/**
 * 需要自动审计的文本写工具。官方 write/edit 用 file_path；
 * dsh-ops 的 ops_write_file / ops_edit_file / ops_replace 用 path（同时兼容 file_path 别名）。
 */
export const TEXT_WRITE_TOOLS = [
    { name: 'write', argKeys: ['file_path', 'filePath', 'path'] },
    { name: 'edit', argKeys: ['file_path', 'filePath', 'path'] },
    { name: 'ops_write_file', argKeys: ['path', 'file_path', 'filePath'] },
    { name: 'ops_edit_file', argKeys: ['path', 'file_path', 'filePath'] },
    { name: 'ops_replace', argKeys: ['path', 'file_path', 'filePath'] },
];
/** 是否为受管的文本写工具 */
export function isTextWriteTool(toolName) {
    if (!toolName)
        return false;
    return TEXT_WRITE_TOOLS.some((t) => t.name === toolName);
}
/** 从工具调用里取出目标文件路径（相对路径原样返回，交给 resolveTarget 解析） */
export function targetPathOf(exec) {
    if (!exec)
        return null;
    const spec = TEXT_WRITE_TOOLS.find((t) => t.name === exec.name);
    if (!spec)
        return null;
    const args = exec.arguments;
    if (!args || typeof args !== 'object')
        return null;
    for (const key of spec.argKeys) {
        const value = args[key];
        if (typeof value === 'string' && value.trim())
            return value;
    }
    return null;
}
/**
 * 把工具参数里的目标路径解析成绝对规范路径。
 * 宿主工具接受相对路径（相对会话工作目录），旧实现直接 fs.readFile 会相对
 * 宿主进程 cwd，是错的。
 */
export function resolveTarget(target, cwd) {
    if (path.isAbsolute(target))
        return path.normalize(target);
    return path.resolve(cwd ?? process.cwd(), target);
}
/** 会话工作目录：优先 workingDirectory 服务（反映 /cd），回退 header.cwd，再回退进程 cwd */
export function getSessionCwd(ctx, session) {
    const headerCwd = session?.header?.cwd;
    try {
        const wd = ctx?.get?.('workingDirectory');
        const resolved = wd?.get?.(session);
        if (typeof resolved === 'string' && resolved)
            return resolved;
    }
    catch {
        // 服务未挂载或未激活：回退
    }
    return typeof headerCwd === 'string' && headerCwd ? headerCwd : undefined;
}
export function getSandboxPolicy(ctx, session) {
    try {
        const service = ctx?.get?.('sandboxPolicy');
        if (!service || typeof service.resolve !== 'function')
            return undefined;
        const policy = service.resolve(session ? { session } : undefined);
        if (!policy || typeof policy.mode !== 'string')
            return undefined;
        return {
            mode: policy.mode,
            workspaceRoot: typeof policy.workspaceRoot === 'string' ? policy.workspaceRoot : undefined,
        };
    }
    catch {
        return undefined;
    }
}
function isInside(root, target) {
    const rel = path.relative(path.resolve(root), path.resolve(target));
    if (!rel)
        return true;
    if (path.isAbsolute(rel))
        return false;
    const norm = rel.replace(/\\/g, '/').toLowerCase();
    return norm !== '..' && !norm.startsWith('../');
}
/** 写入边界判断：返回 null 表示允许，否则返回拒绝原因 */
export function checkWriteAllowed(policy, target) {
    if (!policy)
        return null;
    if (policy.mode === 'danger-full-access')
        return null;
    if (policy.mode === 'read-only') {
        return `当前会话是只读沙箱（read-only），拒绝写入 "${target}"`;
    }
    if (policy.mode === 'workspace-write') {
        const root = policy.workspaceRoot;
        if (!root)
            return null;
        if (!isInside(root, target)) {
            return `当前会话是 workspace-write 沙箱，只允许写 "${root}" 内的路径，拒绝写入 "${target}"`;
        }
        return null;
    }
    return null;
}
/**
 * 判定工具执行结果是不是"真的写入了文件"。
 * 宿主结果有两层：外层 ToolExecutionResult.isError，内层 dsh-ops 的
 * value.status（completed / planned / rejected / error / partial / unknown …）。
 */
export function writeOutcome(result) {
    const r = result;
    if (!r)
        return 'unknown';
    if (r.isError === true)
        return 'failed';
    const value = r.value;
    if (!value || typeof value !== 'object')
        return 'applied';
    if (value.error !== undefined && value.error !== null)
        return 'failed';
    if (value.dryRun === true)
        return 'dry-run';
    if (typeof value.status === 'string') {
        if (value.status === 'planned')
            return 'dry-run';
        if (value.status === 'completed')
            return 'applied';
        if (value.status === 'partial')
            return 'applied';
        if (value.status === 'rejected' || value.status === 'error')
            return 'failed';
        return 'unknown';
    }
    // 官方 write/edit：{ path, version, ... }，无 status 字段
    if (typeof value.changed === 'number' && value.changed === 0)
        return 'unknown';
    return 'applied';
}
/**
 * 执行键：exec.token 是 branded symbol，且所有 token 的 String() 都是
 * "Symbol(dsh.tool.execution)"，不能当 key。用 WeakMap 分配递增 id；
 * 非 symbol 时回退 callId，再回退目标路径。
 */
// WeakMap 只接受对象键，symbol 会报 TS2344；这里用 Map（token 生命周期与调用同长，条目有界）
const tokenIds = new Map();
let tokenSeq = 0;
export function executionKey(exec) {
    if (!exec)
        return 'anon';
    const token = exec.token;
    if (typeof token === 'symbol') {
        let id = tokenIds.get(token);
        if (id === undefined) {
            id = ++tokenSeq;
            tokenIds.set(token, id);
        }
        return `token:${id}`;
    }
    if (typeof exec.callId === 'string' && exec.callId)
        return `call:${exec.callId}`;
    const target = targetPathOf(exec);
    if (target)
        return `path:${target}`;
    return `anon:${exec.name ?? 'unknown'}`;
}
/** 供测试使用：清空 token 计数（WeakMap 本身不可清空，仅重置序号） */
export function resetExecutionKeysForTest() {
    tokenSeq = 0;
}
