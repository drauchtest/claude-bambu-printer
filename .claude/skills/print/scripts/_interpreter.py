"""Re-exec under an interpreter that has the printer dependencies.

Why this exists: SKILL.md invokes every script as `python3 ~/.claude/skills/print/
scripts/<name>.py`. On this machine `python3` resolves to the Windows Store
launcher, which does not have `bambu-lab-cloud-api` -- so the skill reported
"library not installed" and offered to pip-install into the wrong interpreter,
while the printer was perfectly reachable from a venv two directories away.

Patching the 19 call sites in SKILL.md would fix only the call sites that got
patched. Fixing it here fixes every invocation, including the ones a future
version of the skill adds.

The interpreter path is NOT hardcoded: it is read from a pointer file outside the
repository, because this is a public fork and the path is specific to one machine.

    ~/.claude/bambu-python.txt   one line: the full path to the interpreter

Without that file the behaviour is unchanged, so upstream and other machines are
not affected.
"""

import os
import sys

POINTER = os.path.expanduser("~/.claude/bambu-python.txt")
GUARD = "BAMBU_SKILL_REEXEC"


def _lees_pointer():
    # utf-8-sig, not utf-8: PowerShell 5.1 writes a BOM with `Set-Content
    # -Encoding utf8`, and so does Notepad. Read as plain utf-8 the path then
    # starts with an invisible ﻿, the file "does not exist", and the whole
    # re-exec falls through silently. That is exactly how this shim first failed.
    try:
        with open(POINTER, encoding="utf-8-sig") as f:
            for regel in f:
                regel = regel.strip()
                if regel and not regel.startswith("#"):
                    return regel
    except OSError:
        return None
    return None


def ensure(module="bambulab"):
    """Re-exec this script under the pointed-to interpreter if `module` is missing.

    Returns normally when the current interpreter is already usable, when no
    pointer file exists, or when we have already re-execed once -- never loops.
    """
    try:
        __import__(module)
        return
    except ImportError:
        pass

    if os.environ.get(GUARD):
        # Already switched once and the module is still missing. Carry on and let
        # the script's own error stand; switching again would only hide the real
        # cause.
        return

    doel = _lees_pointer()
    if not doel or not os.path.isfile(doel):
        # One line to stderr, not a silent fallback. Without it a broken install
        # looks identical to a machine that never needed this shim, and the
        # script's own "pip install bambu-lab-cloud-api" then points at the wrong
        # interpreter. Execution continues; this is a hint, not a failure.
        wat = "is missing" if not doel else f"points at something that does not exist: {doel}"
        print(f"[skill] {module} not available here, and {POINTER} {wat}. "
              f"Point that file at an interpreter that has it, or install it "
              f"into {sys.executable}.", file=sys.stderr)
        return
    if os.path.normcase(doel) == os.path.normcase(sys.executable):
        return

    omgeving = dict(os.environ)
    omgeving[GUARD] = "1"
    argumenten = [doel, os.path.abspath(sys.argv[0])] + sys.argv[1:]
    print(f"[skill] switching to {doel} (this interpreter lacks {module})",
          file=sys.stderr)

    # subprocess, not os.execve: on Windows execve replaces the process in a way
    # that loses the child's output through a pipe -- the first version of this
    # shim announced the switch and then printed nothing. The exit code is passed
    # through, so the skill's `reauth` handling keeps working.
    import subprocess
    try:
        resultaat = subprocess.run(argumenten, env=omgeving)
    except OSError as e:
        print(f"[skill] could not start {doel}: {e}", file=sys.stderr)
        return
    sys.exit(resultaat.returncode)
