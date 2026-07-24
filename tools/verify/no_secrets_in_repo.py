#!/usr/bin/env python3
"""
Verify no hardcoded secrets exist in the repository.
Run as part of CI or before commits.
"""
import re
import sys
import os

# Known compromised values — must NEVER appear in committed code
BANNED = [
    "hermes-local-secret-2026",
    "SFBCBA",
    "uHNgVCmJfld_Kx8BfLEjVK5X7I2nF9Be6KidmM3yYc8",
    "NeN0FkX-dFLWzcLQltzCKw",
]

# Patterns that look like hardcoded secrets (not in test/mock context)
SECRET_PATTERNS = [
    (r'token\s*=\s*["\'][A-Za-z0-9_\-]{20,}["\']', "hardcoded token"),
    (r'secret\s*=\s*["\'][A-Za-z0-9_\-]{10,}["\']', "hardcoded secret"),
    (r'password\s*=\s*["\'][A-Za-z0-9_\-]{10,}["\']', "hardcoded password"),
    (r'expected\s*=\s*["\'][A-Za-z0-9_\-]{20,}["\']', "hardcoded expected value"),
]

EXCLUDE_DIRS = {'.git', 'node_modules', '__pycache__', '.hermes', 'build', '.gradle'}
EXCLUDE_FILES = {'.env', '.env.local', '.env.production'}
# This file contains banned patterns for detection — exclude it
SELF_PATH = os.path.normpath(os.path.relpath(__file__, '.'))

def scan():
    errors = []
    scanned = 0

    for root, dirs, files in os.walk('.'):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for f in files:
            if f in EXCLUDE_FILES:
                continue
            if f.endswith(('.pyc', '.class', '.jar', '.apk', '.dex', '.so')):
                continue

            path = os.path.join(root, f)
            if os.path.normpath(path) == SELF_PATH:
                continue  # skip this detection script itself

            # Skip .md docs (they reference rotated values for documentation)
            if f.endswith('.md'):
                continue

            scanned += 1

            try:
                content = open(path, errors='ignore').read()
            except (IOError, OSError):
                continue

            # Check for banned secrets
            for banned in BANNED:
                if banned in content:
                    errors.append(f"LEAKED SECRET in {path}: contains {banned[:12]}...")

            # Check for suspect patterns (skip test files)
            is_test = 'test' in path.lower() or 'mock' in path.lower()
            if not is_test:
                for pattern, desc in SECRET_PATTERNS:
                    for match in re.finditer(pattern, content, re.IGNORECASE):
                        # Skip lines that reference env vars or placeholders
                        line_start = content.rfind('\n', 0, match.start()) + 1
                        line = content[line_start:match.end() + 50]
                        if 'env' in line.lower() or 'placeholder' in line.lower():
                            continue
                        if 'REDACTED' in line or 'xxx' in line.lower():
                            continue
                        errors.append(f"SUSPECT in {path}: {desc} → {match.group()[:50]}")

    print(f"Scanned {scanned} files")
    return errors


if __name__ == '__main__':
    errors = scan()
    if errors:
        print("\n❌ SECRET CHECK FAILED:", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        sys.exit(1)
    else:
        print("✅ PASS: No hardcoded secrets found in repository")
        sys.exit(0)
