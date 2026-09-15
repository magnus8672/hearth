"""Check repository documentation links and the immutable source snapshot. No network calls."""

import argparse
import hashlib
import json
import re
import subprocess
from collections import Counter
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check():
    errors = []
    listed = subprocess.check_output(
        ['git', 'ls-files', '--cached', '--others', '--exclude-standard'], cwd=ROOT, text=True,
    ).splitlines()
    files = sorted({ROOT / name for name in listed if (ROOT / name).is_file()})
    documents = [path for path in files if path.suffix.lower() == '.md']
    outside = [path.relative_to(ROOT).as_posix() for path in documents
               if not path.is_relative_to(ROOT / 'docs') and path.name not in {'README.md', 'AGENTS.md'}]
    # Only the two root discovery pointers are exempt, not nested README/AGENTS files.
    outside += [path.relative_to(ROOT).as_posix() for path in documents
                if not path.is_relative_to(ROOT / 'docs') and path.parent != ROOT
                and path.name in {'README.md', 'AGENTS.md'}]
    errors.extend(f'Document outside docs: {name}' for name in outside)
    links = 0

    def inspect_link(source, value, line):
        nonlocal links
        value = value.strip('<>')
        parsed = urlsplit(value)
        if parsed.scheme or parsed.netloc or not parsed.path or parsed.path.startswith('/'):
            return
        target = (source.parent / unquote(parsed.path)).resolve()
        links += 1
        if not target.is_relative_to(ROOT) or not target.exists():
            errors.append(f'{source.relative_to(ROOT).as_posix()}:{line}: missing local link {value}')

    for source in documents:
        fence = None
        for number, line in enumerate(source.read_text(encoding='utf-8-sig').splitlines(), 1):
            marker = re.match(r'^\s*(`{3,}|~{3,})', line)
            if marker:
                sequence = marker.group(1)
                if fence is None:
                    fence = sequence
                elif sequence[0] == fence[0] and len(sequence) >= len(fence):
                    fence = None
                continue
            if fence is not None:
                continue
            for match in re.finditer(r'\]\((<[^>]+>|[^\s)]+)(?:\s+"[^"]*")?\)', line):
                inspect_link(source, match.group(1), number)
            definition = re.match(r'^\s*\[[^\]]+\]:\s*(<[^>]+>|\S+)', line)
            if definition:
                inspect_link(source, definition.group(1), number)
        if fence:
            errors.append(f'{source.relative_to(ROOT).as_posix()}: unclosed code fence')

    class GalleryLinks(HTMLParser):
        def __init__(self, source):
            super().__init__()
            self.source = source

        def handle_starttag(self, tag, attrs):
            for name, value in attrs:
                if name in {'href', 'src'} and value:
                    inspect_link(self.source, value, self.getpos()[0])

    for source in [ROOT / 'brand/index.html', ROOT / 'docs/plan/brand/index.html']:
        GalleryLinks(source).feed(source.read_text(encoding='utf-8'))

    baseline = json.loads((ROOT / 'evidence/preparation/2026-09-12/inspection.json').read_text(encoding='utf-8'))['source_inventory']
    preserved = 0
    for record in baseline:
        path = ROOT / 'docs/plan' / record['file']
        if path.is_file() and digest(path) == record['sha256']:
            preserved += 1
        else:
            errors.append(f'Original snapshot changed or missing: {record["file"]}')
    gates = json.loads((ROOT / 'docs/implementation/release-gates.json').read_text(encoding='utf-8'))['gates']
    return {
        'checked_at': datetime.now(UTC).isoformat(),
        'scope': 'Local documentation file/asset links, balanced fences, docs placement and original snapshot hashes. External URLs and Markdown heading anchors are not checked. No product tests or inference rerun.',
        'status': 'passed' if not errors else 'failed',
        'markdown_files': len(documents),
        'local_links_checked': links,
        'documents_outside_docs': outside,
        'root_pointers': [path.name for path in documents if path.parent == ROOT],
        'original_snapshot_files_verified': preserved,
        'original_snapshot_file_count': len(baseline),
        'release_gate_counts': dict(Counter(gate['status'] for gate in gates)),
        'errors': errors,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='Optional JSON evidence file.')
    args = parser.parse_args()
    result = check()
    encoded = json.dumps(result, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding='utf-8')
    print(encoded)
    raise SystemExit(0 if result['status'] == 'passed' else 1)


if __name__ == '__main__':
    main()
