# -*- coding: utf-8 -*-
"""
Scope Resolver.

Locates edit targets in a DOCX document using structural anchors
(headings, section numbers) rather than page numbers or paragraph indices.
"""

import re
from dataclasses import dataclass, field
from typing import Optional, List
from difflib import SequenceMatcher


@dataclass
class EditScope:
    """Resolved edit scope with paragraph range and protection info."""
    start_para_index: int
    end_para_index: int
    start_heading: Optional[str] = None
    end_heading: Optional[str] = None
    start_heading_level: Optional[int] = None
    end_heading_level: Optional[int] = None
    included_paragraphs: list = field(default_factory=list)  # list[int]
    included_tables: list = field(default_factory=list)  # list[int]
    protected_neighbors: list = field(default_factory=list)  # list[str]
    ambiguous: bool = False
    ambiguity_options: list = field(default_factory=list)  # list[str]
    warnings: list = field(default_factory=list)
    # Non-empty means the scope could not be resolved (incomplete / unparseable
    # range parameters).  Callers must refuse the edit instead of using the
    # default range fields.
    error: Optional[str] = None


def _normalize_heading(text):
    """Normalize heading text for matching."""
    return re.sub(r'\s+', ' ', text.strip().lower())


def _fuzzy_match(query, candidate, threshold=0.6):
    """Check if candidate matches query with fuzzy matching."""
    q = _normalize_heading(query)
    c = _normalize_heading(candidate)

    # Exact match
    if q == c:
        return 1.0

    # Substring match
    if q in c or c in q:
        return 0.9

    # SequenceMatcher for fuzzy
    ratio = SequenceMatcher(None, q, c).ratio()
    return ratio


def _is_heading(para):
    """Check if a paragraph is a heading (supports both WordParagraphInfo and raw Paragraph)."""
    if hasattr(para, 'is_heading'):
        return para.is_heading
    # Raw python-docx Paragraph: check style name
    if hasattr(para, 'style') and para.style:
        style_name = para.style.name or ''
        if style_name.startswith('Heading'):
            return True
    return False


def _get_heading_level(para):
    """Get heading level (supports both WordParagraphInfo and raw Paragraph)."""
    if hasattr(para, 'heading_level'):
        return para.heading_level
    # Raw python-docx Paragraph
    if hasattr(para, 'style') and para.style:
        import re
        m = re.search(r'heading\s*(\d+)', para.style.name or '', re.IGNORECASE)
        if m:
            return int(m.group(1))
    return None


def _get_para_text(para):
    """Get paragraph text (supports both WordParagraphInfo and raw Paragraph)."""
    if hasattr(para, 'text'):
        return para.text
    return ''


def _get_para_index(para, fallback_index):
    """Get paragraph index (supports both WordParagraphInfo and raw Paragraph)."""
    if hasattr(para, 'index'):
        return para.index
    return fallback_index


def _find_heading(paragraphs, heading_text, level=None, allow_fuzzy=True):
    """
    Find a heading paragraph matching the given text.

    Args:
        paragraphs: list of WordParagraphInfo or raw Paragraph objects
        heading_text: heading text to match
        level: optional heading level to filter by
        allow_fuzzy: whether to use fuzzy matching

    Returns:
        list of (index, match_score, paragraph_info) tuples
    """
    matches = []
    for i, p in enumerate(paragraphs):
        if not _is_heading(p):
            continue
        p_level = _get_heading_level(p)
        if level is not None and p_level is not None and p_level != level:
            continue

        text = _get_para_text(p)
        score = _fuzzy_match(heading_text, text)
        if score >= 0.5:
            idx = _get_para_index(p, i)
            matches.append((idx, score, p))

    # Sort by score descending
    matches.sort(key=lambda x: -x[1])
    return matches


def _scope_error(scope, message):
    """Mark a scope as unresolvable and return it.

    A half-specified or contradictory range must never silently degrade to
    "the whole document": the caller has to see the error and refuse to write.
    """
    scope.start_para_index = 0
    scope.end_para_index = -1
    scope.included_paragraphs = []
    scope.ambiguous = True
    scope.error = message
    scope.warnings.append(message)
    return scope


