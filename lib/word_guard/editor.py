# -*- coding: utf-8 -*-
"""
Run-Aware Paragraph Editor.

Safe text replacement in DOCX paragraphs that preserves:
- Run-level formatting (bold, italic, font, size, color)
- Complex objects (fields, equations, hyperlinks, bookmarks)
- Inline images and drawings

Follows the principle: never flatten complex paragraphs.

修复后的核心不变量（P1-1 / P1-5）：
- 绝不删除任何 w:r 元素（淘汰的 run 宁可留空）；
- 绝不修改或删除 w:t / w:tab / w:br / w:cr 之外的任何子节点；
- 匹配跨度内的文本节点可以改文本或删除，跨度外的一切内容原样保留；
- 替换文本写入新的 w:r，格式（rPr）从命中起点所在的 run 深拷贝。
"""

import copy

from lxml import etree
from docx.oxml.ns import qn
from docx.shared import RGBColor

try:  # 包导入（cli.py 以 word_guard.editor 导入）
    from .protected import protected_nodes_between, protected_nodes_in_element
except ImportError:  # 裸模块导入（验证脚本把 src/word_guard 直接加入 sys.path）
    from protected import protected_nodes_between, protected_nodes_in_element


RED = RGBColor(0xFF, 0x00, 0x00)
BLACK = RGBColor(0x00, 0x00, 0x00)

_W_R = qn('w:r')
_W_RPR = qn('w:rPr')
_W_T = qn('w:t')
_W_TAB = qn('w:tab')
_W_PTAB = qn('w:ptab')
_W_BR = qn('w:br')
_W_CR = qn('w:cr')
_W_NO_BREAK_HYPHEN = qn('w:noBreakHyphen')
_W_SOFT_HYPHEN = qn('w:softHyphen')
_W_COLOR = qn('w:color')
_XML_SPACE = qn('xml:space')

# 允许修改 / 删除的文本节点（核心不变量）
_EDITABLE_TEXT_TAGS = frozenset({_W_T, _W_TAB, _W_BR, _W_CR})
# 参与偏移映射、但不可触碰的原子文本节点（契约只允许动上面四个标签）
_ATOMIC_TEXT_TAGS = frozenset({_W_PTAB, _W_NO_BREAK_HYPHEN, _W_SOFT_HYPHEN})
_TEXT_TAGS = _EDITABLE_TEXT_TAGS | _ATOMIC_TEXT_TAGS

# 段落里除直接 w:r 之外还可能承载文本的容器。
# 命中跨度横跨这些容器时无法保证内容顺序，直接拒绝。
_TEXT_CONTAINER_TAGS = frozenset({
    qn('w:hyperlink'), qn('w:fldSimple'), qn('w:ins'), qn('w:del'),
    qn('w:moveFrom'), qn('w:moveTo'), qn('w:sdt'), qn('w:smartTag'),
    qn('w:customXml'), qn('w:dir'), qn('w:bdo'),
})

# replace_entire_paragraph 的拒绝清单：契约要求 + 整体替换会破坏的安全扩展
_ENTIRE_PARAGRAPH_REFUSE_TAGS = {
    'drawing': qn('w:drawing'),
    'pict': qn('w:pict'),
    'object': qn('w:object'),
    'fldChar': qn('w:fldChar'),
    'fldSimple': qn('w:fldSimple'),
    'instrText': qn('w:instrText'),
    'oMath': qn('m:oMath'),
    'oMathPara': qn('m:oMathPara'),
    'footnoteReference': qn('w:footnoteReference'),
    'commentReference': qn('w:commentReference'),
    # 以下为安全扩展：同样携带可视文本 / 结构，整体替换会丢内容
    'hyperlink': qn('w:hyperlink'),
    'endnoteReference': qn('w:endnoteReference'),
    'sdt': qn('w:sdt'),
    'ins': qn('w:ins'),
    'del': qn('w:del'),
    'smartTag': qn('w:smartTag'),
    'customXml': qn('w:customXml'),
    'ptab': qn('w:ptab'),
    'noBreakHyphen': qn('w:noBreakHyphen'),
    'softHyphen': qn('w:softHyphen'),
}
_REFUSE_TAG_NAMES = {tag: name for name, tag in _ENTIRE_PARAGRAPH_REFUSE_TAGS.items()}


