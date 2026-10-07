# -*- coding: utf-8 -*-
from __future__ import annotations

import subprocess
import tempfile
import textwrap
from pathlib import Path

node = Path.home() / ".toa3" / "harness-runtime" / "node" / "node.exe"
binjs = (
    Path.home()
    / ".toa3"
    / "harness-runtime"
    / "node_modules"
    / "@deepseek-ai"
    / "dsh"
    / "lib"
    / "bin.js"
)
home = Path.home() / ".toa3" / "harness-runtime" / ".dsh"

probe = Path(tempfile.gettempdir()) / "toa_probe_main.mjs"
probe.write_text(
    "console.log('main=' + import.meta.main);\n"
    "console.log('url=' + import.meta.url);\n",
    encoding="utf-8",
)
r = subprocess.run([str(node), str(probe)], capture_output=True, text=True)
print("probe", r.returncode, repr(r.stdout), repr(r.stderr))

# Does bin.js see itself as main?
r_bin = subprocess.run(
    [str(node), str(binjs), "--version"],
    capture_output=True,
    text=True,
    cwd=str(binjs.parent),
    env={**dict(**__import__("os").environ), "DSH_HOME": str(home)},
)
print("bin --version", r_bin.returncode, repr(r_bin.stdout), repr(r_bin.stderr))

wrap = Path(tempfile.gettempdir()) / "toa_run_dsh.mjs"
wrap.write_text(
    textwrap.dedent(
        f"""\
        import {{ pathToFileURL }} from 'node:url';
        const bin = {binjs.as_posix()!r};
        process.argv = [process.execPath, bin, '--profile', 'web', '--port', '3082', '--no-open'];
        process.env.DSH_HOME = {str(home).replace(chr(92), '/')!r};
        const mod = await import(pathToFileURL(bin).href);
        console.error('force runCli');
        await mod.runCli();
        """
    ),
    encoding="utf-8",
)
r3 = subprocess.run(
    [str(node), str(wrap)],
    capture_output=True,
    text=True,
    timeout=20,
    cwd=str(binjs.parent),
    env={**dict(**__import__("os").environ), "DSH_HOME": str(home)},
)
print("force rc", r3.returncode)
print("OUT", (r3.stdout or "")[-4000:])
print("ERR", (r3.stderr or "")[-4000:])
