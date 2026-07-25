#!/usr/bin/env python3
"""
Verify deduplication logic for Tasker Gateway.
No last-write-wins: identical replays return cached, conflicts rejected.
"""
import sys

class PendingCommandRegistry:
    """Python simulation of the Kotlin PendingCommandRegistry."""
    def __init__(self):
        self._pending = {}  # command_id -> (request_hash)
        self._completed = {}  # command_id -> (request_hash, response)

    def register(self, command_id, request_hash):
        """Returns: (status, cached_response)"""
        if command_id in self._pending:
            existing_hash = self._pending[command_id]
            if existing_hash == request_hash:
                return 'duplicate_identical', None
            return 'duplicate_conflict', None

        if command_id in self._completed:
            existing_hash, response = self._completed[command_id]
            if existing_hash == request_hash:
                return 'duplicate_identical', response
            return 'duplicate_conflict', None

        self._pending[command_id] = request_hash
        return 'new', None

    def complete(self, command_id, request_hash, response):
        if command_id in self._pending:
            stored_hash = self._pending[command_id]
            if stored_hash != request_hash:
                raise ValueError("hash mismatch")
            del self._pending[command_id]
            self._completed[command_id] = (request_hash, response)

passed = 0
failed = 0

def test(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✓ {name}")
    else:
        failed += 1
        print(f"  ✗ {name}: {detail}")

# ====== Dedup Tests ======
print("=== Deduplication Logic ===")

reg = PendingCommandRegistry()

# Test 1: New command
status, _ = reg.register("cmd-1", "hash-a")
test("New command", status == 'new', f"got {status}")

# Test 2: Identical duplicate returns cached response
cached = {"ok": True, "response": "first"}
reg.complete("cmd-1", "hash-a", cached)
status, resp = reg.register("cmd-1", "hash-a")
test("Identical replay returns cached", status == 'duplicate_identical')
test("Cached response matches", resp == cached)

# Test 3: Conflict after completion
status, _ = reg.register("cmd-2", "hash-a")
reg.complete("cmd-2", "hash-a", {"ok": True})
status, resp = reg.register("cmd-2", "hash-b")
test("Conflict after completion", status == 'duplicate_conflict')
test("No response on conflict", resp is None, f"got {resp}")

# Test 4: Pending identical
status, _ = reg.register("cmd-3", "hash-c")
status2, _ = reg.register("cmd-3", "hash-c")
test("Pending identical", status2 == 'duplicate_identical')

# Test 5: Pending conflict
status, _ = reg.register("cmd-4", "hash-d")
status2, _ = reg.register("cmd-4", "hash-e")
test("Pending conflict", status2 == 'duplicate_conflict')

# Test 6: Independent commands
status, _ = reg.register("cmd-5", "hash-f")
test("Independent command 1", status == 'new')
status, _ = reg.register("cmd-6", "hash-g")
test("Independent command 2", status == 'new')

# Test 7: No last-write-wins
reg2 = PendingCommandRegistry()
reg2.register("cmd-lww", "hash-1")
reg2.complete("cmd-lww", "hash-1", {"response": "first"})
status, resp = reg2.register("cmd-lww", "hash-2")
test("No last-write-wins on conflict", status == 'duplicate_conflict')
test("Conflict has no response", resp is None)

# Test 8: Three independent commands
reg3 = PendingCommandRegistry()
for i in range(3):
    status, _ = reg3.register(f"cmd-{i}", f"hash-{i}")
    test(f"Command {i} is new", status == 'new')

# Test 9: Complete and re-register returns cached
reg4 = PendingCommandRegistry()
reg4.register("cmd-r", "hash-r")
response = {"ok": True, "duration_ms": 50}
reg4.complete("cmd-r", "hash-r", response)
status, resp = reg4.register("cmd-r", "hash-r")
test("Re-register after complete returns cached", status == 'duplicate_identical')
test("Cached response intact", resp == response)

# ====== Summary ======
total = passed + failed
print(f"\n{'=' * 50}")
print(f"Results: {passed}/{total} passed, {failed} failed")
if failed > 0:
    print("FAIL")
    sys.exit(1)
else:
    print("PASS: Deduplication logic verified")
    sys.exit(0)