class _TextSegment:
    """段落中的一个文本段（w:t / w:tab / w:br / w:cr / ...）及其完整文本偏移。"""

    __slots__ = ('run_index', 'run_element', 'element', 'tag', 'text', 'start', 'end')

    def __init__(self, run_index, run_element, element, tag, text, start, end):
        self.run_index = run_index
        self.run_element = run_element
        self.element = element
        self.tag = tag
        self.text = text
        self.start = start
        self.end = end

    @property
    def editable(self):
        """该文本节点是否允许修改 / 删除。"""
        return self.tag in _EDITABLE_TEXT_TAGS


def _edit_result(success, method=None, warnings=None, preserved_nodes=None,
                 refused_reason=None, error=None):
    """
    构造编辑结果 dict（跨文件契约，cli.py 按此消费）。

    Args:
        success: 是否成功
        method: 'text_node_split' | 'multi_node_merge' | None
        warnings: 警告列表
        preserved_nodes: 段落里仍然存在的受保护节点标签名
        refused_reason: 'protected_node_in_span' | 'protected_node_paragraph' |
            'not_found' | None
        error: 硬失败说明（异常场景），None 表示无
    """
    return {
        'success': bool(success),
        'method': method,
        'warnings': list(warnings or []),
        'preserved_nodes': list(preserved_nodes or []),
        'refused_reason': refused_reason,
        'error': error,
    }


def _get_para_element(para):
    """兼容 python-docx Paragraph 对象与裸 lxml 元素。"""
    return para._element if hasattr(para, '_element') else para


def _paragraph_text(para):
    """读取 python-docx 段落文本；裸元素没有该属性时返回 None。"""
    try:
        return para.text
    except Exception:
        return None


def _local_names(elements):
    """按出现顺序返回元素标签本地名（去重）。"""
    names = []
    for element in elements:
        name = etree.QName(element).localname
        if name not in names:
            names.append(name)
    return names


def _set_text_value(element, value):
    """写入 w:t 文本；空串或首尾有空白时设置 xml:space=preserve。"""
    element.text = value
    if value == '' or value != value.strip():
        element.set(_XML_SPACE, 'preserve')


def _make_text_element(value):
    """新建带文本的 w:t 元素（尚未挂到文档树上）。"""
    t_elem = etree.Element(_W_T)
    _set_text_value(t_elem, value)
    return t_elem


def _remove_node(element):
    """从父节点摘除元素（只用于文本节点或本次新建的 run）。"""
    parent = element.getparent()
    if parent is not None:
        parent.remove(element)


def _children_after(parent, element):
    """返回 parent 中位于 element 之后的同级子元素列表。"""
    children = list(parent)
    try:
        position = children.index(element)
    except ValueError:
        return []
    return children[position + 1:]


def _clone_run_format(source_elem):
    """Clone run properties from a source w:r element."""
    rPr = source_elem.find(_W_RPR)
    if rPr is not None:
        return copy.deepcopy(rPr)
    return None


def _set_run_color(run_elem, color):
    """设置 run 颜色；rPr 必须位于 run 的第一个子节点位置。"""
    rPr = run_elem.find(_W_RPR)
    if rPr is None:
        rPr = etree.Element(_W_RPR)
        run_elem.insert(0, rPr)
    color_elem = rPr.find(_W_COLOR)
    if color_elem is None:
        color_elem = etree.SubElement(rPr, _W_COLOR)
    color_elem.set(qn('w:val'), str(color))


def _new_text_run(para_elem, text, rPr=None, red=False):
    """
    新建 run（插入位置由调用方决定；绝不删除任何原有 run）。

    Args:
        para_elem: 段落元素（新 run 先挂在末尾，随后由调用方移动）
        text: 文本内容；空串时不写 w:t（用于只承载被移动子节点的 run）
        rPr: 可选，克隆自源 run 的 w:rPr
        red: 是否标红

    Returns:
        new w:r element
    """
    new_r = etree.SubElement(para_elem, _W_R)
    if rPr is not None:
        new_r.append(copy.deepcopy(rPr))
    if red:
        _set_run_color(new_r, RED)
    if text:
        t_elem = etree.SubElement(new_r, _W_T)
        _set_text_value(t_elem, text)
    return new_r


def _get_run_text_elements(run_elem):
    """Get all w:t elements in a run."""
    return run_elem.findall(qn('w:t'))


