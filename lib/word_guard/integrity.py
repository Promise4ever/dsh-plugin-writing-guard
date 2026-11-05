# -*- coding: utf-8 -*-
"""
Scope Integrity Checker.

Verifies that editing operations did not modify content outside
the requested scope. Compares paragraph text / format, tables and
headers/footers before and after editing.
"""

from dataclasses import dataclass, field
from typing import Optional, List


# 变更清单里 before/after 预览的最大字符数
PREVIEW_LIMIT = 100


@dataclass
class IntegrityCheckResult:
    """Result of a scope integrity check."""
    scope_intact: bool = True
    requested_scope: str = ""
    unchanged_regions: list = field(default_factory=list)
    unexpected_changes: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    # 段落 / 表格 / 页眉页脚数量快照，便于调用方判断结构变化
    counts: dict = field(default_factory=dict)


def _preview(value, limit=PREVIEW_LIMIT):
    """把比较值转成短字符串，便于写入 JSON 变更清单。"""
    text = value if isinstance(value, str) else str(value)
    if len(text) > limit:
        text = text[:limit] + '...'
    return text


def _get_para_element(para):
    """兼容 python-docx Paragraph 对象与裸 lxml 元素。"""
    return para._element if hasattr(para, '_element') else para


def _get_para_texts(doc):
    """Extract all paragraph texts from a document."""
    return [p.text for p in doc.paragraphs]


def _scope_paragraph_indices(scope, doc_before):
    """
    把 scope.included_paragraphs 归一化成 doc_before 的段落索引集合。

    现有实现里 included_paragraphs 是 int 列表；这里同时兼容直接传入
    Paragraph 对象（用 lxml 元素身份定位，避免 python-docx 包装对象每次重建
    导致 id() 不稳）。
    """
    entries = getattr(scope, 'included_paragraphs', None) or []
    paragraphs = doc_before.paragraphs
    element_to_index = {id(p._element): i for i, p in enumerate(paragraphs)}

    indices = set()
    for entry in entries:
        if isinstance(entry, int) and not isinstance(entry, bool):
            indices.add(entry)
            continue
        element = _get_para_element(entry)
        if element is None:
            continue
        index = element_to_index.get(id(element))
        if index is None and hasattr(entry, 'text'):
            # 退化路径：按文本定位（对象身份对不上时）
            index = next(
                (i for i, p in enumerate(paragraphs) if p.text == entry.text),
                None)
        if index is not None:
            indices.add(index)

    return indices


def _format_signature(para):
    """段落级格式指纹：对齐方式 + 样式名。"""
    alignment = para.paragraph_format.alignment
    alignment_name = getattr(alignment, 'name', alignment)
    style = para.style
    style_name = style.name if style is not None else None
    return f"alignment={alignment_name}, style={style_name}"


def _table_cell_texts(table):
    """按行优先顺序返回表格全部单元格文本。"""
    texts = []
    for row in table.rows:
        for cell in row.cells:
            texts.append(cell.text)
    return texts


def _header_footer_snapshot(section):
    """
    返回 (header_texts, footer_texts)；未定义（链接到上一节）的一侧为 None。

    注意：python-docx 在访问 .paragraphs 时会为本节凭空创建页眉页脚部件，
    因此必须先判断 is_linked_to_previous，再读段落。
    """
    header_texts = None
    footer_texts = None

    header = section.header
    if not header.is_linked_to_previous:
        header_texts = [p.text for p in header.paragraphs]

    footer = section.footer
    if not footer.is_linked_to_previous:
        footer_texts = [p.text for p in footer.paragraphs]

    return header_texts, footer_texts


def _header_footer_effective_texts(doc):
    """
    按 section 顺序返回 (header_text, footer_text)、显式定义段落总数与定义标记。

    链接到上一节的 section 沿用上一节内容（与 Word 渲染一致）；定义标记用于在
    比较时跳过“两侧都只是继承”的 section，避免同一处改动被重复报告。
    """
    snapshots = []
    defined_flags = []
    header_text = ''
    footer_text = ''
    defined_paragraphs = 0

    for section in doc.sections:
        header_texts, footer_texts = _header_footer_snapshot(section)
        header_defined = header_texts is not None
        footer_defined = footer_texts is not None
        if header_defined:
            header_text = '\n'.join(header_texts)
            defined_paragraphs += len(header_texts)
        if footer_defined:
            footer_text = '\n'.join(footer_texts)
            defined_paragraphs += len(footer_texts)
        snapshots.append((header_text, footer_text))
        defined_flags.append((header_defined, footer_defined))

    return snapshots, defined_paragraphs, defined_flags


