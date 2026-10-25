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
    # utf-8-sig, niet utf-8: PowerShell 5.1 schrijft met `Set-Content -Encoding utf8`
    # een BOM, en Kladblok doet dat ook. Met gewone utf-8 begint het pad dan met een
    # onzichtbaar ﻿, bestaat het bestand "niet", en valt de hele re-exec stil
    # zonder foutmelding. Precies hoe deze shim bij de eerste test faalde.
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
        # Al een keer gewisseld en de module is er nog niet. Doorgaan en de
        # normale foutmelding van het script laten staan; een tweede wissel zou
        # alleen de echte oorzaak verbergen.
        return

    doel = _lees_pointer()
    if not doel or not os.path.isfile(doel):
        return
    if os.path.normcase(doel) == os.path.normcase(sys.executable):
        return

    omgeving = dict(os.environ)
    omgeving[GUARD] = "1"
    argumenten = [doel, os.path.abspath(sys.argv[0])] + sys.argv[1:]
    print(f"[skill] switching to {doel} (this interpreter lacks {module})",
          file=sys.stderr)

    # subprocess, niet os.execve: op Windows vervangt execve het proces zo dat de
    # uitvoer van het kind door een pipe heen verdwijnt - de eerste versie van deze
    # shim schakelde zichtbaar en leverde daarna niets op. Hier wordt de exitcode
    # doorgegeven, zodat `reauth`-afhandeling in de skill blijft werken.
    import subprocess
    try:
        resultaat = subprocess.run(argumenten, env=omgeving)
    except OSError as e:
        print(f"[skill] could not start {doel}: {e}", file=sys.stderr)
        return
    sys.exit(resultaat.returncode)