def _create_run_with_format(para, text, rPr=None, color=None):
    """
    Create a new run element with given text and formatting.

    Args:
        para: paragraph element
        text: text content
        rPr: optional run properties element to clone
        color: optional RGBColor for text color

    Returns:
        new w:r element
    """
    new_r = _new_text_run(para, text, rPr, red=False)
    if color is not None:
        _set_run_color(new_r, color)
    return new_r


def _segment_text(tag, element):
    """
    返回文本段对外的文本值。

    映射与 python-docx 1.2.0 的 Run.text 保持一致，避免偏移错位：
    w:t → 文本；w:tab / w:ptab → '\\t'；w:br（仅换行符）→ '\\n'；
    w:cr → '\\n'；w:noBreakHyphen → '-'；w:softHyphen → 软连字符。
    """
    if tag == _W_T:
        return element.text or ''
    if tag in (_W_TAB, _W_PTAB):
        return '\t'
    if tag == _W_BR:
        # python-docx：仅 textWrapping（默认值）换行映射为 '\n'，分页/分栏符为空串
        br_type = element.get(qn('w:type'))
        return '\n' if br_type in (None, 'textWrapping') else ''
    if tag == _W_CR:
        return '\n'
    if tag == _W_NO_BREAK_HYPHEN:
        # python-docx 1.2.0 的 CT_NoBreakHyphen.__str__ 返回 '-'
        return '-'
    if tag == _W_SOFT_HYPHEN:
        # python-docx 忽略 softHyphen，这里映射为软连字符以保持偏移稳定
        return '\u00ad'
    return ''


def _collect_text_segments(para_elem):
    """
    收集段落直接子 run 中的文本段，给出 runs、偏移映射与完整文本。

    只遍历 w:p 的直接 w:r 子节点（与 Paragraph.runs 一致，不含 w:hyperlink 内的 run）。

    Returns:
        (runs, segments, concat)
    """
    runs = [child for child in para_elem if child.tag == _W_R]
    segments = []
    parts = []
    offset = 0
    for run_index, run_elem in enumerate(runs):
        for child in run_elem:
            if child.tag not in _TEXT_TAGS:
                continue
            text = _segment_text(child.tag, child)
            if not text:
                continue
            segments.append(_TextSegment(
                run_index=run_index,
                run_element=run_elem,
                element=child,
                tag=child.tag,
                text=text,
                start=offset,
                end=offset + len(text),
            ))
            parts.append(text)
            offset += len(text)
    return runs, segments, ''.join(parts)


def _text_containers_between(para_elem, first_run, last_run):
    """返回首末 run 之间可能承载文本的容器标签本地名。"""
    if first_run is last_run:
        return []
    children = list(para_elem)
    try:
        first_pos = children.index(first_run)
        last_pos = children.index(last_run)
    except ValueError:
        return []
    containers = [child for child in children[first_pos + 1:last_pos]
                  if child.tag in _TEXT_CONTAINER_TAGS]
    return _local_names(containers)


def _refused_node_names(para_elem):
    """返回段落子树里触发整体替换拒绝的节点名（文档顺序、去重）。"""
    names = []
    for element in para_elem.iter():
        name = _REFUSE_TAG_NAMES.get(element.tag)
        if name is not None and name not in names:
            names.append(name)
    return names


def _restore_children(para_elem, backup):
    """异常回滚：用编辑前的深拷贝恢复段落全部子节点。"""
    for child in list(para_elem):
        para_elem.remove(child)
    for child in list(backup):
        para_elem.append(copy.deepcopy(child))


def _apply_single_segment(para_elem, run, seg, left_remainder, right_remainder,
                          right_context, new_text, red, rPr):
    """单个文本段内命中：原地拆分文本节点。"""
    if left_remainder:
        _set_text_value(seg.element, left_remainder)

    if new_text:
        # 替换 run 必须排在末段右侧内容之前：右侧剩余与右侧上下文搬进新 run
        if not left_remainder:
            _remove_node(seg.element)
        if right_remainder or right_context:
            tail_run = _new_text_run(para_elem, right_remainder,
                                     _clone_run_format(run))
            run.addnext(tail_run)
            for child in right_context:
                tail_run.append(child)
        new_run = _new_text_run(para_elem, new_text, rPr, red=red)
        run.addnext(new_run)
        return

    # 纯删除：原地拆分，不新建 run
    if right_remainder:
        if left_remainder:
            seg.element.addnext(_make_text_element(right_remainder))
        else:
            seg.element.addprevious(_make_text_element(right_remainder))
            _remove_node(seg.element)
    elif not left_remainder:
        _remove_node(seg.element)


