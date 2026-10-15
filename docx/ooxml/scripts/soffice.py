"""Run LibreOffice headless inside a private, throwaway profile.

A private profile makes each run independent of any LibreOffice window the
user has open, of other runs in parallel, and of the user's own settings and
macros, none of which it reads or writes. The cost is about two seconds of
first-start initialisation per run.

Identical copies live in docx/ooxml/scripts, pptx/ooxml/scripts and
xlsx/scripts so that each skill folder stays self-contained.
"""

import os
import shutil
import signal
import subprocess
import tempfile
from pathlib import Path

MACOS_APP = "/Applications/LibreOffice.app/Contents/MacOS/soffice"

_XCU_HEAD = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<oor:items xmlns:oor="http://openoffice.org/2001/registry" '
    'xmlns:xs="http://www.w3.org/2001/XMLSchema" '
    'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">\n'
)


class SofficeError(RuntimeError):
    pass


def find_soffice():
    for name in ("soffice", "libreoffice"):
        if path := shutil.which(name):
            return path
    if os.path.exists(MACOS_APP):
        return MACOS_APP
    raise SofficeError(
        "LibreOffice not found. Install it with `brew install --cask libreoffice` "
        "or `apt-get install libreoffice`."
    )


def _write_settings(profile, settings):
    """Seed the profile with configuration values before first start.

    `settings` maps "/org.openoffice.Office.X/Some/Group" to {prop: value}.
    """
    items = "".join(
        f'<item oor:path="{path}"><prop oor:name="{name}" oor:op="fuse">'
        f"<value>{value}</value></prop></item>\n"
        for path, props in settings.items()
        for name, value in props.items()
    )
    user = Path(profile) / "user"
    user.mkdir(parents=True, exist_ok=True)
    (user / "registrymodifications.xcu").write_text(
        _XCU_HEAD + items + "</oor:items>\n", encoding="utf-8"
    )


def run(args, timeout=120, settings=None):
    """Run soffice with `args` in a fresh profile; return the CompletedProcess.

    Raises SofficeError on timeout. The whole process group is killed then, so
    no orphaned LibreOffice keeps the profile or the input file locked.
    """
    exe = find_soffice()
    with tempfile.TemporaryDirectory(prefix="soffice-profile-") as profile:
        if settings:
            _write_settings(profile, settings)
        cmd = [
            exe,
            f"-env:UserInstallation={Path(profile).as_uri()}",
            "--headless",
            "--invisible",
            "--norestore",
            "--nologo",
            "--nodefault",
            "--nolockcheck",
            *map(str, args),
        ]
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
            raise SofficeError(f"LibreOffice timed out after {timeout}s") from None
        return subprocess.CompletedProcess(cmd, proc.returncode, out, err)


def convert(src, outdir, target, timeout=120, settings=None):
    """Convert `src` into `outdir` with --convert-to `target`; return the output path.

    `target` is an extension, optionally with a filter ("pdf", "xlsx:Calc MS
    Excel 2007 XML"). Raises SofficeError when LibreOffice produces no file.
    """
    src, outdir = Path(src).resolve(), Path(outdir).resolve()
    if not src.is_file():
        raise SofficeError(f"{src} does not exist")
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / f"{src.stem}.{target.split(':')[0]}"
    out.unlink(missing_ok=True)
    result = run(
        ["--convert-to", target, "--outdir", outdir, src],
        timeout=timeout,
        settings=settings,
    )
    if not out.exists():
        detail = (result.stderr or result.stdout).strip() or "no output produced"
        raise SofficeError(f"LibreOffice could not convert {src.name}: {detail}")
    return out
