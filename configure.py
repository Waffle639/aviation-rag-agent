"""
Unified project setup: database schema + security model, one entrypoint.

Usage:
    python configure.py           guided, asks before installing/downloading
    python configure.py --check   verify only, exit 1 if anything is missing
    python configure.py --db      database schema only
    python configure.py --model   security model only
"""

import argparse
import importlib
import os
import shutil
import subprocess
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


class Step:
    def __init__(self, name, check, fix=None, prompt=None):
        self.name = name
        self.check = check
        self.fix = fix
        self.prompt = prompt

    def run(self):
        try:
            return self.check()
        except Exception as e:
            return False, str(e)


def _pad(name, width=44):
    return (name + " ").ljust(width, ".")


def _ask(prompt):
    try:
        return input(f"      {prompt} [y/N] ").strip().lower() in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        print()
        return False


def _check_env():
    if os.path.exists(os.path.join(PROJECT_ROOT, ".env")):
        return True, ".env exists."
    return False, ".env is missing."


def _setup_env():
    src = os.path.join(PROJECT_ROOT, ".env.example")
    dst = os.path.join(PROJECT_ROOT, ".env")
    if not os.path.exists(src):
        return False, ".env.example not found."
    shutil.copy(src, dst)
    return True, ".env created from template. Fill in your keys."


def _check_db():
    from ingestion.setup_database import verify_schema
    return verify_schema()


def _setup_db():
    try:
        subprocess.check_call([sys.executable, "-m", "ingestion.setup_database"])
        return _check_db()
    except subprocess.CalledProcessError as e:
        return False, f"Database setup failed: {e}"


def _security():
    return importlib.import_module("rag.setup_security")


STEPS = [
    Step(".env template", _check_env, _setup_env, "Copy .env.example → .env?"),
    Step("Database schema", _check_db, _setup_db, "Apply schema.sql?"),
    Step("Security dependencies", lambda: _security().check_torch(),
         lambda: _security().install_torch(),
         "Install torch (CPU wheel) + transformers (~200MB)?"),
    Step("HF_TOKEN", lambda: _security().check_hf_token()),
    Step("Model license", lambda: _security().check_license()),
    Step("Prompt Guard model", lambda: _security().check_model(),
         lambda: _security().download_model(),
         "Download Prompt Guard 2 86M (~350MB)?"),
    Step("Smoke test", lambda: _security().smoke_test()),
]


def _run_check():
    all_ok = True
    for step in STEPS:
        ok, msg = step.run()
        print(f"  {'ok' if ok else 'MISSING':8s} {step.name}")
        if not ok:
            print(f"           {msg}")
            all_ok = False
    return all_ok


def _run_interactive(steps):
    print("\nAviation RAG — project setup")
    print("─" * 30)
    ok_count = missing = 0
    for i, step in enumerate(steps, 1):
        label = _pad(f"[{i}/{len(steps)}] {step.name}")
        ok, msg = step.run()
        if ok:
            print(f"  {label} ok")
            ok_count += 1
            continue
        if step.fix and step.prompt:
            print(f"  {label} not ready")
            if _ask(step.prompt):
                ok, msg = step.fix()
                if ok:
                    print(f"  {label} ok")
                    ok_count += 1
                    continue
        print(f"  {label} missing")
        print(f"           {msg}")
        missing += 1
    print(f"\nDone: {ok_count} ok, {missing} to resolve.")
    return missing == 0


def main():
    parser = argparse.ArgumentParser(description="Aviation RAG — project setup.")
    parser.add_argument("--check", action="store_true",
                        help="verify only, exit non-zero if anything is missing")
    parser.add_argument("--db", action="store_true", help="database schema only")
    parser.add_argument("--model", action="store_true", help="security model only")
    args = parser.parse_args()

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    if args.check:
        ok = _run_check()
        if not ok:
            print("\nRun 'python configure.py' to fix interactively.")
        sys.exit(0 if ok else 1)

    if args.db:
        ok = _run_interactive([STEPS[1]])
        sys.exit(0 if ok else 1)

    if args.model:
        ok = _run_interactive(STEPS[2:])
        sys.exit(0 if ok else 1)

    ok = _run_interactive(STEPS)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