def _apply_single_run(para_elem, run, covered, left_remainder, right_remainder,
                      right_context, new_text, red, first_rPr, last_rPr):
    """同一 run 内跨多个文本段命中：节点级拆分 + 中间节点删除。"""
    first_seg, last_seg = covered[0], covered[-1]

    if left_remainder:
        _set_text_value(first_seg.element, left_remainder)
    else:
        _remove_node(first_seg.element)
    for seg in covered[1:-1]:
        _remove_node(seg.element)

    if new_text:
        # 替换 run 必须排在末段右侧内容之前：右侧剩余与右侧上下文搬进新 run
        if right_remainder or right_context:
            tail_run = _new_text_run(para_elem, right_remainder, last_rPr)
            run.addnext(tail_run)
            for child in right_context:
                tail_run.append(child)
        _remove_node(last_seg.element)
        new_run = _new_text_run(para_elem, new_text, first_rPr, red=red)
        run.addnext(new_run)
        return

    # 纯删除：右侧剩余留在末段节点里
    if right_remainder:
        _set_text_value(last_seg.element, right_remainder)
    else:
        _remove_node(last_seg.element)


def _apply_across_runs(para_elem, covered, left_remainder, right_remainder,
                       new_text, red, first_run, first_rPr):
    """跨多个 run 命中：首 run 留左段、末 run 留右段，中间文本节点删除。"""
    first_seg, last_seg = covered[0], covered[-1]

    if left_remainder:
        _set_text_value(first_seg.element, left_remainder)
    else:
        _remove_node(first_seg.element)
    for seg in covered[1:-1]:
        _remove_node(seg.element)
    if right_remainder:
        _set_text_value(last_seg.element, right_remainder)
    else:
        _remove_node(last_seg.element)

    if new_text:
        new_run = _new_text_run(para_elem, new_text, first_rPr, red=red)
        first_run.addnext(new_run)


def _apply_replacement(para_elem, covered, start, end, new_text, red):
    """
    在内存中执行替换（调用方已完成全部拒绝判断）。

    绝不删除 w:r，也绝不动 w:t/w:tab/w:br/w:cr 之外的子节点。
    """
    first_seg, last_seg = covered[0], covered[-1]
    first_run, last_run = first_seg.run_element, last_seg.run_element
    left_remainder = (first_seg.text[:start - first_seg.start]
                      if start > first_seg.start else '')
    right_remainder = (last_seg.text[end - last_seg.start:]
                       if end < last_seg.end else '')
    first_rPr = _clone_run_format(first_run)
    last_rPr = _clone_run_format(last_run)

    if first_run is not last_run:
        _apply_across_runs(para_elem, covered, left_remainder, right_remainder,
                           new_text, red, first_run, first_rPr)
        return

    run = first_run
    right_context = _children_after(run, last_seg.element)
    if first_seg is last_seg:
        _apply_single_segment(para_elem, run, first_seg, left_remainder,
                              right_remainder, right_context, new_text, red,
                              first_rPr)
    else:
        _apply_single_run(para_elem, run, covered, left_remainder,
                          right_remainder, right_context, new_text, red,
                          first_rPr, last_rPr)