def resolve_scope(paragraphs, start_heading=None, end_heading=None,
                  heading=None, level=None, start_index=None, end_index=None,
                  allow_fuzzy=True):
    """
    Resolve an edit scope from heading anchors or paragraph indices.

    Supports multiple resolution modes:
    1. Section by heading: start_heading → end_heading
    2. Single section: heading (uses parent/child boundaries)
    3. Direct index range: start_index → end_index

    Args:
        paragraphs: list of WordParagraphInfo from scanner
        start_heading: start heading text (inclusive)
        end_heading: end heading text (exclusive)
        heading: single heading to select (for edit_section mode)
        level: heading level filter
        start_index: direct start paragraph index
        end_index: direct end paragraph index
        allow_fuzzy: whether to use fuzzy heading matching

    Returns:
        EditScope with resolved paragraph range. If the supplied parameters are
        incomplete or unresolvable, ``scope.error`` is set and
        ``included_paragraphs`` stays empty — callers must not edit anything.
    """
    scope = EditScope(start_para_index=0, end_para_index=len(paragraphs) - 1)
    total_paragraphs = len(paragraphs)

    # Empty heading strings mean "not supplied" (the tool schema may forward '').
    start_heading = start_heading or None
    end_heading = end_heading or None
    heading = heading or None

    # ── Mode 0: Validate the range parameters ──
    # The tool schema lets callers supply any subset of anchors. A lone or
    # contradictory boundary is a caller error, never an invitation to edit
    # the whole document.
    if heading is not None and (start_heading is not None or end_heading is not None):
        return _scope_error(
            scope,
            "范围参数冲突：heading 不能与 start_heading/end_heading 同时使用",
        )

    if (start_heading is None) != (end_heading is None):
        provided = 'start_heading' if start_heading is not None else 'end_heading'
        missing = 'end_heading' if provided == 'start_heading' else 'start_heading'
        return _scope_error(
            scope,
            f"范围边界不成对：只提供了 {provided}，缺少 {missing}"
            "（章节范围必须同时给出起止标题）",
        )

    if (start_index is None) != (end_index is None):
        provided = 'start_index' if start_index is not None else 'end_index'
        missing = 'end_index' if provided == 'start_index' else 'start_index'
        return _scope_error(
            scope,
            f"范围边界不成对：只提供了 {provided}，缺少 {missing}"
            "（段落范围必须同时给出起止索引）",
        )

    if start_index is not None and end_index is not None:
        if start_index < 0 or end_index < 0:
            return _scope_error(
                scope,
                f"段落范围越界：start_index={start_index}, end_index={end_index}，索引不能为负",
            )
        if start_index >= total_paragraphs or end_index >= total_paragraphs:
            return _scope_error(
                scope,
                f"段落范围越界：文档共 {total_paragraphs} 个段落，"
                f"请求 start_index={start_index}, end_index={end_index}",
            )
        if start_index > end_index:
            return _scope_error(
                scope,
                f"段落范围无效：start_index({start_index}) 大于 end_index({end_index})",
            )

    # ── Mode 1: Explicit index range ──
    if start_index is not None and end_index is not None:
        scope.start_para_index = start_index
        scope.end_para_index = end_index
        scope.included_paragraphs = list(
            range(scope.start_para_index, scope.end_para_index + 1)
        )
        return scope

    # ── Mode 2: Section range (start_heading → end_heading) ──
    if start_heading and end_heading:
        start_matches = _find_heading(paragraphs, start_heading, level, allow_fuzzy)
        end_matches = _find_heading(paragraphs, end_heading, level, allow_fuzzy)

        if not start_matches:
            return _scope_error(scope, f"未找到起始标题：'{start_heading}'")
        if not end_matches:
            return _scope_error(scope, f"未找到结束标题：'{end_heading}'")

        if len(start_matches) > 1 and start_matches[0][1] < 0.9:
            scope.ambiguity_options = [_get_para_text(m[2]) for m in start_matches[:5]]
            return _scope_error(
                scope,
                f"起始标题匹配存在歧义：'{start_heading}' 可能是 "
                f"{[_get_para_text(m[2]) for m in start_matches[:3]]}",
            )
        if len(end_matches) > 1 and end_matches[0][1] < 0.9:
            scope.ambiguity_options = [_get_para_text(m[2]) for m in end_matches[:5]]
            return _scope_error(
                scope,
                f"结束标题匹配存在歧义：'{end_heading}' 可能是 "
                f"{[_get_para_text(m[2]) for m in end_matches[:3]]}",
            )

        start_idx = start_matches[0][0]
        end_idx = end_matches[0][0]
        if end_idx <= start_idx:
            return _scope_error(
                scope,
                f"章节范围无效：结束标题 '{_get_para_text(end_matches[0][2])}' "
                f"(段落 {end_idx}) 不在起始标题 "
                f"'{_get_para_text(start_matches[0][2])}' (段落 {start_idx}) 之后",
            )

        scope.start_para_index = start_idx
        scope.end_para_index = end_idx - 1  # exclusive
        scope.start_heading = _get_para_text(start_matches[0][2])
        scope.end_heading = _get_para_text(end_matches[0][2])
        scope.start_heading_level = _get_heading_level(start_matches[0][2])
        scope.end_heading_level = _get_heading_level(end_matches[0][2])
        scope.included_paragraphs = list(range(start_idx, end_idx))

        return scope

    # ── Mode 3: Single heading (section edit) ──
    if heading:
        matches = _find_heading(paragraphs, heading, level, allow_fuzzy)

        if not matches:
            return _scope_error(scope, f"未找到标题：'{heading}'")

        if len(matches) > 1 and matches[0][1] < 0.9:
            scope.ambiguity_options = [_get_para_text(m[2]) for m in matches[:5]]
            return _scope_error(
                scope,
                f"标题匹配存在歧义：'{heading}' 可能是 "
                f"{[_get_para_text(m[2]) for m in matches[:3]]}",
            )

        target = matches[0]
        target_idx = target[0]
        target_level = _get_heading_level(target[2]) or 1

        # Find the end: next heading at same or higher level
        end_idx = len(paragraphs)
        for j, p in enumerate(paragraphs[target_idx + 1:]):
            if _is_heading(p) and _get_heading_level(p) is not None and _get_heading_level(p) <= target_level:
                end_idx = _get_para_index(p, target_idx + 1 + j)
                break

        scope.start_para_index = target_idx
        scope.end_para_index = end_idx - 1
        scope.start_heading = _get_para_text(target[2])
        scope.start_heading_level = target_level
        scope.included_paragraphs = list(range(target_idx, end_idx))

        return scope

    # ── Default: full document ──
    scope.included_paragraphs = list(range(len(paragraphs)))
    return scope


def find_paragraph_containing(paragraphs, substring, case_sensitive=False):
    """
    Find all paragraphs whose text contains the given substring.

    Args:
        paragraphs: list of WordParagraphInfo (or doc.paragraphs)
        substring: text to search for
        case_sensitive: whether the search is case-sensitive

    Returns:
        list of (index, paragraph) tuples
    """
    results = []
    for i, p in enumerate(paragraphs):
        text = p.text if hasattr(p, 'text') else str(p)
        if case_sensitive:
            if substring in text:
                results.append((i, p))
        else:
            if substring.lower() in text.lower():
                results.append((i, p))
    return results
