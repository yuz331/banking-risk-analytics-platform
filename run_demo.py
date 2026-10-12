"""Prepare a reusable four-rule synthetic demo, then launch its local dashboard."""

import argparse
import csv
import importlib.util
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import webbrowser
from contextlib import closing, contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from detect_risks import load_parameters, rule_registry
from generate_data import create_dataset
from load_database import load_dataset

DEFAULT_DIR = ROOT / "data" / "demo_run"
SETTINGS_FILE = "demo-run.json"
SNAPSHOT_FILES = (
    "customers.csv", "accounts.csv", "transactions.csv",
    "injected_scenarios.csv", "banking.db", SETTINGS_FILE,
)


class DemoError(ValueError):
    """A preparation or startup problem with an actionable explanation."""


def demo_path(value):
    path = Path(value).expanduser()
    return (path if path.is_absolute() else ROOT / path).resolve()


def check_dependencies():
    missing = [name for name in ("streamlit", "pandas", "altair")
               if importlib.util.find_spec(name) is None]
    if missing:
        raise DemoError(
            f"Missing dashboard packages: {', '.join(missing)}. "
            f'Install once with: "{sys.executable}" -m pip install -r "{ROOT / "requirements.txt"}"'
        )


def check_port(port):
    if not 1 <= port <= 65535:
        raise DemoError("Port must be between 1 and 65535")
    try:
        # create_server permits closed TCP connections in TIME_WAIT on POSIX,
        # while still refusing an active listener. It handles Windows separately.
        with socket.create_server(("127.0.0.1", port), backlog=1):
            pass
    except OSError as error:
        raise DemoError(
            f"Cannot use local port {port}: {error}. Choose another --port, for example --port 8502."
        ) from error


@contextmanager
def preparation_lock(folder):
    """Prevent two launchers from preparing the same directory concurrently."""
    lock = folder.parent / f"{folder.name}.demo-prepare.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise DemoError(
            f"Preparation lock already exists: {lock}. Check that no other preparation "
            "is running before removing an interrupted preparation's lock."
        ) from error
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(f"pid={os.getpid()}\n")
        yield
    finally:
        lock.unlink(missing_ok=True)


def existing_snapshot(folder, settings):
    if not folder.is_dir() or any(not (folder / name).is_file() for name in SNAPSHOT_FILES):
        raise DemoError(
            f"{folder} is occupied or incomplete. Existing files were preserved. "
            "Choose a new --demo-dir; this launcher does not replace existing folders."
        )
    try:
        saved = json.loads((folder / SETTINGS_FILE).read_text(encoding="utf-8"))
    except (ValueError, OSError) as error:
        raise DemoError(f"Cannot read demo settings in {folder}; choose a new --demo-dir") from error
    if saved != settings:
        raise DemoError(
            f"{folder} was prepared with different settings. Existing files and reviews "
            "were preserved. Use the original --transactions/--seed or choose a new --demo-dir."
        )
    # A zero-byte/empty database is incomplete, rather than permission to refill it.
    database = folder / "banking.db"
    try:
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as connection:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            required = {"customers", "accounts", "transactions", "alerts",
                        "alert_transactions", "alert_details", "reviews"}
            if (not required.issubset(tables) or
                    connection.execute("SELECT count(*) FROM transactions").fetchone()[0] != settings["transactions"]):
                raise DemoError(f"Demo database is incomplete: {database}. Existing files were preserved; choose a new --demo-dir.")
    except sqlite3.Error as error:
        raise DemoError(f"Cannot read demo database {database}: {error}. Choose a new --demo-dir.") from error


