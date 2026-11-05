# -*- coding: utf-8 -*-
"""
Protected Node Policy.

Defines which XML nodes and document elements must never be modified
during editing operations, and provides helpers for checking
complex paragraph status.
"""

from docx.oxml.ns import qn


# ── Protected XML Tags ────────────────────────────────────────────────────
# These nodes must never be deleted, modified, or recreated unless
# the user explicitly requests it.

PROTECTED_TAGS = {
    # Section properties
    'sectPr': qn('w:sectPr'),

    # Bookmarks
    'bookmarkStart': qn('w:bookmarkStart'),
    'bookmarkEnd': qn('w:bookmarkEnd'),

    # Fields (cross-references, TOC, etc.)
    'fldChar': qn('w:fldChar'),
    'instrText': qn('w:instrText'),
    'fldSimple': qn('w:fldSimple'),

    # Images and drawings
    'drawing': qn('w:drawing'),
    'pict': qn('w:pict'),
    'object': qn('w:object'),

    # Hyperlinks
    'hyperlink': qn('w:hyperlink'),

    # Footnotes and endnotes
    'footnoteReference': qn('w:footnoteReference'),
    'endnoteReference': qn('w:endnoteReference'),
    'footnote': qn('w:footnote'),
    'endnote': qn('w:endnote'),

    # Comments
    'commentReference': qn('w:commentReference'),
    'commentStart': qn('w:commentRangeStart'),
    'commentEnd': qn('w:commentRangeEnd'),
    'comment': qn('w:comment'),

    # Equations
    'oMath': qn('m:oMath'),
    'oMathPara': qn('m:oMathPara'),

    # Table structure
    'tbl': qn('w:tbl'),
    'tr': qn('w:tr'),
    'tc': qn('w:tc'),

    # Page setup
    'pgSz': qn('w:pgSz'),
    'pgMar': qn('w:pgMar'),
    'cols': qn('w:cols'),

    # Headers and footers
    'hdr': qn('w:hdr'),
    'ftr': qn('w:ftr'),
}

# 反向映射：XML 标签 → 受保护节点名（按文档顺序遍历整棵子树时使用）
_TAG_TO_PROTECTED_NAME = {tag: name for name, tag in PROTECTED_TAGS.items()}


def _as_element(node):
    """兼容 python-docx 包装对象（如 Paragraph）与裸 lxml 元素。"""
    return node._element if hasattr(node, '_element') else node


def protected_nodes_in_element(element):
    """
    返回 element 子树里出现的受保护节点标签名。

    按 PROTECTED_TAGS 的键名返回，文档顺序、去重；element 自身也参与判断。

    Args:
        element: lxml 元素或 python-docx 包装对象（如 Paragraph）

    Returns:
        list[str]
    """
    element = _as_element(element)
    if element is None:
        return []
    names = []
    for node in element.iter():
        name = _TAG_TO_PROTECTED_NAME.get(node.tag)
        if name is not None and name not in names:
            names.append(name)
    return names


def protected_nodes_between(paragraph, first_run_index, last_run_index):
    """
    返回 paragraph 直接 run 列表里 [first, last] 区间内各 run 含的受保护节点标签名。

    只统计 w:p 的直接 w:r 子节点（与 Paragraph.runs 一致）；索引会自动收敛到
    合法范围，避免越界。

    Args:
        paragraph: python-docx Paragraph 对象或 w:p 元素
        first_run_index: 起始 run 索引（含）
        last_run_index: 结束 run 索引（含）

    Returns:
        list[str]：文档顺序、去重
    """
    element = _as_element(paragraph)
    if element is None:
        return []
    runs = [child for child in element if child.tag == qn('w:r')]
    if not runs:
        return []

    last_index = len(runs) - 1
    start = max(0, min(first_run_index, last_run_index, last_index))
    end = max(0, min(max(first_run_index, last_run_index), last_index))

    names = []
    for run_elem in runs[start:end + 1]:
        for name in protected_nodes_in_element(run_elem):
            if name not in names:
                names.append(name)
    return names