def replace_text_in_paragraph(para, old_text, new_text, red=True):
    """
    替换段落中的文本，保留未被替换的 run 格式与全部受保护节点。

    只替换第一次出现（保持原实现语义）。命中跨度覆盖受保护节点时拒绝并返回
    refused_reason='protected_node_in_span'，不修改文档。

    Args:
        para: python-docx Paragraph 对象
        old_text: 待替换文本
        new_text: 替换后的文本（空串表示纯删除）
        red: 是否标红

    Returns:
        dict：success/method/warnings/preserved_nodes/refused_reason/error
    """
    para_elem = _get_para_element(para)
    if para_elem is None:
        return _edit_result(False, warnings=["Invalid paragraph element"],
                            refused_reason='not_found', preserved_nodes=[])

    preserved = protected_nodes_in_element(para_elem)
    if not old_text:
        return _edit_result(False, warnings=["Empty search text"],
                            refused_reason='not_found',
                            preserved_nodes=preserved)

    try:
        runs, segments, concat = _collect_text_segments(para_elem)
    except Exception as exc:
        return _edit_result(False, warnings=[f"Failed to read paragraph: {exc}"],
                            preserved_nodes=preserved, error=str(exc))

    start = concat.find(old_text)
    if start < 0:
        warnings = [f"Text not found: '{old_text[:50]}'"]
        para_text = _paragraph_text(para)
        if para_text is not None and old_text in para_text:
            warnings.append(
                "Text only appears inside hyperlink/container content; "
                "nothing was modified"
            )
        return _edit_result(False, warnings=warnings,
                            refused_reason='not_found',
                            preserved_nodes=preserved)

    end = start + len(old_text)
    covered = [seg for seg in segments if seg.end > start and seg.start < end]
    if not covered:
        return _edit_result(False, warnings=["Text not found in editable runs"],
                            refused_reason='not_found',
                            preserved_nodes=preserved)

    method = 'text_node_split' if len(covered) == 1 else 'multi_node_merge'
    first_seg, last_seg = covered[0], covered[-1]

    # 拒绝 1：命中跨度覆盖原子文本节点（ptab / noBreakHyphen / softHyphen 不可改动）
    atomic = [seg.element for seg in covered if not seg.editable]
    if atomic:
        return _edit_result(
            False, method=method,
            warnings=[f"Refused: replacement span covers non-editable text nodes: "
                      f"{', '.join(_local_names(atomic))}"],
            preserved_nodes=preserved, refused_reason='protected_node_in_span')

    # 拒绝 2：跨度内的 run 含受保护非文本节点（drawing / field / bookmark ...）
    in_span = protected_nodes_between(para_elem, first_seg.run_index,
                                      last_seg.run_index)
    if in_span:
        return _edit_result(
            False, method=method,
            warnings=[f"Refused: replacement span contains protected nodes: "
                      f"{', '.join(in_span)}"],
            preserved_nodes=preserved, refused_reason='protected_node_in_span')

    # 拒绝 3：跨度横跨段落级文本容器（hyperlink 等），无法保证内容顺序
    crossing = _text_containers_between(para_elem, runs[first_seg.run_index],
                                        runs[last_seg.run_index])
    if crossing:
        return _edit_result(
            False, method=method,
            warnings=[f"Refused: replacement span crosses text containers: "
                      f"{', '.join(crossing)}"],
            preserved_nodes=preserved, refused_reason='protected_node_in_span')

    backup = copy.deepcopy(para_elem)
    try:
        _apply_replacement(para_elem, covered, start, end, new_text, red)
    except Exception as exc:  # 回滚，保证文档不会被改坏
        _restore_children(para_elem, backup)
        return _edit_result(
            False, method=method,
            warnings=[f"Replacement failed and paragraph was restored: {exc}"],
            preserved_nodes=protected_nodes_in_element(para_elem),
            error=str(exc))

    return _edit_result(True, method=method,
                        preserved_nodes=protected_nodes_in_element(para_elem))


def replace_entire_paragraph(para, new_text, red=True):
    """
    整体替换段落文本，保留首个 run 的格式。

    段落含 drawing/pict/object/字段/公式/脚注/批注等受保护节点时直接拒绝
    （refused_reason='protected_node_paragraph'），不做任何修改。

    Args:
        para: python-docx Paragraph object
        new_text: new text content
        red: whether to highlight in red

    Returns:
        dict：success/method/warnings/preserved_nodes/refused_reason/error
    """
    para_elem = _get_para_element(para)
    if para_elem is None:
        return _edit_result(False, warnings=["Invalid paragraph element"],
                            refused_reason='not_found', preserved_nodes=[])

    preserved = protected_nodes_in_element(para_elem)
    runs = [child for child in para_elem if child.tag == _W_R]
    if not runs:
        return _edit_result(False, warnings=["No runs in paragraph"],
                            refused_reason='not_found',
                            preserved_nodes=preserved)

    refused_nodes = _refused_node_names(para_elem)
    if refused_nodes:
        return _edit_result(
            False,
            warnings=[f"Refused: paragraph contains protected nodes: "
                      f"{', '.join(refused_nodes)}"],
            preserved_nodes=preserved,
            refused_reason='protected_node_paragraph')

    first_rPr = _clone_run_format(runs[0])
    backup = copy.deepcopy(para_elem)
    try:
        # 只清空文本节点，保留 rPr、书签、批注范围等其余子节点
        touched_runs = 0
        for run_elem in runs:
            removed = False
            for child in list(run_elem):
                if child.tag in _EDITABLE_TEXT_TAGS:
                    run_elem.remove(child)
                    removed = True
            if removed:
                touched_runs += 1
        if new_text:
            new_run = _new_text_run(para_elem, new_text, first_rPr, red=red)
            runs[0].addnext(new_run)
    except Exception as exc:  # 回滚，保证文档不会被改坏
        _restore_children(para_elem, backup)
        return _edit_result(
            False,
            warnings=[f"Replacement failed and paragraph was restored: {exc}"],
            preserved_nodes=protected_nodes_in_element(para_elem),
            error=str(exc))

    if touched_runs > 1:
        method = 'multi_node_merge'
    elif touched_runs == 1:
        method = 'text_node_split'
    else:
        method = None
    return _edit_result(True, method=method,
                        preserved_nodes=protected_nodes_in_element(para_elem))


