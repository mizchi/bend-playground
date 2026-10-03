"""Prepare an isolated pinned Bend checkout and run step 1 regressions."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PIN = "7d24b8d0235cb9781140512c0f163c48ea84a719"
SOURCE = ROOT / "compiler-patches/step-01-ffi-runtime-ids"
PATCH = SOURCE / "compiler.patch"
CHECKOUT = ROOT / "build/bend-steps/step-01/bend"


def git(repo, *args, check=True):
    result = subprocess.run(["git", "-C", str(repo), *args], text=True,
                            capture_output=True)
    if check and result.returncode:
        raise RuntimeError(result.stderr.strip())
    return result


def prepare():
    if not CHECKOUT.exists():
        CHECKOUT.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--no-hardlinks", "--no-checkout",
                        str(ROOT / "upstream/bend"), str(CHECKOUT)], check=True)
        git(CHECKOUT, "checkout", "--detach", PIN)
    if git(CHECKOUT, "rev-parse", "HEAD").stdout.strip() != PIN:
        raise RuntimeError("step 1 requires its pinned revision; existing checkout was preserved")
    if git(CHECKOUT, "apply", "--reverse", "--check", str(PATCH), check=False).returncode:
        # --check refuses conflicting edits; never reset an existing experiment.
        git(CHECKOUT, "apply", "--check", str(PATCH))
        git(CHECKOUT, "apply", str(PATCH))
    for fixture in SOURCE.glob("foreign_runtime_*.*"):
        if (CHECKOUT / "tests/io" / fixture.name).read_bytes() != fixture.read_bytes():
            raise RuntimeError("regression fixture differs from compiler.patch: " + fixture.name)
    return CHECKOUT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("setup", "check"))
    args = parser.parse_args()
    if args.action == "setup":
        print(prepare())
    else:
        repo = Path(os.environ["BEND_REPO"]).resolve() if "BEND_REPO" in os.environ else prepare()
        env = {**os.environ, "BEND_REPO": str(repo), "BEND_NO_TELEMETRY": "1"}
        return subprocess.run(["python3", str(ROOT / "tests/bend_step01.py")], env=env).returncode
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as error:
        sys.exit(str(error))
