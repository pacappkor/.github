# SPDX-License-Identifier: GPL-3.0-only
"""Archive GitHub daily traffic; no third-party dependencies."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request


class TrafficError(ValueError):
    """Safe diagnostic, never includes authentication data."""


def data_path(value):
    path = Path(value)
    if (not value or path.anchor or any(p.lower() in ('..', '.git') for p in path.parts)
            or not path.parts or '\\' in value or ':' in value
            or any(not re.fullmatch(r'[A-Za-z0-9_.-]+', p) for p in path.parts)):
        raise TrafficError('data-dir must be a relative directory outside .git')
    root = Path.cwd().resolve()
    current = root
    for part in path.parts:
        current /= part
        if current.is_symlink():
            raise TrafficError('data-dir must not contain symlinks')
    if current == root:
        raise TrafficError('data-dir cannot be the repository root')
    return path


def normalize(record):
    if not isinstance(record, dict):
        raise TrafficError('invalid daily record')
    timestamp = record.get('timestamp')
    if not isinstance(timestamp, str):
        raise TrafficError('invalid timestamp')
    try:
        date = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
    except ValueError:
        raise TrafficError('invalid timestamp') from None
    if date.tzinfo is None or date.utcoffset().total_seconds() != 0 or any(
            (date.hour, date.minute, date.second, date.microsecond)):
        raise TrafficError('expected UTC daily timestamp')
    result = {'timestamp': date.astimezone(timezone.utc).strftime('%Y-%m-%dT00:00:00Z')}
    for key in ('count', 'uniques'):
        number = record.get(key)
        if type(number) is not int or number < 0:
            raise TrafficError('counts must be nonnegative integers')
        result[key] = number
    if result['uniques'] > result['count']:
        raise TrafficError('uniques cannot exceed count')
    return result


def accumulate(previous, incoming):
    if not isinstance(previous, list) or not isinstance(incoming, list):
        raise TrafficError('daily records must be arrays')
    days = {}
    for raw in previous + incoming:
        row = normalize(raw)
        old = days.get(row['timestamp'])
        if old:
            row = {**row, 'count': max(old['count'], row['count']),
                   'uniques': max(old['uniques'], row['uniques'])}
        days[row['timestamp']] = row
    return [days[key] for key in sorted(days)]


def compact(value):
    for divisor, suffix in ((1_000_000_000, 'B'), (1_000_000, 'M'), (1_000, 'k')):
        if value >= divisor:
            return f'{value / divisor:.1f}'.removesuffix('.0') + suffix
    return str(value)


def badge(kind, records):
    total = sum(row['count'] for row in records)
    uniques = sum(row['uniques'] for row in records)
    noun = 'views' if kind == 'views' else 'clones'
    return {'schemaVersion': 1, 'label': 'visitors' if kind == 'views' else 'clones',
            'message': f'{compact(total)} {noun} / {compact(uniques)} daily uniques',
            'color': 'blue', 'cacheSeconds': 3600}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward the Authorization header to a redirect destination.
        return None


def fetch(repository, kind, token):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise TrafficError('invalid repository')
    request = urllib.request.Request(
        f'https://api.github.com/repos/{repository}/traffic/{kind}?per=day',
        headers={'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json',
                 'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'org-traffic-counter'})
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=30) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        raise TrafficError(f'traffic API {kind} failed (HTTP {error.code})') from None
    except (OSError, ValueError):
        raise TrafficError(f'traffic API {kind} failed') from None
    if not isinstance(payload, dict) or kind not in payload:
        raise TrafficError(f'traffic API {kind} has no daily array')
    return payload[kind]


def update(directory, responses):
    directory = data_path(str(directory))
    outputs = {}
    for kind in ('views', 'clones'):
        target = directory / f'{kind}.json'
        if target.is_symlink():
            raise TrafficError('data files must not be symlinks')
        previous = json.loads(target.read_text(encoding='utf-8')) if target.exists() else []
        records = accumulate(previous, responses[kind])
        outputs[target] = records
        outputs[directory / f'badge-{kind}.json'] = badge(kind, records)
    # Validate both responses before writing anything. Stable output means no empty commits.
    directory.mkdir(parents=True, exist_ok=True)
    changed = []
    for target, payload in outputs.items():
        if target.is_symlink():
            raise TrafficError('data files must not be symlinks')
        text = json.dumps(payload, ensure_ascii=False, indent=2) + '\n'
        if not target.exists() or target.read_text(encoding='utf-8') != text:
            temporary = target.with_suffix('.json.tmp')
            if temporary.is_symlink():
                raise TrafficError('temporary files must not be symlinks')
            temporary.write_text(text, encoding='utf-8', newline='\n')
            temporary.replace(target)
            changed.append(target)
    return changed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', default='.traffic')
    parser.add_argument('--repository', required=True)
    args = parser.parse_args()
    try:
        directory = data_path(args.data_dir)
        token = os.environ.get('TRAFFIC_TOKEN')
        if not token:
            raise TrafficError('TRAFFIC_TOKEN is required')
        responses = {kind: fetch(args.repository, kind, token) for kind in ('views', 'clones')}
        changed = update(directory, responses)
        print(f'Updated {len(changed)} traffic data files')
    except (TrafficError, OSError, ValueError):
        # Do not render exception text: network libraries can retain request secrets.
        print('Traffic update failed; check API access, input paths and stored JSON.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
