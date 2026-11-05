# -*- coding: utf-8 -*-
"""
Word Manuscript Guard - CLI and Tool Interface.

Provides the main entry points for DOCX operations:
- writing_word_scan: structural scan
- writing_word_edit: safe section/paragraph editing
- writing_word_audit: writing audit on extracted text
- writing_word_scope_check: verify scope integrity
"""

import os
import sys
import json
import copy
import errno
import shutil
import tempfile
import time
import zipfile
from pathlib import Path
from dataclasses import asdict, is_dataclass

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from word_guard.scanner import scan_docx, print_scan_summary
from word_guard.scope import resolve_scope, find_paragraph_containing
from word_guard.editor import (
    replace_text_in_paragraph,
    replace_entire_paragraph,
    insert_paragraph_after,
    replace_section_text,
)
from word_guard.protected import check_complex_paragraph, get_protected_elements_in_range
from word_guard.manifest import ChangeManifest
from word_guard.integrity import check_scope_integrity
from word_guard.package_guard import validate_docx_package, compare_package_parts
from word_guard.fingerprint import build_baseline_fingerprint
from word_guard.equation_audit import audit_equations
from word_guard.table_format import convert_tables_to_three_line
from word_guard.equation_format import format_equations
from word_guard.paragraph_format import justify_body_paragraphs


