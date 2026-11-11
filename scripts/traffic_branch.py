# SPDX-License-Identifier: GPL-3.0-only
"""Synchronize the counting branch. Run from the caller repository root."""
import os
from pathlib import PurePosixPath
import subprocess
import sys
from pathlib import Path

# Explicit trusted sibling import also works with Python isolated mode.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from traffic_update import data_path


def git(*args, check=True):
    return subprocess.run(['git', *args], check=check, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE)


def synchronize(branch, directory):
    directory = data_path(directory).as_posix()
    if branch == 'main' or branch.startswith('-'):
        raise ValueError('counting branch cannot be main or an option')
    git('check-ref-format', f'refs/heads/{branch}')
    git('config', 'user.name', 'antisocial-socialist')
    git('config', 'user.email', '355263797+antisocial-socialist@users.noreply.github.com')
    remote = f'refs/remotes/origin/{branch}'
    exists = git('show-ref', '--verify', '--quiet', remote, check=False).returncode == 0
    if not exists:
        git('checkout', '-b', branch, 'origin/main')
        return
    git('checkout', '-B', branch, remote)
    if git('merge', '--ff-only', 'origin/main', check=False).returncode == 0:
        return
    merged = git('merge', '--no-edit', '--no-commit', 'origin/main', check=False)
    if merged.returncode:
        conflicts = git('diff', '--name-only', '--diff-filter=U', '-z').stdout
        paths = [os.fsdecode(p) for p in conflicts.split(b'\0') if p]
        if not paths or any(not PurePosixPath(p).is_relative_to(directory) for p in paths):
            git('merge', '--abort', check=False)
            raise ValueError('merge failed outside counting data; resolve on main first')
        for path in paths:
            ours = git('cat-file', '-e', f':2:{path}', check=False).returncode == 0
            if ours:
                git('checkout', '--ours', '--', path)
                git('add', '--', path)
            else:
                git('rm', '-f', '--', path)
    # --no-commit deliberately leaves an explicit merge to preserve main ancestry.
    git('commit', '--no-edit')


if __name__ == '__main__':
    try:
        synchronize(os.environ['TRAFFIC_BRANCH'], os.environ['TRAFFIC_DATA_DIR'])
    except (ValueError, OSError, subprocess.CalledProcessError):
        print('Traffic branch sync failed: invalid input or conflict outside data directory.',
              file=sys.stderr)
        sys.exit(1)
