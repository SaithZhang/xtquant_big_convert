"""Run the upstream generator unchanged, then apply the small Galaxy overlay."""
import ast
import hashlib
import json
import os
from pathlib import Path
import pprint
import subprocess
import sys

from .config import ROOT, load_profile, runtime_config

OUTPUT = ROOT / "build" / "BIGQMT_GALAXY_SIM.py"


def configure_shell(source, profile):
    values = {"BIGQMT_ACCOUNT_ID": profile["account_id"],
              "BIGQMT_ACCOUNT_TYPE": profile["account_type"],
              "BIGQMT_REDIS_CONFIG": runtime_config(profile)}
    lines = source.splitlines(keepends=True)
    edits = []
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            name = getattr(node.targets[0], "id", "")
            if name in values:
                edits.append((node.lineno - 1, node.end_lineno, name))
    if sorted(name for _, _, name in edits) != sorted(values):
        raise RuntimeError("Upstream shell contract changed; inspect before rebuilding")
    for start, end, name in reversed(edits):
        lines[start:end] = [name + " = " + pprint.pformat(values[name]) + "\n"]
    return "".join(lines)


def main():
    profile = load_profile()
    OUTPUT.parent.mkdir(exist_ok=True)
    raw = OUTPUT.with_suffix(".upstream.py")
    env = dict(os.environ, BIGQMT_BUILD_OUT=str(raw))
    subprocess.run([sys.executable, str(ROOT / "tools/build_no_redis_single_file_flat.py")],
                   env=env, cwd=str(ROOT), check=True)
    source = configure_shell(raw.read_text(encoding="gbk"), profile)
    overlay = Path(__file__).with_name("qmt_overlay.py").read_text(encoding="ascii")
    source += "\n# GALAXY_SIM_OVERLAY_V1\n" + overlay
    compile(source, str(OUTPUT), "exec")
    OUTPUT.write_bytes(source.encode("gbk"))
    digest = hashlib.sha256(OUTPUT.read_bytes()).hexdigest()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(ROOT), text=True).strip()
    metadata = {"source_commit": head, "sha256": digest,
                "generator": "tools/build_no_redis_single_file_flat.py",
                "overlay": "extensions/galaxy_sim/qmt_overlay.py"}
    OUTPUT.with_suffix(".manifest.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print("Built %s\nSHA256 %s" % (OUTPUT, digest))
    return OUTPUT


if __name__ == "__main__":
    main()
