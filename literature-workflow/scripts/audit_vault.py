"""Read-only CSV/note inventory and exact DOI/title candidate matching. No XLSX writes/reads."""
import argparse
import csv
import json
import re
import unicodedata
from pathlib import Path

FIELDS = '文献ID,论文标题,作者与年份,期刊/会议,DOI,研究主题,核心研究问题,数据来源,研究方法,主要发现,创新贡献,研究局限,可借鉴之处,潜在研究问题,阅读状态,详细笔记文件,Zotero条目,最后更新'.split(',')


def doi_key(value):
    value = value.strip().strip('\"\'').lower()
    value = re.sub(r'^(?:https?://(?:dx\.)?doi\.org/|doi\s*:\s*)', '', value)
    return value.rstrip('.')


def title_key(value):
    return ''.join(c for c in unicodedata.normalize('NFKC', value).casefold() if c.isalnum())


def scalar(front, key):
    match = re.search(r'^' + re.escape(key) + r':\s*([^\n]*)$', front, re.M)
    return match.group(1).strip().strip('\"\'') if match else ''


def audit(vault, doi='', title=''):
    vault = Path(vault)
    if not vault.is_dir():
        raise ValueError('文献库不存在：' + str(vault))
    issues, warnings, rows, notes = [], [], [], []
    csv_path = vault / '文献总表.csv'
    if csv_path.exists():
        with csv_path.open(encoding='utf-8-sig', newline='') as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != FIELDS:
                issues.append('CSV字段与内置18列约定不同；需检查当前schema')
            for number, row in enumerate(reader, start=2):
                if None in row or any(v is None for v in row.values()):
                    issues.append(f'CSV第{number}行列数异常')
                rows.append({k: v or '' for k, v in row.items() if k is not None})
    else:
        warnings.append('未找到CSV，只检查笔记；不能判断完整入库状态')
    folder = vault / 'Literature'
    for path in sorted(folder.glob('*.md')):
        content = path.read_text(encoding='utf-8-sig')
        match = re.match(r'^---\s*\n(.*?)\n---(?:\s*\n|$)', content, re.S)
        front = match.group(1) if match else ''
        identity = scalar(front, '文献ID') or path.stem
        notes.append({'文献ID': identity, '论文标题': scalar(front, '标题'),
                      'DOI': scalar(front, 'DOI'), 'path': str(path)})
        if scalar(front, '文献ID') and identity != path.stem:
            issues.append('笔记文件名与ID不同：' + str(path))
    for label, entries in [('CSV', rows), ('笔记', notes)]:
        for key, normalizer in [('文献ID', str.strip), ('DOI', doi_key)]:
            seen = {}
            for entry in entries:
                value = normalizer(entry.get(key, ''))
                # Only recognizable DOIs are identity keys, not placeholders.
                if key == 'DOI' and not re.match(r'^10\.\d{4,9}/\S+$', value):
                    continue
                if not value:
                    continue
                if value in seen:
                    issues.append(f'{label}重复{key}：{value}')
                seen[value] = True
    row_ids = {r.get('文献ID', '') for r in rows} - {''}
    note_ids = {n['文献ID'] for n in notes}
    candidates = []
    for label, entries in [('CSV', rows), ('笔记', notes)]:
        for entry in entries:
            reasons = []
            if doi and doi_key(doi) == doi_key(entry.get('DOI', '')):
                reasons.append('DOI相同')
            if title and title_key(title) == title_key(entry.get('论文标题', '')):
                reasons.append('规范化标题相同，仍需核对版本')
            if reasons:
                candidates.append({'source': label, **entry, 'match': reasons})
    return {'vault': str(vault), 'csv_records': len(rows), 'notes': len(notes),
            'csv_only_ids': sorted(row_ids - note_ids), 'note_only_ids': sorted(note_ids - row_ids),
            'records': [{'id': r.get('文献ID', ''), 'title': r.get('论文标题', ''), 'doi': r.get('DOI', '')} for r in rows],
            'candidates': candidates, 'issues': issues, 'warnings': warnings,
            'scope': '只读CSV与Literature笔记；未检查Excel、PDF身份、全部内部链接；未分配ID'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vault', default='D:/文献阅读')
    parser.add_argument('--doi', default='')
    parser.add_argument('--title', default='')
    args = parser.parse_args()
    try:
        result = audit(args.vault, args.doi, args.title)
    except (OSError, ValueError, csv.Error) as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result['issues'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