def prepare_demo(demo_dir=DEFAULT_DIR, transactions=50000, seed=42,
                 config_path=ROOT / "config" / "rules.json"):
    """Publish a complete fresh demo, or validate/reuse an existing owned snapshot.

    Reuse never regenerates CSVs. The importer refuses different source data, and
    detector deduplication retains saved review history and case statuses.
    """
    if type(transactions) is not int or transactions < 19:
        raise DemoError("All four seeded scenarios require --transactions >= 19")
    if type(seed) is not int:
        raise DemoError("Seed must be an integer")
    registry = rule_registry()
    # Validate every rule before preparing files or writing any alerts.
    parameters = {rule: load_parameters(config_path, rule) for rule in registry}
    folder = demo_path(demo_dir)
    settings = {"format_version": 1, "transactions": transactions,
                "seed": seed, "all_scenarios": True}
    folder.parent.mkdir(parents=True, exist_ok=True)
    with preparation_lock(folder):
        reused = folder.exists()
        if reused:
            existing_snapshot(folder, settings)
            snapshot = load_dataset(folder, folder / "banking.db")
            results = [detect(folder / "banking.db", **parameters[rule])
                       for rule, (detect, _, _) in registry.items()]
        else:
            # A failed fresh generation/import/detection leaves no partial demo folder.
            with tempfile.TemporaryDirectory(prefix="demo-prepare-", dir=folder.parent) as temporary:
                stage = Path(temporary)
                create_dataset(transactions, seed=seed, output_dir=stage,
                               include_r001=True, include_r003=True, include_r004=True)
                snapshot = load_dataset(stage, stage / "banking.db")
                results = [detect(stage / "banking.db", **parameters[rule])
                           for rule, (detect, _, _) in registry.items()]
                (stage / SETTINGS_FILE).write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
                if folder.exists():
                    raise DemoError(f"{folder} appeared during preparation; existing files were preserved")
                stage.rename(folder)
    return {"db_path": folder / "banking.db", "reused": reused,
            "snapshot": snapshot, "rules": results}


def wait_for_server(process, url, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise DemoError(f"Dashboard server exited before startup (exit code {process.returncode})")
        try:
            with urllib.request.urlopen(url + "/_stcore/health", timeout=1) as response:
                if response.status == 200 and response.read().strip() == b"ok":
                    return
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(0.2)
    raise DemoError("Dashboard server did not become healthy within 30 seconds; see its output above")


def launch_dashboard(db_path, port=8501, open_browser=True):
    check_port(port)
    environment = os.environ.copy()
    environment["BANKING_RISK_DB"] = str(Path(db_path).resolve())
    command = [sys.executable, "-m", "streamlit", "run", str(ROOT / "app.py"),
               "--server.address", "127.0.0.1", "--server.port", str(port),
               "--server.headless", "true"]
    process = subprocess.Popen(command, cwd=ROOT, env=environment)
    url = f"http://127.0.0.1:{port}"
    try:
        wait_for_server(process, url)
        print(f"\nDashboard ready: {url}\nDatabase: {db_path}\nPress Ctrl+C to stop.", flush=True)
        if open_browser:
            try:
                opened = webbrowser.open(url)
            except webbrowser.Error:
                opened = False
            if not opened:
                print(f"Open {url} in your browser to view the demo.", flush=True)
        return process.wait()
    except KeyboardInterrupt:
        return 0
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo-dir", type=Path, default=DEFAULT_DIR,
                        help="Dedicated snapshot folder; relative paths resolve from the repository root")
    parser.add_argument("--transactions", type=int, default=50000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument("--no-browser", action="store_true", help="Print the URL without opening a browser")
    parser.add_argument("--prepare-only", action="store_true", help="Prepare data and alerts without starting Streamlit")
    args = parser.parse_args(argv)
    try:
        if sys.version_info < (3, 10):
            raise DemoError("Python 3.10 or newer is required")
        if not args.prepare_only:
            check_dependencies()
            check_port(args.port)
        print("Preparing four-rule synthetic demo...", flush=True)
        result = prepare_demo(args.demo_dir, args.transactions, args.seed)
        action = "Reused" if result["reused"] else "Prepared"
        snapshot = result["snapshot"]
        print(f"{action}: {snapshot['customers']} customers, {snapshot['accounts']} accounts, "
              f"{snapshot['transactions']:,} transactions\nDatabase: {result['db_path']}", flush=True)
        for rule in result["rules"]:
            print(f"{rule['rule_id']}: {rule['matched_events']} matched, "
                  f"{rule['new_alerts']} new, {rule['existing_alerts']} already saved", flush=True)
        if result["reused"]:
            print("Existing CSVs, case statuses and review history retained.", flush=True)
        if args.prepare_only:
            return 0
        return launch_dashboard(result["db_path"], args.port, not args.no_browser)
    except KeyboardInterrupt:
        print("\nPreparation interrupted. Run the command again to reuse a completed demo.", file=sys.stderr)
        return 130
    except (ValueError, OSError, sqlite3.Error, csv.Error) as error:
        print(f"Demo failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