def is_protected_node(element):
    """
    Check if an XML element is a protected node that must not be modified.

    Args:
        element: lxml etree element

    Returns:
        True if the element is protected
    """
    if element is None:
        return False
    tag = element.tag
    for protected_tag in PROTECTED_TAGS.values():
        if tag == protected_tag:
            return True
    return False


def check_complex_paragraph(para):
    """
    Check if a paragraph is complex (contains protected objects).

    A complex paragraph requires run-aware or XML-aware editing.
    Simple text replacement should NOT be used on complex paragraphs.

    Args:
        para: python-docx Paragraph object

    Returns:
        dict with complexity analysis
    """
    elem = para._element if hasattr(para, '_element') else para

    result = {
        'is_complex': False,
        'has_equation': False,
        'has_drawing': False,
        'has_field': False,
        'has_hyperlink': False,
        'has_bookmark': False,
        'has_footnote': False,
        'has_comment': False,
        'protected_nodes': [],
        'risk_level': 'low',  # low / medium / high
    }

    # Check for equations
    eq = elem.find('.//' + qn('m:oMath'))
    eq_para = elem.find('.//' + qn('m:oMathPara'))
    if eq is not None or eq_para is not None:
        result['has_equation'] = True
        result['is_complex'] = True
        result['protected_nodes'].append('equation')

    # Check for drawings/images
    drawing = elem.find('.//' + qn('w:drawing'))
    if drawing is not None:
        result['has_drawing'] = True
        result['is_complex'] = True
        result['protected_nodes'].append('drawing')

    # Check for fields
    fld_char = elem.find('.//' + qn('w:fldChar'))
    instr = elem.find('.//' + qn('w:instrText'))
    if fld_char is not None or instr is not None:
        result['has_field'] = True
        result['is_complex'] = True
        result['protected_nodes'].append('field')

    # Check for hyperlinks
    hyperlink = elem.find(qn('w:hyperlink'))
    if hyperlink is not None:
        result['has_hyperlink'] = True
        result['is_complex'] = True
        result['protected_nodes'].append('hyperlink')

    # Check for bookmarks
    bm_start = elem.find('.//' + qn('w:bookmarkStart'))
    if bm_start is not None:
        result['has_bookmark'] = True
        result['is_complex'] = True
        result['protected_nodes'].append('bookmark')

    # Check for footnotes
    fn_ref = elem.find('.//' + qn('w:footnoteReference'))
    if fn_ref is not None:
        result['has_footnote'] = True
        result['is_complex'] = True
        result['protected_nodes'].append('footnote')

    # Check for comments
    cm_ref = elem.find('.//' + qn('w:commentReference'))
    if cm_ref is not None:
        result['has_comment'] = True
        result['is_complex'] = True
        result['protected_nodes'].append('comment')

    # Determine risk level
    if result['has_equation'] or result['has_field']:
        result['risk_level'] = 'high'
    elif result['has_drawing'] or result['has_hyperlink'] or result['has_bookmark']:
        result['risk_level'] = 'medium'
    else:
        result['risk_level'] = 'low'

    return result


def get_protected_elements_in_range(doc, start_idx, end_idx):
    """
    Find all protected elements within a paragraph range.

    Args:
        doc: python-docx Document
        start_idx: start paragraph index (inclusive)
        end_idx: end paragraph index (exclusive)

    Returns:
        list of dicts describing protected elements found
    """
    protected = []

    for i in range(start_idx, min(end_idx, len(doc.paragraphs))):
        para = doc.paragraphs[i]
        check = check_complex_paragraph(para)
        if check['is_complex']:
            protected.append({
                'paragraph_index': i,
                'text_preview': para.text[:80],
                'protected_nodes': check['protected_nodes'],
                'risk_level': check['risk_level'],
            })

    return protected
