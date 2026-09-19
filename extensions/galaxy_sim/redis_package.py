"""Build checkout-owned package files and private Redis/client configuration."""
import argparse
import hashlib
import ipaddress
import json
from pathlib import Path
import secrets
import shutil
import subprocess
from .config import ROOT, load_profile

PRIVATE = ROOT / ".local" / "redis-lan"
STAGE = ROOT / "build" / "redis-package"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate(host=None):
    PRIVATE.mkdir(parents=True, exist_ok=True)
    path = PRIVATE / "settings.json"
    if path.exists():
        settings = json.loads(path.read_text())
        if host and host != settings["host"]:
            raise ValueError("LAN address changed; review private settings and firewall first")
    else:
        address = ipaddress.ip_address(host or "")
        if not trusted_address(address):
            raise ValueError("Supply the trusted LAN IPv4 address with --host")
        settings = dict(host=str(address), port=16379, db=5,
                        password=secrets.token_urlsafe(36))
        path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    if not trusted_address(ipaddress.ip_address(settings["host"])):
        raise ValueError("Redis host must be an RFC1918 LAN IPv4 address")
    if not (1024 <= settings["port"] <= 65535) or settings["db"] not in range(16):
        raise ValueError("Invalid private Redis port/db")
    if len(settings["password"]) < 32 or not all(c.isalnum() or c in "-_" for c in settings["password"]):
        raise ValueError("Redis password must contain at least 32 URL-safe characters")
    account = load_profile()["account_id"]
    # No disk persistence: this instance is transport, not a business database.
    (PRIVATE / "redis.conf").write_text(
        'bind 0.0.0.0\nprotected-mode yes\nport 6379\nsave ""\nappendonly no\n'
        'requirepass ' + settings["password"] + '\n', encoding="ascii")
    for name, host_value in (("windows", "127.0.0.1"), ("mac", settings["host"])):
        directory = PRIVATE / name
        directory.mkdir(exist_ok=True)
        config = dict(settings, host=host_value, transport="redis")
        text = "# Private client configuration. Do not share or commit.\n"
        text += "BIGQMT_ACCOUNT_ID = %r\nBIGQMT_RPC_TIMEOUT_SECONDS = 5.0\n" % account
        text += "BIGQMT_REDIS_CONFIG = %r\n" % config
        for option in ("FORMULA_SERVER", "LOCAL_CACHE", "FULL_TICK_CACHE"):
            text += "BIGQMT_%s_CONFIG = {'enabled': False}\n" % option
        (directory / "bigqmt_signal_trader_client_config.py").write_text(text, encoding="ascii")
    return settings, account


def trusted_address(address):
    return any(address in ipaddress.ip_network(block) for block in
               ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))


def build(settings, account):
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    files = subprocess.check_output(["git", "ls-files", "src/bigqmt_signal_trader"],
                                    cwd=ROOT, text=True).splitlines()
    files += ["src/" + name for name in ("BIGQMT_REDIS_DRYRUN.py",
              "bigqmt_signal_trader_strategy.py", "bigqmt_signal_trader_redis_rpc_runtime.py")]
    STAGE.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for source in files:
        relative = str(Path(source).relative_to("src")).replace("\\", "/")
        target = STAGE / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / source, target)
        hashes[relative] = digest(target)
    entry = STAGE / "BIGQMT_GALAXY_REDIS.py"
    entry.write_bytes((STAGE / "BIGQMT_REDIS_DRYRUN.py").read_bytes() +
                     ("\nGALAXY_SOURCE_COMMIT = %r\n" % commit).encode("ascii") +
                     (ROOT / "extensions/galaxy_sim/package_overlay.py").read_bytes())
    config = dict(settings, host="127.0.0.1", transport="redis", redis_enabled=True,
                  account_type="STOCK", rpc_allow_order_methods=False,
                  rpc_background_threads=True, rpc_process_in_listener=False,
                  rpc_listener_methods=(), schedule_adjust=True,
                  schedule_adjust_interval="100nMilliSecond", full_tick_cache_enabled=False,
                  download_jobs_enabled=False, exec_events_enabled=False, quote_push={"enabled": True})
    local = STAGE / "bigqmt_signal_trader_local_config.py"
    local.write_text("# Private; generated from this checkout.\nBIGQMT_ACCOUNT_ID = %r\n"
                     "BIGQMT_ACCOUNT_TYPE = 'STOCK'\nBIGQMT_REDIS_CONFIG = %r\n" %
                     (account, config), encoding="ascii")
    for path in (entry, local):
        hashes[path.name] = digest(path)
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=normal"], cwd=ROOT))
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip()
    manifest = dict(source_commit=commit, source_branch=branch, source_dirty=dirty, files=hashes,
                    overlay_sha256=digest(ROOT / "extensions/galaxy_sim/package_overlay.py"))
    (STAGE / "galaxy-package-manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def deploy(target, manifest):
    if manifest["source_dirty"]:
        raise ValueError("Commit checkout changes before deploying a traceable package")
    if manifest.get("source_branch") == "main":
        raise ValueError("Galaxy deployment must not be developed on main")
    target = Path(target).resolve() / "python"
    if not (target / "_PyContextInfo.py").is_file() or target.is_symlink():
        raise ValueError("Not a regular QMT python directory")
    owner = target / "galaxy-package-manifest.json"
    old = json.loads(owner.read_text()) if owner.exists() else {"files": {}}
    # Preflight all files before writing. Never replace unknown or GUI-modified files.
    for name, expected in manifest["files"].items():
        path = target / name
        if path.exists() and digest(path) not in (expected, old["files"].get(name)):
            raise ValueError("Existing file is not owned/unchanged: " + name)
        if path.is_symlink() or any(p.is_symlink() for p in path.parents if p != target.parent):
            raise ValueError("Refusing redirected destination")
    if owner.exists():
        backup = PRIVATE / "backups" / (old.get("source_commit", "unknown") + "-" + secrets.token_hex(4))
        for name in list(old["files"]) + [owner.name]:
            source = target / name
            if source.is_file():
                destination = backup / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
    for name, expected in manifest["files"].items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(STAGE / name, path)
        if digest(path) != expected:
            raise RuntimeError("Deployment hash mismatch: " + name)
    shutil.copyfile(STAGE / owner.name, owner)
    print("Package deployed; %d files verified; commit=%s dirty=%s" %
          (len(manifest["files"]), manifest["source_commit"], manifest["source_dirty"]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host")
    parser.add_argument("--qmt-root")
    args = parser.parse_args()
    settings, account = generate(args.host)
    manifest = build(settings, account)
    if args.qmt_root:
        deploy(args.qmt_root, manifest)
    else:
        print("Private configuration and package staged; no QMT files changed")


if __name__ == "__main__":
    main()