def check_scope_integrity(doc_before, doc_after, scope, scope_description=""):
    """
    Verify that only the intended scope was modified.

    Compares paragraph texts / formats, tables and headers/footers and reports
    any unexpected changes outside the requested scope.

    Args:
        doc_before: python-docx Document (before editing)
        doc_after: python-docx Document (after editing)
        scope: EditScope with paragraph range
        scope_description: human-readable description of the scope

    Returns:
        IntegrityCheckResult
    """
    result = IntegrityCheckResult(requested_scope=scope_description)

    texts_before = _get_para_texts(doc_before)
    texts_after = _get_para_texts(doc_after)
    paras_before = doc_before.paragraphs
    paras_after = doc_after.paragraphs
    tables_before = doc_before.tables
    tables_after = doc_after.tables
    hf_before, hf_count_before, hf_defined_before = _header_footer_effective_texts(
        doc_before)
    hf_after, hf_count_after, hf_defined_after = _header_footer_effective_texts(
        doc_after)

    result.counts = {
        'paragraphs_before': len(texts_before),
        'paragraphs_after': len(texts_after),
        'tables_before': len(tables_before),
        'tables_after': len(tables_after),
        'headers_footers_before': hf_count_before,
        'headers_footers_after': hf_count_after,
    }

    # ── 1) 段落数变化：尾段被删也要靠这一步捕获 ──────────────────────────
    if len(texts_before) != len(texts_after):
        result.unexpected_changes.append({
            'kind': 'paragraph_count',
            'index': None,
            'before': len(texts_before),
            'after': len(texts_after),
        })
        result.warnings.append(
            f"Paragraph count changed: {len(texts_before)} → {len(texts_after)}"
        )

    scope_indices = _scope_paragraph_indices(scope, doc_before)

    # ── 2) 范围外段落：文本 + 对齐 / 样式 ────────────────────────────────
    total_paras = min(len(paras_before), len(paras_after))
    for i in range(total_paras):
        if i in scope_indices:
            continue
        if texts_before[i] != texts_after[i]:
            result.unexpected_changes.append({
                'kind': 'paragraph',
                'index': i,
                'before': _preview(texts_before[i]),
                'after': _preview(texts_after[i]),
            })
            continue
        format_before = _format_signature(paras_before[i])
        format_after = _format_signature(paras_after[i])
        if format_before != format_after:
            result.unexpected_changes.append({
                'kind': 'paragraph_format',
                'index': i,
                'before': format_before,
                'after': format_after,
            })

    # ── 3) 表格：数量 + 逐单元格文本 ────────────────────────────────────
    if len(tables_before) != len(tables_after):
        result.unexpected_changes.append({
            'kind': 'table',
            'index': None,
            'before': len(tables_before),
            'after': len(tables_after),
        })
        result.warnings.append(
            f"Table count changed: {len(tables_before)} → {len(tables_after)}"
        )
    else:
        for table_index in range(len(tables_before)):
            cells_before = _table_cell_texts(tables_before[table_index])
            cells_after = _table_cell_texts(tables_after[table_index])
            if cells_before != cells_after:
                result.unexpected_changes.append({
                    'kind': 'table',
                    'index': table_index,
                    'before': _preview(cells_before),
                    'after': _preview(cells_after),
                })

    # ── 4) 页眉页脚：逐 section 比较有效文本（链接段已继承上一节）────────
    for section_index in range(min(len(hf_before), len(hf_after))):
        if hf_before[section_index] == hf_after[section_index]:
            continue
        # 两侧都只是“链接到上一节”时，变化来自前面的 section，已在那里比较过
        if (not any(hf_defined_before[section_index])
                and not any(hf_defined_after[section_index])):
            continue
        result.unexpected_changes.append({
            'kind': 'header_footer',
            'index': section_index,
            'before': _preview(hf_before[section_index]),
            'after': _preview(hf_after[section_index]),
        })

    # ── 5) 范围内段落的预期变化统计（仅用于报告，不影响 scope_intact）────
    scope_changed = 0
    scope_unchanged = 0
    for i in range(total_paras):
        if i not in scope_indices:
            continue
        if texts_before[i] != texts_after[i]:
            scope_changed += 1
        else:
            scope_unchanged += 1

    # ── 6) 结论：任一 unexpected → scope_intact=False ───────────────────
    if result.unexpected_changes:
        result.scope_intact = False
        result.warnings.append(
            f"{len(result.unexpected_changes)} unexpected changes found "
            f"outside the requested scope"
        )
    else:
        result.scope_intact = True
        # 只有真的没有 unexpected 时才敢声明“范围外未变”
        result.unchanged_regions.append("All out-of-scope content is unchanged")

    scope_summary = (
        f"Scope: {scope_changed} paragraphs modified, "
        f"{scope_unchanged} paragraphs unchanged within scope"
    )
    if result.scope_intact:
        result.unchanged_regions.append(scope_summary)
    else:
        result.warnings.append(scope_summary)

    return result


def compare_paragraphs(before_paras, after_paras, indices):
    """
    Compare specific paragraphs between two document states.

    Args:
        before_paras: paragraphs from before document
        after_paras: paragraphs from after document
        indices: list of paragraph indices to compare

    Returns:
        list of dicts with comparison results
    """
    results = []
    for i in indices:
        if i < len(before_paras) and i < len(after_paras):
            before_text = before_paras[i].text
            after_text = after_paras[i].text
            results.append({
                'index': i,
                'changed': before_text != after_text,
                'before': before_text[:200],
                'after': after_text[:200],
            })
    return results