def insert_paragraph_after(para, text, red=True, bold=False, italic=False,
                           inherit_format=True):
    """
    Insert a new paragraph after the given paragraph.

    Args:
        para: python-docx Paragraph object (or XML element)
        text: text content
        red: highlight in red
        bold: bold text
        italic: italic text
        inherit_format: inherit format from the reference paragraph

    Returns:
        new paragraph XML element
    """
    para_elem = para._element if hasattr(para, '_element') else para
    parent = para_elem.getparent()

    # Clone the reference paragraph structure
    new_p = copy.deepcopy(para_elem)

    # Clear all runs from the clone
    for child in list(new_p):
        if child.tag.endswith('}r') or child.tag.endswith('}hyperlink'):
            new_p.remove(child)

    # Create new run
    new_r = etree.SubElement(new_p, qn('w:r'))
    rpr = etree.SubElement(new_r, qn('w:rPr'))

    # Set color
    color = etree.SubElement(rpr, qn('w:color'))
    color.set(qn('w:val'), 'FF0000' if red else '000000')

    if bold:
        etree.SubElement(rpr, qn('w:b'))
    if italic:
        etree.SubElement(rpr, qn('w:i'))

    t = etree.SubElement(new_r, qn('w:t'))
    t.text = text
    t.set(qn('xml:space'), 'preserve')

    # Insert after the reference paragraph
    para_elem.addnext(new_p)
    return new_p


def _scope_paragraph_indices(scope, paragraphs):
    """
    把 scope.included_paragraphs 归一化成段落索引列表（保持原顺序）。

    现有实现里是 int 列表；兼容直接传入 Paragraph 对象的情况（用 lxml 元素身份
    定位，避免 python-docx 包装对象每次重建导致 id() 不稳）。
    """
    entries = getattr(scope, 'included_paragraphs', None) or []
    element_to_index = {id(p._element): i for i, p in enumerate(paragraphs)}
    indices = []
    for entry in entries:
        if isinstance(entry, int) and not isinstance(entry, bool):
            index = entry
        else:
            element = getattr(entry, '_element', None)
            index = element_to_index.get(id(element)) if element is not None else None
            if index is None and hasattr(entry, 'text'):
                index = next(
                    (i for i, p in enumerate(paragraphs) if p.text == entry.text),
                    None)
        if index is not None and 0 <= index < len(paragraphs) \
                and index not in indices:
            indices.append(index)
    return indices


def replace_section_text(doc, scope, replacements):
    """
    Apply multiple text replacements within a resolved scope.

    Args:
        doc: python-docx Document
        scope: EditScope with paragraph range
        replacements: list of (old_text, new_text) tuples

    Returns:
        list of change results：契约 dict + old_text / new_text / paragraph_index
    """
    results = []
    paragraphs = doc.paragraphs

    for old_text, new_text in replacements:
        found = False
        for idx in _scope_paragraph_indices(scope, paragraphs):
            if idx >= len(paragraphs):
                continue
            para = paragraphs[idx]
            if old_text in para.text:
                result = replace_text_in_paragraph(para, old_text, new_text, red=True)
                result['old_text'] = old_text
                result['new_text'] = new_text
                result['paragraph_index'] = idx
                results.append(result)
                found = True
                break  # Replace first occurrence only
        if not found:
            result = _edit_result(
                False,
                warnings=[f"Text not found in scope: '{old_text[:50]}'"],
                refused_reason='not_found')
            result['old_text'] = old_text
            result['new_text'] = new_text
            result['paragraph_index'] = None
            results.append(result)

    return results
