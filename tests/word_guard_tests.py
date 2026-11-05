#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v2.4.0 缺陷修复回归测试（Python 侧）。

覆盖 src/word_guard/ 下的 10 余项缺陷修复（P1-1/P1-2/P1-3/P1-4/P1-5/P1-6/
P2-9/P2-10/P2-11/P2-12）。自包含、可独立运行：

    PYTHONDONTWRITEBYTECODE=1 PYTHONIOENCODING=utf-8 python -B tests/word_guard_tests.py

最后一行输出 JSON 汇总：
    {"passed": N, "failed": M, "failures": [{"name": ..., "detail": ...}]}
"""

from __future__ import annotations

import dataclasses
import io
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import traceback
import zlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / 'src'
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

RESULT = {'passed': 0, 'failed': 0, 'failures': []}


def check(name, cond, detail=''):
    """Record one assertion; never raises."""
    if cond:
        RESULT['passed'] += 1
        return True
    RESULT['failed'] += 1
    RESULT['failures'].append({'name': name, 'detail': str(detail)[:1200]})
    return False


def emit_and_exit(code=0):
    print(json.dumps(RESULT, ensure_ascii=False))
    sys.exit(code)


try:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import parse_xml
    from docx.oxml.ns import qn
    from docx.shared import Inches

    from word_guard import (
        cli,
        editor,
        equation_format,
        integrity,
        package_guard,
        scanner,
        scope as scope_mod,
    )
except Exception as exc:  # pragma: no cover - 缺依赖时必须 SKIP，不能让 CI 变红
    reason = (
        'python-docx not installed'
        if 'docx' in str(exc).lower()
        else repr(exc)
    )
    print(json.dumps(
        {'skipped': True, 'reason': reason, 'passed': 0, 'failed': 0, 'failures': []},
        ensure_ascii=False,
    ))
    sys.exit(0)

W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
M_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/math'

OMATH_XML = (
    f'<m:oMath xmlns:m="{M_NS}"><m:r><m:t>x</m:t></m:r></m:oMath>'
)
OMATHPARA_XML = (
    f'<m:oMathPara xmlns:m="{M_NS}">'
    f'<m:oMath><m:r><m:t>y</m:t></m:r></m:oMath></m:oMathPara>'
)
HYPERLINK_XML = (
    f'<w:hyperlink xmlns:w="{W_NS}" xmlns:r="{R_NS}" r:id="rIdMISSING">'
    f'<w:r><w:t>linked</w:t></w:r></w:hyperlink>'
)


def one_pixel_png():
    """构造一个合法的 1x1 PNG，避免依赖 base64 常量是否正确。"""
    def chunk(tag, payload):
        return (
            struct.pack('>I', len(payload))
            + tag
            + payload
            + struct.pack('>I', zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    ihdr = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(b'\x00\xff\xff\xff', 9)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) + chunk(b'IDAT', idat) + chunk(b'IEND', b'')


PNG_1X1 = one_pixel_png()


# ─── fixture helpers ────────────────────────────────────────────────────────

def new_doc(*texts):
    doc = Document()
    for text in texts:
        doc.add_paragraph(text)
    return doc


def add_picture_run(paragraph):
    run = paragraph.add_run()
    run.add_picture(io.BytesIO(PNG_1X1), width=Inches(0.2))
    return run


def count_drawings(paragraph):
    return len(paragraph._p.findall('.//' + qn('w:drawing')))


def count_runs(paragraph):
    return len(paragraph._p.findall(qn('w:r')))


def doc_with_header(header_text):
    doc = Document()
    doc.add_paragraph('Body paragraph')
    header = doc.sections[0].header
    header.is_linked_to_previous = False
    header.paragraphs[0].text = header_text
    return doc


def as_dict(obj):
    if dataclasses.is_dataclass(obj):
        return dataclasses.asdict(obj)
    return dict(obj)


def kinds_of(result):
    return [c.get('kind') for c in result.unexpected_changes]


def run_cli(args):
    env = dict(os.environ)
    env['PYTHONPATH'] = str(SRC_DIR)
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['PYTHONIOENCODING'] = 'utf-8'
    return subprocess.run(
        [sys.executable, '-B', '-m', 'word_guard.cli'] + [str(a) for a in args],
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
        env=env,
        timeout=180,
    )


# ══════════════════════════════════════════════════════════════════════════
# 测试主体
# ══════════════════════════════════════════════════════════════════════════

def test_p1_1_editor_protected_nodes(work):
    # 返回契约
    doc = new_doc('The quick brown fox')
    para = doc.paragraphs[0]
    res = editor.replace_text_in_paragraph(para, 'quick', 'slow')
    check(
        'P1-1 返回值含 6 个契约字段',
        set(res.keys()) == {
            'success', 'method', 'warnings', 'preserved_nodes',
            'refused_reason', 'error',
        },
        sorted(res.keys()),
    )
    check(
        'P1-1 单段替换成功且 method=text_node_split',
        res['success'] is True and res['method'] == 'text_node_split',
        res,
    )
    check('P1-1 替换结果文本正确', para.text == 'The slow brown fox', para.text)

    # 跨度覆盖 drawing → 拒绝且内容不变
    doc = Document()
    para = doc.add_paragraph()
    para.add_run('alpha')
    add_picture_run(para)
    para.add_run(' omega')
    before_text = para.text
    before_drawings = count_drawings(para)
    res = editor.replace_text_in_paragraph(para, 'alpha omega', 'X')
    check(
        'P1-1 跨度覆盖 drawing 时拒绝',
        res['success'] is False and res['refused_reason'] == 'protected_node_in_span',
        res,
    )
    check(
        'P1-1 拒绝后段落内容与 drawing 不变',
        para.text == before_text and count_drawings(para) == before_drawings,
        (para.text, count_drawings(para)),
    )

    # 绝不删除 w:r
    doc = Document()
    para = doc.add_paragraph()
    para.add_run('abc')
    para.add_run('DEF')
    runs_before = count_runs(para)
    res = editor.replace_text_in_paragraph(para, 'cD', 'X')
    check(
        'P1-1 跨 run 替换不删除任何 w:r',
        res['success'] is True and count_runs(para) >= runs_before,
        (runs_before, count_runs(para), res),
    )
    check(
        'P1-1 跨 run 合并 method=multi_node_merge',
        res['method'] == 'multi_node_merge',
        res['method'],
    )

    # 跨 run 替换不得减少同段 drawing
    doc = Document()
    para = doc.add_paragraph()
    para.add_run('foo')
    para.add_run('bar')
    add_picture_run(para)
    drawings_before = count_drawings(para)
    res = editor.replace_text_in_paragraph(para, 'oob', 'X')
    check(
        'P1-1 跨 run 替换保留 drawing',
        res['success'] is True
        and count_drawings(para) == drawings_before
        and para.text == 'fXar',
        (res, para.text, count_drawings(para)),
    )

    # 整段替换拒绝复杂段落
    doc = Document()
    para = doc.add_paragraph('text')
    add_picture_run(para)
    res = editor.replace_entire_paragraph(para, 'new text')
    check(
        'P1-1 整段替换拒绝受保护段落',
        res['success'] is False
        and res['refused_reason'] == 'protected_node_paragraph',
        res,
    )

    # 文本不存在
    doc = new_doc('hello world')
    res = editor.replace_text_in_paragraph(doc.paragraphs[0], 'zzz', 'y')
    check(
        'P1-1 未命中返回 not_found',
        res['success'] is False
        and res['refused_reason'] == 'not_found'
        and res['method'] is None,
        res,
    )


def test_p1_5_multi_text_nodes(work):
    # 单 run 含两个 w:t：abc + DEF，替换 bcD → aXEF（旧实现 aDEFXEF）
    doc = Document()
    para = doc.add_paragraph()
    run = para.add_run('abc')
    run._r.append(
        parse_xml(f'<w:t xmlns:w="{W_NS}" xml:space="preserve">DEF</w:t>')
    )
    check('P1-5 前置条件：段落文本为 abcDEF', para.text == 'abcDEF', para.text)
    res = editor.replace_text_in_paragraph(para, 'bcD', 'X')
    check(
        'P1-5 单 run 多 w:t 替换得 aXEF',
        res['success'] is True and para.text == 'aXEF',
        (res, para.text),
    )

    # 单 run 含 w:tab：ab + tab + cd，替换 cd → ab\tX（旧实现 ab\t\tcdX）
    doc = Document()
    para = doc.add_paragraph()
    run = para.add_run('ab')
    run._r.append(parse_xml(f'<w:tab xmlns:w="{W_NS}"/>'))
    run._r.append(
        parse_xml(f'<w:t xmlns:w="{W_NS}" xml:space="preserve">cd</w:t>')
    )
    check('P1-5 前置条件：段落文本为 ab\\tcd', para.text == 'ab\tcd', repr(para.text))
    res = editor.replace_text_in_paragraph(para, 'cd', 'X')
    check(
        'P1-5 单 run 含 w:tab 替换得 ab\\tX',
        res['success'] is True and para.text == 'ab\tX',
        (res, repr(para.text)),
    )


def test_p1_6_integrity(work):
    # 干净编辑
    before = new_doc('Alpha', 'Bravo', 'Charlie')
    after = new_doc('Alpha revised', 'Bravo', 'Charlie')
    sc = scope_mod.resolve_scope(before.paragraphs, start_index=0, end_index=0)
    res = integrity.check_scope_integrity(before, after, sc)
    check(
        'P1-6 干净编辑 scope_intact=True',
        res.scope_intact is True and res.unexpected_changes == [],
        as_dict(res),
    )
    check(
        'P1-6 counts 字段完整',
        set(res.counts.keys()) == {
            'paragraphs_before', 'paragraphs_after',
            'tables_before', 'tables_after',
            'headers_footers_before', 'headers_footers_after',
        },
        res.counts,
    )
    check(
        'P1-6 干净编辑 unchanged_regions 非空且含声明',
        bool(res.unchanged_regions)
        and 'All out-of-scope content is unchanged' in res.unchanged_regions,
        res.unchanged_regions,
    )

    # 尾段被删（旧实现取 min 长度掩盖）
    before = new_doc('Alpha', 'Bravo', 'Charlie', 'Delta')
    after = new_doc('Alpha', 'Bravo', 'Charlie')
    sc = scope_mod.resolve_scope(before.paragraphs, start_index=0, end_index=0)
    res = integrity.check_scope_integrity(before, after, sc)
    check(
        'P1-6 尾段被删检出 paragraph_count',
        res.scope_intact is False and 'paragraph_count' in kinds_of(res),
        (kinds_of(res), res.counts),
    )
    check(
        'P1-6 异常时不声明范围外未变',
        'All out-of-scope content is unchanged'
        not in json.dumps(as_dict(res), ensure_ascii=False),
        as_dict(res),
    )

    # 范围外段落对齐变化
    before = new_doc('Alpha', 'Bravo', 'Charlie')
    after = new_doc('Alpha', 'Bravo', 'Charlie')
    after.paragraphs[2].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sc = scope_mod.resolve_scope(before.paragraphs, start_index=0, end_index=0)
    res = integrity.check_scope_integrity(before, after, sc)
    check(
        'P1-6 范围外对齐变化检出 paragraph_format',
        res.scope_intact is False and 'paragraph_format' in kinds_of(res),
        kinds_of(res),
    )

    # 表格单元格文本变化
    before = Document()
    before.add_paragraph('Alpha')
    table = before.add_table(rows=1, cols=2)
    table.cell(0, 0).text = 'CellA'
    table.cell(0, 1).text = 'CellB'
    after = Document()
    after.add_paragraph('Alpha')
    table = after.add_table(rows=1, cols=2)
    table.cell(0, 0).text = 'CellA'
    table.cell(0, 1).text = 'CellB changed'
    sc = scope_mod.resolve_scope(before.paragraphs, start_index=0, end_index=0)
    res = integrity.check_scope_integrity(before, after, sc)
    check(
        'P1-6 表格单元格变化检出 table',
        res.scope_intact is False and 'table' in kinds_of(res),
        kinds_of(res),
    )

    # 页眉文本变化
    before = doc_with_header('Header original')
    after = doc_with_header('Header changed')
    sc = scope_mod.resolve_scope(before.paragraphs, start_index=0, end_index=0)
    res = integrity.check_scope_integrity(before, after, sc)
    check(
        'P1-6 页眉变化检出 header_footer',
        res.scope_intact is False and 'header_footer' in kinds_of(res),
        kinds_of(res),
    )


def test_p1_2_text_only_mode(work):
    src = os.path.join(work, 'p1_2_source.docx')
    doc = Document()
    doc.add_paragraph(
        'This is a sufficiently long body paragraph that should stay untouched '
        'outside the requested scope.'
    )
    doc.add_paragraph(
        'Body two contains the target token and is also long enough to be '
        'treated as running prose by the formatter.'
    )
    table = doc.add_table(rows=2, cols=2, style='Table Grid')
    table.cell(0, 0).text = 'A'
    table.cell(1, 1).text = 'B'
    doc.save(src)

    out_text = os.path.join(work, 'p1_2_text_only.docx')
    res = cli.writing_word_edit(
        src,
        [{'old': 'Body two', 'new': 'Body two revised'}],
        {'startParagraph': 1, 'endParagraph': 1},
        'text_only',
        out_text,
    )
    check('P1-2 text_only 编辑成功', res.get('success') is True, res.get('error'))
    edited = Document(out_text)
    check(
        'P1-2 text_only 范围外段落保持未格式化',
        edited.paragraphs[0].paragraph_format.alignment is None,
        edited.paragraphs[0].paragraph_format.alignment,
    )
    check(
        'P1-2 text_only 表格样式保持 Table Grid',
        edited.tables[0].style is not None
        and edited.tables[0].style.name == 'Table Grid',
        edited.tables[0].style.name if edited.tables[0].style else None,
    )
    check(
        'P1-2 text_only default_formatting 标记未应用',
        res.get('default_formatting') == {'applied': False, 'reason': 'mode'},
        res.get('default_formatting'),
    )

    out_fmt = os.path.join(work, 'p1_2_format.docx')
    res2 = cli.writing_word_edit(
        src,
        [{'old': 'Body two', 'new': 'Body two revised'}],
        {'startParagraph': 1, 'endParagraph': 1},
        'format_normalization',
        out_fmt,
    )
    check(
        'P1-2 format_normalization 标记 applied=True',
        isinstance(res2.get('default_formatting'), dict)
        and res2['default_formatting'].get('applied') is True,
        res2.get('default_formatting'),
    )
    formatted = Document(out_fmt)
    check(
        'P1-2 format_normalization 真的格式化了正文',
        formatted.paragraphs[0].paragraph_format.alignment
        == WD_ALIGN_PARAGRAPH.JUSTIFY,
        formatted.paragraphs[0].paragraph_format.alignment,
    )


def test_p1_3_safe_write(work):
    # 覆盖自身成功 → 生成 .bak
    ok_path = os.path.join(work, 'p1_3_ok.docx')
    new_doc('Alpha beta').save(ok_path)
    original_bytes = Path(ok_path).read_bytes()
    res = cli.writing_word_edit(
        ok_path, [{'old': 'Alpha', 'new': 'Gamma'}]
    )
    backup_path = ok_path + '.bak'
    check('P1-3 覆盖自身编辑成功', res.get('success') is True, res.get('error'))
    check(
        'P1-3 成功时 saved=True 且 backup_path 非空',
        res.get('saved') is True and bool(res.get('backup_path')),
        (res.get('saved'), res.get('backup_path')),
    )
    check(
        'P1-3 生成 <file>.bak 且内容为原文件',
        os.path.exists(backup_path)
        and Path(backup_path).read_bytes() == original_bytes,
        backup_path,
    )
    check(
        'P1-3 目标文件被更新',
        Path(ok_path).read_bytes() != original_bytes
        and 'Gamma' in Document(ok_path).paragraphs[0].text,
        Document(ok_path).paragraphs[0].text,
    )

    # 校验失败（悬空 r:id）→ 原文件逐字节不变
    bad_path = os.path.join(work, 'p1_3_dangling.docx')
    doc = Document()
    para = doc.add_paragraph()
    para.add_run('ReplaceMe token')
    para._p.append(parse_xml(HYPERLINK_XML))
    doc.save(bad_path)
    bad_bytes = Path(bad_path).read_bytes()
    res = cli.writing_word_edit(
        bad_path, [{'old': 'ReplaceMe', 'new': 'Changed'}]
    )
    check(
        'P1-3 校验失败时 success/saved 为 False 且 error 非空',
        res.get('success') is False
        and res.get('saved') is False
        and bool(res.get('error')),
        {k: res.get(k) for k in ('success', 'saved', 'error')},
    )
    check(
        'P1-3 校验失败时原文件逐字节不变',
        Path(bad_path).read_bytes() == bad_bytes,
        len(Path(bad_path).read_bytes()),
    )

    # 零替换 → 不写文件、字段符合契约
    zero_path = os.path.join(work, 'p1_3_zero.docx')
    new_doc('Only text').save(zero_path)
    zero_bytes = Path(zero_path).read_bytes()
    res = cli.writing_word_edit(
        zero_path, [{'old': 'ABSENT_TOKEN', 'new': 'X'}]
    )
    check(
        'P1-3 零替换字段契约',
        res.get('success') is False
        and res.get('changes') == 0
        and res.get('applied') == 0
        and res.get('failed') == 1
        and res.get('complete') is False
        and res.get('saved') is False,
        {k: res.get(k) for k in
         ('success', 'changes', 'applied', 'failed', 'complete', 'saved')},
    )
    check(
        'P1-3 零替换目标文件字节不变且不生成备份',
        Path(zero_path).read_bytes() == zero_bytes
        and not os.path.exists(zero_path + '.bak'),
        None,
    )


def test_p1_4_scope_validation(work):
    doc = new_doc('Alpha', 'Bravo', 'Charlie')

    sc = scope_mod.resolve_scope(doc.paragraphs, start_index=1)
    check(
        'P1-4 只给 start_index 报错且不返回段落',
        bool(sc.error) and sc.included_paragraphs == [],
        (sc.error, sc.included_paragraphs),
    )

    sc = scope_mod.resolve_scope(doc.paragraphs, start_heading='Heading 1')
    check(
        'P1-4 只给 start_heading 报错',
        bool(sc.error) and sc.included_paragraphs == [],
        (sc.error, sc.included_paragraphs),
    )

    sc = scope_mod.resolve_scope(doc.paragraphs, start_index=2, end_index=1)
    check(
        'P1-4 start_index 大于 end_index 报错',
        bool(sc.error) and sc.included_paragraphs == [],
        (sc.error, sc.included_paragraphs),
    )

    sc = scope_mod.resolve_scope(doc.paragraphs, heading='不存在的标题')
    check(
        'P1-4 heading 找不到报错',
        bool(sc.error) and sc.included_paragraphs == [],
        (sc.error, sc.included_paragraphs),
    )

    sc = scope_mod.resolve_scope(doc.paragraphs)
    check(
        'P1-4 无任何范围参数返回全篇且 error 为 None',
        sc.error is None and list(sc.included_paragraphs) == [0, 1, 2],
        (sc.error, list(sc.included_paragraphs)),
    )

    # CLI：只给 startParagraph → 退出码 2 且文件不被修改
    cli_doc = os.path.join(work, 'p1_4_cli.docx')
    new_doc('Alpha', 'Bravo').save(cli_doc)
    cli_bytes = Path(cli_doc).read_bytes()
    repl = os.path.join(work, 'p1_4_repl.json')
    with open(repl, 'w', encoding='utf-8') as fh:
        json.dump([{'old': 'Alpha', 'new': 'Omega'}], fh, ensure_ascii=False)
    proc = run_cli([
        'edit', cli_doc, repl, 'null', 'text_only',
        json.dumps({'startParagraph': 1}),
    ])
    try:
        parsed = json.loads(proc.stdout)
    except Exception:
        parsed = {}
    check(
        'P1-4 CLI 半范围参数退出码为 2',
        proc.returncode == 2,
        (proc.returncode, (proc.stderr or '')[-400:]),
    )
    check(
        'P1-4 CLI 半范围参数不改文件且返回 error',
        Path(cli_doc).read_bytes() == cli_bytes
        and parsed.get('success') is False
        and bool(parsed.get('error')),
        parsed.get('error'),
    )


def test_p2_9_package_guard(work):
    clean = os.path.join(work, 'p2_9_clean.docx')
    new_doc('clean document').save(clean)
    clean_result = package_guard.validate_docx_package(clean)
    check(
        'P2-9 干净文档 valid=True',
        clean_result.valid is True and not clean_result.errors,
        clean_result.errors,
    )

    dangling = os.path.join(work, 'p2_9_dangling.docx')
    doc = Document()
    para = doc.add_paragraph('body text')
    para._p.append(parse_xml(HYPERLINK_XML))
    doc.save(dangling)
    bad_result = package_guard.validate_docx_package(dangling)
    check(
        'P2-9 悬空 r:id 判为无效并提到 rIdMISSING',
        bad_result.valid is False
        and any('rIdMISSING' in str(e) for e in bad_result.errors),
        bad_result.errors,
    )


def test_p2_10_equation_alignment(work):
    doc = Document()
    inline = doc.add_paragraph()
    inline.add_run('Inline formula: ')
    inline._p.append(parse_xml(OMATH_XML))
    standalone = doc.add_paragraph()
    standalone._p.append(parse_xml(OMATHPARA_XML))

    actions = equation_format.format_equations(doc)
    check(
        'P2-10 行内公式段落不被居中',
        inline.paragraph_format.alignment is None,
        inline.paragraph_format.alignment,
    )
    check(
        'P2-10 独立公式段落仍居中',
        standalone.paragraph_format.alignment == WD_ALIGN_PARAGRAPH.CENTER,
        standalone.paragraph_format.alignment,
    )
    inline_actions = [
        a for a in actions if a.get('paragraph_index') == 0
    ]
    check(
        'P2-10 行内公式标记为 skipped_inline',
        bool(inline_actions)
        and inline_actions[0].get('action') == 'skipped_inline',
        actions,
    )


def test_p2_11_table_equation_count(work):
    path = os.path.join(work, 'p2_11.docx')
    doc = Document()
    table = doc.add_table(rows=1, cols=1)
    table.cell(0, 0).paragraphs[0]._p.append(parse_xml(OMATH_XML))
    doc.save(path)

    info = scanner.scan_docx(path)
    check(
        'P2-11 表格内公式计入 total_equations',
        info.total_equations >= 1,
        info.total_equations,
    )
    check(
        'P2-11 表格对象自身统计到公式',
        len(info.tables) >= 1 and info.tables[0].equations >= 1,
        [t.equations for t in info.tables],
    )


def test_p2_12_cli_exit_codes(work):
    proc = run_cli(['scan'])
    check(
        'P2-12 scan 缺参数退出码为 1',
        proc.returncode == 1,
        (proc.returncode, (proc.stdout or '')[-300:]),
    )

    missing = os.path.join(work, 'missing-file.docx')
    for command in ('scan', 'package-validate', 'fingerprint'):
        proc = run_cli([command, missing])
        try:
            parsed = json.loads(proc.stdout)
        except Exception:
            parsed = {}
        check(
            f'P2-12 {command} 缺文件退出码为 2 且 JSON 含 error',
            proc.returncode == 2 and bool(parsed.get('error')),
            (proc.returncode, parsed, (proc.stderr or '')[-200:]),
        )

    zero_doc = os.path.join(work, 'p2_12_zero.docx')
    new_doc('Some text').save(zero_doc)
    zero_bytes = Path(zero_doc).read_bytes()
    repl = os.path.join(work, 'p2_12_repl.json')
    with open(repl, 'w', encoding='utf-8') as fh:
        json.dump([{'old': 'ABSENT_TOKEN', 'new': 'X'}], fh, ensure_ascii=False)
    proc = run_cli(['edit', zero_doc, repl, 'null', 'text_only'])
    try:
        parsed = json.loads(proc.stdout)
    except Exception:
        parsed = {}
    check(
        'P2-12 零替换 edit 退出码为 0 且报告未修改',
        proc.returncode == 0
        and parsed.get('success') is False
        and parsed.get('changes') == 0
        and Path(zero_doc).read_bytes() == zero_bytes,
        (proc.returncode, parsed.get('changes'), (proc.stderr or '')[-200:]),
    )


def main():
    work = tempfile.mkdtemp(prefix='wg-regress-')
    saved_path = sys.path[:]
    try:
        test_p1_1_editor_protected_nodes(work)
        test_p1_5_multi_text_nodes(work)
        test_p1_6_integrity(work)
        test_p1_2_text_only_mode(work)
        test_p1_3_safe_write(work)
        test_p1_4_scope_validation(work)
        test_p2_9_package_guard(work)
        test_p2_10_equation_alignment(work)
        test_p2_11_table_equation_count(work)
        test_p2_12_cli_exit_codes(work)
    except Exception:
        RESULT['failed'] += 1
        RESULT['failures'].append({
            'name': '未捕获异常导致测试中断',
            'detail': traceback.format_exc()[-2000:],
        })
    finally:
        sys.path[:] = saved_path
        shutil.rmtree(work, ignore_errors=True)


if __name__ == '__main__':
    main()
    emit_and_exit(0)