def _apply_default_academic_formatting(doc, include_unknown_tables=True):
    """Apply Word Guard's default academic table and equation presentation.

    Defaults:
    - non-layout tables -> clear old table style, apply three-line borders,
      center cell content horizontally and vertically;
    - OMML equations -> center equation body and right-align a trailing equation
      number on the same line;
    - likely running body-text paragraphs -> justified alignment, while preserving
      headings, captions, equations, and explicit center/right alignment.
    """
    table_results = convert_tables_to_three_line(
        doc, baseline_path=None, include_unknown=include_unknown_tables
    )
    paragraph_results = justify_body_paragraphs(doc)
    equation_results = format_equations(doc)
    return {
        'tables': {
            'formatted': sum(1 for r in table_results if r.get('action') == 'formatted'),
            'skipped': sum(1 for r in table_results if r.get('action') == 'skipped'),
            'details': table_results,
        },
        'body_paragraphs': {
            'justified': sum(1 for r in paragraph_results if r.get('action') == 'justified'),
            'skipped': sum(1 for r in paragraph_results if r.get('action') == 'skipped'),
            'details': paragraph_results,
        },
        'equations': {
            'formatted_numbered': sum(1 for r in equation_results if r.get('action') == 'formatted_numbered'),
            'centered_unnumbered': sum(1 for r in equation_results if r.get('action') == 'centered_unnumbered'),
            'skipped_inline': sum(1 for r in equation_results if r.get('action') == 'skipped_inline'),
            'details': equation_results,
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# Shared helpers for the editing tools
# ═══════════════════════════════════════════════════════════════════════════

# The TypeScript tool schema uses camelCase; the Python resolver uses snake_case.
_SCOPE_KEYMAP = {
    'startHeading': 'start_heading',
    'endHeading': 'end_heading',
    'heading': 'heading',
    'startParagraph': 'start_index',
    'endParagraph': 'end_index',
    'start_heading': 'start_heading',
    'end_heading': 'end_heading',
    'start_index': 'start_index',
    'end_index': 'end_index',
    'level': 'level',
    'allow_fuzzy': 'allow_fuzzy',
}


def _normalize_scope_config(scope_config):
    """Map camelCase tool arguments to ``resolve_scope()`` keyword arguments.

    Returns ``(config, error)``.  Unrecognized keys are rejected rather than
    silently dropped: a typo must never degrade the edit to the whole document.
    """
    if not scope_config:
        return None, None
    if not isinstance(scope_config, dict):
        return None, f"范围参数必须是对象，收到 {type(scope_config).__name__}"

    config = {}
    unknown = []
    for key, value in scope_config.items():
        mapped = _SCOPE_KEYMAP.get(key)
        if mapped is None:
            unknown.append(str(key))
            continue
        if value is not None:
            config[mapped] = value
    if unknown:
        return None, f"无法识别的范围参数：{', '.join(sorted(unknown))}"
    return (config or None), None


def _coerce_edit_result(res):
    """Normalize the editor return value to the current dict contract.

    ``editor.replace_text_in_paragraph`` historically returned a bool in some
    code paths; the run-aware editor now returns a dict.  Both shapes are
    accepted so cli.py stays usable while the editor is being upgraded.
    """
    if isinstance(res, dict):
        return {
            'success': bool(res.get('success')),
            'method': res.get('method'),
            'warnings': list(res.get('warnings') or []),
            'preserved_nodes': list(res.get('preserved_nodes') or []),
            'refused_reason': res.get('refused_reason'),
            'error': res.get('error'),
            'old_text': res.get('old_text'),
            'new_text': res.get('new_text'),
            'paragraph_index': res.get('paragraph_index'),
        }
    return {
        'success': bool(res),
        'method': None,
        'warnings': [],
        'preserved_nodes': [],
        'refused_reason': None,
        'error': None,
        'old_text': None,
        'new_text': None,
        'paragraph_index': None,
    }


def _failed_change(old_text, new_text, warning, paragraph_index=None):
    """Build one failed replacement record in the coerced shape."""
    return {
        'success': False,
        'method': None,
        'warnings': [warning],
        'preserved_nodes': [],
        'refused_reason': None,
        'error': None,
        'old_text': old_text,
        'new_text': new_text,
        'paragraph_index': paragraph_index,
    }


def _scope_payload(scope):
    """Serialize an EditScope for tool output (including resolution errors)."""
    if scope is None:
        return {}
    return {
        'start': scope.start_para_index,
        'end': scope.end_para_index,
        'heading': scope.start_heading,
        'end_heading': scope.end_heading,
        'ambiguous': scope.ambiguous,
        'warnings': list(scope.warnings),
        'error': getattr(scope, 'error', None),
    }


def _empty_package_validation(error=None):
    return {
        'valid': False,
        'errors': [error] if error else [],
        'warnings': [],
        'xml_parts_checked': 0,
        'relationships_checked': 0,
        'orphan_media': [],
    }


def _empty_package_integrity():
    return {
        'intact': False,
        'changed_parts': [],
        'added_parts': [],
        'removed_parts': [],
        'unexpected_changed_parts': [],
        'unexpected_added_parts': [],
        'unexpected_removed_parts': [],
    }


def _failed_edit_result(error, output, replacements, scope=None,
                        default_formatting=None, applied=0):
    """Full result dictionary for an edit that must not touch the target."""
    total = len(replacements or [])
    return {
        'success': False,
        'complete': False,
        'applied': applied,
        'failed': max(0, total - applied),
        # 没有落盘就不算改动：applied 只表示"内存里替换成功了几条"。
        'changes': 0,
        'total_replacements': total,
        'output': output,
        'saved': False,
        'backup_path': None,
        'restored_parts': [],
        'error': error,
        'scope': _scope_payload(scope),
        'protected_elements': 0,
        'default_formatting': default_formatting or {'applied': False, 'reason': 'mode'},
        'package_validation': _empty_package_validation(error),
        'package_integrity': _empty_package_integrity(),
        'manifest_summary': '',
    }


def _validation_error_message(package_validation):
    details = package_validation.get('errors') or ['未知校验错误']
    return '包校验失败，未写入目标文件：' + '; '.join(str(e) for e in details[:3])


def _integrity_error_message(package_integrity):
    parts = (
        package_integrity.get('unexpected_removed_parts')
        or package_integrity.get('unexpected_changed_parts')
        or package_integrity.get('unexpected_added_parts')
        or []
    )
    return (
        '包完整性校验失败，未写入目标文件：意外变更的部件 '
        + ', '.join(parts[:5])
    )


def _safe_unlink(path):
    try:
        os.unlink(path)
    except OSError:
        pass


def _replace_file(src_path, dst_path, attempts=5):
    """Move a file onto its target, tolerating transient Windows file locks."""
    last_error = None
    for attempt in range(attempts):
        try:
            os.replace(src_path, dst_path)
            return
        except OSError as exc:
            last_error = exc
            if getattr(exc, 'winerror', None) == 17 or exc.errno == errno.EXDEV:
                # Target lives on another volume: fall back to a copy.
                shutil.copyfile(src_path, dst_path)
                _safe_unlink(src_path)
                return
            # Antivirus/indexers can briefly hold a fresh temp file; retry.
            time.sleep(0.2 * (attempt + 1))
    try:
        shutil.copyfile(src_path, dst_path)
        _safe_unlink(src_path)
        return
    except OSError:
        raise last_error


def _restore_missing_parts(target_path, original_path, missing_parts):
    """Copy package parts dropped by python-docx back into the saved package.

    Rewrites the ZIP with all current entries plus the missing entries read
    from the original package.  Returns the list of restored part names.
    """
    with zipfile.ZipFile(original_path) as zsrc:
        available = set(zsrc.namelist())
        payloads = {
            name: zsrc.read(name) for name in missing_parts if name in available
        }
    if not payloads:
        return []

    with zipfile.ZipFile(target_path) as zin:
        entries = [(info, zin.read(info.filename)) for info in zin.infolist()]

    tmp_out = target_path + '.restored'
    try:
        with zipfile.ZipFile(tmp_out, 'w', zipfile.ZIP_DEFLATED) as zout:
            for info, data in entries:
                zout.writestr(info, data)
            for name, data in payloads.items():
                zout.writestr(name, data)
        _replace_file(tmp_out, target_path)
    finally:
        _safe_unlink(tmp_out)
    return sorted(payloads)


def _commit_file(tmp_path, target_path):
    """Atomically move the validated temp document onto the target path."""
    _replace_file(tmp_path, target_path)


def _as_jsonable(value):
    """Convert dataclass results (e.g. integrity counts) to plain JSON values."""
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, dict):
        return {k: _as_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_as_jsonable(v) for v in value]
    return value


# ═══════════════════════════════════════════════════════════════════════════
# Tool 1: writing_word_scan
# ═══════════════════════════════════════════════════════════════════════════

def writing_word_scan(file_path):
    """
    Perform a structural scan of a DOCX file.

    Returns document profile, heading hierarchy, paragraph info,
    tables, equations, and warnings.

    Args:
        file_path: path to the .docx file

    Returns:
        dict with complete structural analysis
    """
    if not os.path.exists(file_path):
        return {'error': f"File not found: {file_path}"}

    info = scan_docx(file_path)

    result = {
        'file': info.file_name,
        'profile': info.detected_profile,
        'paragraphs': info.paragraph_count,
        'headings': [
            {
                'index': h.index,
                'level': h.heading_level,
                'text': h.text[:120],
                'style': h.style_id,
            }
            for h in info.headings
        ],
        'tables': [
            {
                'index': t.index,
                'rows': t.rows,
                'cols': t.cols,
                'preview': t.text_preview,
                'equations': t.equations,
            }
            for t in info.tables
        ],
        'objects': {
            'equations': info.total_equations,
            'drawings': info.total_drawings,
            'fields': info.total_fields,
            'hyperlinks': info.total_hyperlinks,
            'bookmarks': info.total_bookmarks,
            'footnotes': info.total_footnotes,
            'comments': info.total_comments,
        },
        'complex_paragraphs': sum(1 for p in info.paragraphs if p.is_complex),
        'sections': info.section_count,
        'warnings': info.warnings,
    }

    return result


# ═══════════════════════════════════════════════════════════════════════════
# Tool 2: writing_word_edit
# ═══════════════════════════════════════════════════════════════════════════

def writing_word_edit(file_path, replacements, scope_config=None,
                      mode='text_only', output_path=None, backup=True):
    """
    Safely edit specific sections of a DOCX file.

    Args:
        file_path: path to the source .docx file
        replacements: list of dicts with 'old' and 'new' keys
        scope_config: dict with scope resolution parameters:
            - start_heading, end_heading: section range
            - heading: single section to edit
            - start_index, end_index: direct paragraph indices
        mode: 'text_only' (default), 'structural', or 'format_normalization'
        output_path: output file path (default: overwrite original)
        backup: whether to create a backup before editing

    Returns:
        dict with edit results and change manifest
    """
    output = output_path or file_path
    if isinstance(replacements, dict):
        replacements = replacements.get('replacements') or []
    replacements = list(replacements or [])
    total_replacements = len(replacements)

    if not os.path.exists(file_path):
        return _failed_edit_result(f"File not found: {file_path}", output, replacements)

    scope_config, config_error = _normalize_scope_config(scope_config)
    if config_error:
        return _failed_edit_result(config_error, output, replacements)

    # Load document
    from docx import Document
    try:
        doc = Document(file_path)
    except Exception as exc:
        return _failed_edit_result(f"无法打开 DOCX 文件：{exc}", output, replacements)

    # Resolve scope. A half-specified range must never fall back to the whole
    # document; the resolver reports it through scope.error.
    scope = resolve_scope(doc.paragraphs, **(scope_config or {}))
    if getattr(scope, 'error', None):
        return _failed_edit_result(scope.error, output, replacements, scope=scope)

    # Check protected elements in scope
    protected = get_protected_elements_in_range(
        doc, scope.start_para_index, scope.end_para_index + 1
    )

    # Initialize manifest
    manifest = ChangeManifest(
        file_path,
        requested_scope=scope_config or "full document"
    )

    # Apply replacements
    results = []
    for rep in replacements:
        if not isinstance(rep, dict):
            results.append(_failed_change('', '', '替换项格式无效，已跳过'))
            manifest.add_change(
                change_type='replace_text',
                target='invalid',
                success=False,
                warnings=['替换项格式无效，已跳过'],
            )
            continue

        old_text = rep.get('old', '')
        new_text = rep.get('new', '')

        if not old_text:
            results.append(_failed_change(old_text, new_text, '替换源文本为空，已跳过'))
            manifest.add_change(
                change_type='replace_text',
                target='invalid',
                old_text=old_text,
                new_text=new_text,
                success=False,
                warnings=['替换源文本为空，已跳过'],
            )
            continue

        # Search within scope
        found = False
        for idx in scope.included_paragraphs:
            if idx >= len(doc.paragraphs):
                continue
            para = doc.paragraphs[idx]
            if old_text not in para.text:
                continue

            # Check complexity
            complexity = check_complex_paragraph(para)

            # The editor returns a dict; adapt it so cli.py keeps working with
            # both the old bool contract and the new run-aware contract.
            result = _coerce_edit_result(
                replace_text_in_paragraph(para, old_text, new_text, red=True)
            )
            result['paragraph_index'] = idx
            if result.get('refused_reason'):
                result['success'] = False
            if mode == 'text_only' and complexity['is_complex']:
                result['complexity_warning'] = (
                    f"Paragraph at index {idx} is complex "
                    f"({complexity['risk_level']} risk): "
                    f"{complexity['protected_nodes']}"
                )
            results.append(result)

            # Record in manifest; refused edits are failures, not changes.
            warnings = list(result.get('warnings') or [])
            if result.get('refused_reason'):
                warnings.append(result['refused_reason'])
            manifest.add_change(
                change_type='replace_text',
                target=f"paragraph {idx}",
                old_text=old_text,
                new_text=new_text,
                paragraph_index=idx,
                method=result.get('method'),
                success=result.get('success', False),
                warnings=warnings,
            )

            found = True
            break

        if not found:
            results.append(
                _failed_change(
                    old_text, new_text,
                    f"Text not found in scope: '{old_text[:50]}...'",
                )
            )
            manifest.add_change(
                change_type='replace_text',
                target='not found',
                old_text=old_text,
                new_text=new_text,
                success=False,
                warnings=[f"Text not found in scope"],
            )

    applied = sum(1 for r in results if r.get('success'))
    failed = max(0, total_replacements - applied)

    # Record preserved elements
    manifest.add_preserved(f"Chapters outside scope: paragraphs 0-{scope.start_para_index-1}")
    manifest.add_preserved(f"Chapters outside scope: paragraphs {scope.end_para_index+1}+")
    if protected:
        for p in protected:
            manifest.add_preserved(
                f"Complex paragraph at {p['paragraph_index']}: "
                f"{', '.join(p['protected_nodes'])}"
            )

    # Default academic presentation is a whole-document rewrite, so it only
    # runs in the explicit format_normalization mode. text_only/structural must
    # leave untouched paragraphs, table styles and equation alignment alone.
    if mode == 'format_normalization':
        default_formatting = _apply_default_academic_formatting(
            doc, include_unknown_tables=True
        )
        default_formatting['applied'] = True
    else:
        default_formatting = {'applied': False, 'reason': 'mode'}

    # Nothing was applied: never rewrite the package. Re-serialising a no-op
    # edit still changes the ZIP layout (timestamps, part order), which would
    # contradict the "nothing was changed" report the caller just received.
    if mode != 'format_normalization' and applied == 0:
        manifest.finalize()
        return {
            'success': False,
            'complete': total_replacements == 0,
            'applied': 0,
            'failed': failed,
            'changes': 0,
            'total_replacements': total_replacements,
            'output': output,
            'saved': False,
            'backup_path': None,
            'restored_parts': [],
            'error': None,
            'scope': _scope_payload(scope),
            'protected_elements': len(protected),
            'default_formatting': default_formatting,
            'package_validation': None,
            'package_integrity': None,
            'manifest_summary': manifest.summary(),
        }

    # Save to a temporary package first: the target file is only replaced after
    # every validation passes, so a failed edit can never destroy the original.
    preimage_fd, preimage_path = tempfile.mkstemp(
        suffix='.docx', prefix='wg_preimage_'
    )
    os.close(preimage_fd)
    shutil.copy2(file_path, preimage_path)
    tmp_fd, tmp_path = tempfile.mkstemp(suffix='.docx', prefix='wg_save_')
    os.close(tmp_fd)

    try:
        try:
            doc.save(tmp_path)
        except Exception as exc:
            return _failed_edit_result(
                f"保存文档失败：{exc}", output, replacements,
                scope=scope, default_formatting=default_formatting, applied=applied,
            )

        package_validation = validate_docx_package(tmp_path).to_dict()
        # Only the main document XML and volatile core metadata may change.
        allowed_parts = {'word/document.xml', 'docProps/core.xml'}
        package_integrity = compare_package_parts(
            preimage_path, tmp_path, allowed_parts
        )

        # python-docx drops unreferenced package parts (customXml, ...) on save.
        # Copy them back from the original package before judging the result.
        restored_parts = []
        if package_integrity.get('removed_parts'):
            try:
                restored_parts = _restore_missing_parts(
                    tmp_path, preimage_path, package_integrity['removed_parts']
                )
            except OSError as exc:
                return _failed_edit_result(
                    f"恢复缺失的包部件失败：{exc}", output, replacements,
                    scope=scope, default_formatting=default_formatting, applied=applied,
                )
            if restored_parts:
                package_validation = validate_docx_package(tmp_path).to_dict()
                package_integrity = compare_package_parts(
                    preimage_path, tmp_path, allowed_parts
                )

        fatal_error = None
        if not package_validation.get('valid'):
            fatal_error = _validation_error_message(package_validation)
        elif not package_integrity.get('intact'):
            fatal_error = _integrity_error_message(package_integrity)

        if fatal_error:
            result = _failed_edit_result(
                fatal_error, output, replacements,
                scope=scope, default_formatting=default_formatting, applied=applied,
            )
            result.update({
                'package_validation': package_validation,
                'package_integrity': package_integrity,
                'restored_parts': list(restored_parts),
                'protected_elements': len(protected),
                'manifest_summary': manifest.summary(),
            })
            return result

        # Back up the file that is about to be overwritten.
        backup_path = None
        if backup and os.path.exists(output):
            backup_path = output + '.bak'
            try:
                shutil.copy2(output, backup_path)
            except OSError as exc:
                result = _failed_edit_result(
                    f"创建备份失败：{exc}", output, replacements,
                    scope=scope, default_formatting=default_formatting, applied=applied,
                )
                result.update({
                    'package_validation': package_validation,
                    'package_integrity': package_integrity,
                    'restored_parts': list(restored_parts),
                    'protected_elements': len(protected),
                })
                return result

        # Commit the validated package.
        try:
            _commit_file(tmp_path, output)
        except OSError as exc:
            result = _failed_edit_result(
                f"写入目标文件失败：{exc}", output, replacements,
                scope=scope, default_formatting=default_formatting, applied=applied,
            )
            result.update({
                'backup_path': backup_path,
                'package_validation': package_validation,
                'package_integrity': package_integrity,
                'restored_parts': list(restored_parts),
                'protected_elements': len(protected),
            })
            return result

        manifest.finalize()
        complete = applied == total_replacements
        success = (
            package_validation.get('valid')
            and package_integrity.get('intact')
            and (total_replacements == 0 or applied >= 1)
        )
        return {
            'success': bool(success),
            'complete': complete,
            'applied': applied,
            'failed': failed,
            'changes': applied,
            'total_replacements': total_replacements,
            'output': output,
            'saved': True,
            'backup_path': backup_path,
            'restored_parts': list(restored_parts),
            'error': None,
            'scope': _scope_payload(scope),
            'protected_elements': len(protected),
            'default_formatting': default_formatting,
            'package_validation': package_validation,
            'package_integrity': package_integrity,
            'manifest_summary': manifest.summary(),
        }
    finally:
        _safe_unlink(preimage_path)
        _safe_unlink(tmp_path)


# ═══════════════════════════════════════════════════════════════════════════
# Tool 3: writing_word_audit
# ═══════════════════════════════════════════════════════════════════════════

def writing_word_audit(file_path):
    """
    Extract normalized text from a DOCX and check for writing issues.

    Checks:
    - Revision residue patterns
    - AI-style language
    - Scientific notation issues
    - Unit formatting

    Args:
        file_path: path to the .docx file

    Returns:
        dict with extracted text and audit findings
    """
    if not os.path.exists(file_path):
        return {'error': f"File not found: {file_path}"}

    from docx import Document
    doc = Document(file_path)

    # Extract normalized text with source mapping
    paragraphs = []
    for i, para in enumerate(doc.paragraphs):
        if para.text.strip():
            paragraphs.append({
                'index': i,
                'text': para.text,
                'style': para.style.style_id if para.style else None,
            })

    # Basic writing checks
    issues = []

    # Revision residue patterns (for manuscript profile)
    revision_residue_patterns = [
        'in the original formulation',
        'we revised',
        'the reviewer suggested',
        'in response to the reviewer',
        'the revised model',
        'the previous version',
        'as requested',
        'we have modified',
        'we changed',
    ]

    basename = os.path.basename(file_path).lower()
    is_manuscript = not any(kw in basename for kw in ['rebuttal', 'response', 'reply'])

    for p in paragraphs:
        text_lower = p['text'].lower()
        for pattern in revision_residue_patterns:
            if pattern in text_lower:
                if is_manuscript:
                    issues.append({
                        'type': 'revision_residue',
                        'paragraph': p['index'],
                        'text': p['text'][:100],
                        'pattern': pattern,
                        'severity': 'high',
                    })

    # AI-style patterns
    ai_patterns = [
        ('delve', 'high'),
        ('tapestry', 'high'),
        ('multifaceted', 'medium'),
        ('paradigm', 'medium'),
        ('landscape', 'medium'),
        ('crucial', 'low'),
        ('furthermore', 'low'),
        ('moreover', 'low'),
        ('notably', 'low'),
    ]

    for p in paragraphs:
        text_lower = p['text'].lower()
        for pattern, severity in ai_patterns:
            if pattern in text_lower:
                issues.append({
                    'type': 'ai_style',
                    'paragraph': p['index'],
                    'text': p['text'][:100],
                    'pattern': pattern,
                    'severity': severity,
                })

    # Unit formatting issues
    unit_patterns = [
        ('min-1', 'Should be min⁻¹ or min^-1'),
        ('m-3', 'Should be m⁻³ or m^-3'),
        ('s-1', 'Should be s⁻¹ or s^-1'),
        ('kg m-3', 'Should be kg·m⁻³'),
    ]

    for p in paragraphs:
        for pattern, suggestion in unit_patterns:
            if pattern in p['text']:
                issues.append({
                    'type': 'unit_format',
                    'paragraph': p['index'],
                    'text': p['text'][:100],
                    'pattern': pattern,
                    'suggestion': suggestion,
                    'severity': 'medium',
                })

    return {
        'file': os.path.basename(file_path),
        'profile': 'manuscript' if is_manuscript else 'rebuttal',
        'total_paragraphs': len(paragraphs),
        'issues_found': len(issues),
        'issues': issues,
        'text_preview': [p['text'][:80] for p in paragraphs[:10]],
    }


# ═══════════════════════════════════════════════════════════════════════════
# Tool 4: writing_word_scope_check
# ═══════════════════════════════════════════════════════════════════════════

def writing_word_scope_check(file_before, file_after, scope_config=None):
    """
    Verify that editing did not modify content outside the requested scope.

    Args:
        file_before: path to the original .docx file
        file_after: path to the edited .docx file
        scope_config: dict with scope parameters

    Returns:
        dict with integrity check results
    """
    from docx import Document

    if not os.path.exists(file_before):
        return {'error': f"File not found: {file_before}"}
    if not os.path.exists(file_after):
        return {'error': f"File not found: {file_after}"}

    config, config_error = _normalize_scope_config(scope_config)
    if config_error:
        return {
            'error': config_error,
            'scope_intact': False,
            'requested_scope': str(scope_config),
            'unchanged_regions': [],
            'unexpected_changes': [],
            'warnings': [],
        }

    doc_before = Document(file_before)
    doc_after = Document(file_after)

    scope = resolve_scope(doc_before.paragraphs, **(config or {}))
    if getattr(scope, 'error', None):
        # The scope itself is unresolvable: there is nothing meaningful to
        # compare, and reporting "intact" would be a false pass.
        return {
            'error': scope.error,
            'scope_intact': False,
            'requested_scope': str(config or "full document"),
            'unchanged_regions': [],
            'unexpected_changes': [],
            'warnings': list(scope.warnings),
        }

    result = check_scope_integrity(
        doc_before, doc_after, scope,
        scope_description=str(config or "full document")
    )

    payload = {
        'scope_intact': result.scope_intact,
        'requested_scope': result.requested_scope,
        'unchanged_regions': result.unchanged_regions,
        'unexpected_changes': result.unexpected_changes,
        'warnings': result.warnings,
    }
    # The upgraded integrity checker also reports structural counts.
    counts = getattr(result, 'counts', None)
    if counts is not None:
        payload['counts'] = _as_jsonable(counts)
    return payload


# ═══════════════════════════════════════════════════════════════════════════
# Tool 5: writing_word_format_tables
# ═══════════════════════════════════════════════════════════════════════════

def writing_word_format_tables(file_path, output_path=None, baseline_path=None, include_unknown=True):
    """Safely convert scholarly data tables to three-line format.

    Layout/figure-container tables are skipped.  If a baseline manuscript is
    supplied, border weights are inherited from it when recognizable.
    """
    if not os.path.exists(file_path):
        return {'error': f"File not found: {file_path}"}
    if baseline_path and not os.path.exists(baseline_path):
        return {'error': f"Baseline file not found: {baseline_path}"}

    from docx import Document

    doc = Document(file_path)
    results = convert_tables_to_three_line(doc, baseline_path, include_unknown=include_unknown)
    save_path = output_path or file_path
    doc.save(save_path)
    validation = validate_docx_package(save_path).to_dict()

    return {
        'success': validation['valid'],
        'output': save_path,
        'tables_formatted': sum(1 for r in results if r.get('action') == 'formatted'),
        'tables_skipped': sum(1 for r in results if r.get('action') == 'skipped'),
        'baseline': baseline_path,
        'package_validation': validation,
        'details': results,
    }


def writing_word_format_equations(file_path, output_path=None):
    """Apply the default equation layout without changing equation content."""
    if not os.path.exists(file_path):
        return {'error': f"File not found: {file_path}"}

    from docx import Document
    doc = Document(file_path)
    results = format_equations(doc)
    save_path = output_path or file_path
    doc.save(save_path)
    validation = validate_docx_package(save_path).to_dict()

    return {
        'success': validation['valid'],
        'output': save_path,
        'equations_formatted_numbered': sum(1 for r in results if r.get('action') == 'formatted_numbered'),
        'equations_centered_unnumbered': sum(1 for r in results if r.get('action') == 'centered_unnumbered'),
        'equations_skipped_inline': sum(1 for r in results if r.get('action') == 'skipped_inline'),
        'package_validation': validation,
        'details': results,
    }


def writing_word_format_paragraphs(file_path, output_path=None):
    """Apply justified alignment to likely body-text paragraphs only."""
    if not os.path.exists(file_path):
        return {'error': f"File not found: {file_path}"}

    from docx import Document
    doc = Document(file_path)
    results = justify_body_paragraphs(doc)
    save_path = output_path or file_path
    doc.save(save_path)
    validation = validate_docx_package(save_path).to_dict()

    return {
        'success': validation['valid'],
        'output': save_path,
        'paragraphs_justified': sum(1 for r in results if r.get('action') == 'justified'),
        'paragraphs_skipped': sum(1 for r in results if r.get('action') == 'skipped'),
        'package_validation': validation,
        'details': results,
    }


def writing_word_format_defaults(file_path, output_path=None):
    """Apply default table, equation, and body-paragraph formatting rules."""
    if not os.path.exists(file_path):
        return {'error': f"File not found: {file_path}"}

    from docx import Document
    doc = Document(file_path)
    formatting = _apply_default_academic_formatting(doc, include_unknown_tables=True)
    save_path = output_path or file_path
    doc.save(save_path)
    validation = validate_docx_package(save_path).to_dict()
    return {
        'success': validation['valid'],
        'output': save_path,
        'default_formatting': formatting,
        'package_validation': validation,
    }


def writing_word_package_validate(file_path):
    if not os.path.exists(file_path):
        return {'error': f"File not found: {file_path}"}
    return validate_docx_package(file_path).to_dict()


def writing_word_fingerprint(file_path):
    if not os.path.exists(file_path):
        return {'error': f"File not found: {file_path}"}
    return build_baseline_fingerprint(file_path).to_dict()


def writing_word_equation_audit(file_path, baseline_path=None):
    if not os.path.exists(file_path):
        return {'error': f"File not found: {file_path}"}
    if baseline_path and not os.path.exists(baseline_path):
        return {'error': f"Baseline file not found: {baseline_path}"}
    return audit_equations(file_path, baseline_path)


def writing_word_extract(file_path):
    """
    Extract paragraph text from a DOCX as structured JSON.

    Reuses the same python-docx extraction as writing_word_audit: paragraphs in
    document order, keeping only those whose stripped text is non-empty.

    Args:
        file_path: path to the .docx file

    Returns:
        dict with the absolute file path, the paragraph records and the full
        text (paragraphs joined by newlines)
    """
    if not os.path.exists(file_path):
        return {'error': f"File not found: {file_path}"}

    from docx import Document
    doc = Document(file_path)

    paragraphs = []
    for i, para in enumerate(doc.paragraphs):
        if para.text.strip():
            paragraphs.append({
                'index': i,
                'text': para.text,
                'style': para.style.style_id if para.style else None,
            })

    return {
        'file': os.path.abspath(file_path),
        'paragraphs': paragraphs,
        'text': '\n'.join(p['text'] for p in paragraphs),
    }


# ═══════════════════════════════════════════════════════════════════════════
# CLI Interface
# ═══════════════════════════════════════════════════════════════════════════

def _require_args(usage, minimum):
    """缺少必需参数时向 stderr 输出用法并退出 1。"""
    if len(sys.argv) < minimum:
        print(f"Usage: {usage}", file=sys.stderr)
        sys.exit(1)


def _emit_result(result):
    """打印 JSON 报告；仅在命令报告致命 error 时以退出码 2 结束。

    部分替换失败（success=False 但 error 为空）必须退出 0，否则宿主
    callWordGuardAt 会抛异常，模型就看不到完整报告了。
    """
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if isinstance(result, dict) and result.get('error'):
        sys.exit(2)


def main():
    """CLI entry point."""
    if len(sys.argv) < 2:
        print("Usage: python -m word_guard.cli <command> [args]")
        print("")
        print("Commands:")
        print("  scan <file.docx>                          - Structural scan")
        print("  audit <file.docx>                         - Writing audit")
        print("  extract <file.docx>                       - Extract paragraph text as JSON")
        print("  edit <file.docx> <replacements.json>      - Edit document")
        print("  scope-check <before.docx> <after.docx>    - Check scope integrity")
        print("  format-tables <file.docx> [output.docx] [baseline.docx] - Three-line tables + centered cells")
        print("  format-equations <file.docx> [output.docx] - Equation centered + number at right margin")
        print("  format-paragraphs <file.docx> [output.docx] - Justify likely body-text paragraphs")
        print("  format-defaults <file.docx> [output.docx]  - Apply table + equation + paragraph defaults")
        print("  package-validate <file.docx>              - Validate OOXML package")
        print("  fingerprint <file.docx>                   - Baseline formatting fingerprint")
        print("  equation-audit <file.docx> [baseline.docx]- Audit native equations")
        sys.exit(1)

    command = sys.argv[1]

    if command == 'scan':
        _require_args('scan <file.docx>', 3)
        _emit_result(writing_word_scan(sys.argv[2]))

    elif command == 'audit':
        _require_args('audit <file.docx>', 3)
        _emit_result(writing_word_audit(sys.argv[2]))

    elif command == 'extract':
        _require_args('extract <file.docx>', 3)
        # Emit UTF-8 JSON regardless of the console code page. The host reads
        # this stdout as UTF-8; without this, CJK text would be encoded with the
        # Windows locale codec (cp936/cp1252) and arrive mojibaked.
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass
        _emit_result(writing_word_extract(sys.argv[2]))

    elif command == 'edit':
        _require_args(
            'edit <file.docx> <replacements.json> [output.docx] [mode] [scope.json]',
            4,
        )
        try:
            with open(sys.argv[3], 'r', encoding='utf-8') as f:
                replacements = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            _emit_result({'error': f"无法读取替换文件：{exc}"})
        output_file = None
        if len(sys.argv) > 4 and sys.argv[4] not in ('null', ''):
            output_file = sys.argv[4]
        mode = sys.argv[5] if len(sys.argv) > 5 else 'text_only'
        scope_config = None
        if len(sys.argv) > 6 and sys.argv[6] not in ('null', ''):
            try:
                scope_config = json.loads(sys.argv[6])
            except json.JSONDecodeError as exc:
                _emit_result({'error': f"范围参数不是有效 JSON：{exc}"})
        _emit_result(writing_word_edit(
            sys.argv[2], replacements, scope_config, mode, output_file
        ))

    elif command == 'scope-check':
        _require_args('scope-check <before.docx> <after.docx> [scope.json]', 4)
        scope_config = None
        if len(sys.argv) > 4 and sys.argv[4] not in ('null', ''):
            try:
                scope_config = json.loads(sys.argv[4])
            except json.JSONDecodeError as exc:
                _emit_result({'error': f"范围参数不是有效 JSON：{exc}"})
        _emit_result(writing_word_scope_check(sys.argv[2], sys.argv[3], scope_config))

    elif command == 'format-tables':
        _require_args('format-tables <file.docx> [output.docx] [baseline.docx]', 3)
        input_file = sys.argv[2]
        output_file = sys.argv[3] if len(sys.argv) > 3 else input_file
        baseline_file = sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] not in ('null', '') else None
        _emit_result(writing_word_format_tables(input_file, output_file, baseline_file))

    elif command == 'format-equations':
        _require_args('format-equations <file.docx> [output.docx]', 3)
        input_file = sys.argv[2]
        output_file = sys.argv[3] if len(sys.argv) > 3 else input_file
        _emit_result(writing_word_format_equations(input_file, output_file))

    elif command == 'format-paragraphs':
        _require_args('format-paragraphs <file.docx> [output.docx]', 3)
        input_file = sys.argv[2]
        output_file = sys.argv[3] if len(sys.argv) > 3 else input_file
        _emit_result(writing_word_format_paragraphs(input_file, output_file))

    elif command == 'format-defaults':
        _require_args('format-defaults <file.docx> [output.docx]', 3)
        input_file = sys.argv[2]
        output_file = sys.argv[3] if len(sys.argv) > 3 else input_file
        _emit_result(writing_word_format_defaults(input_file, output_file))

    elif command == 'package-validate':
        _require_args('package-validate <file.docx>', 3)
        _emit_result(writing_word_package_validate(sys.argv[2]))

    elif command == 'fingerprint':
        _require_args('fingerprint <file.docx>', 3)
        _emit_result(writing_word_fingerprint(sys.argv[2]))

    elif command == 'equation-audit':
        _require_args('equation-audit <file.docx> [baseline.docx]', 3)
        baseline_file = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] not in ('null', '') else None
        _emit_result(writing_word_equation_audit(sys.argv[2], baseline_file))

    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
