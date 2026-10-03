"""Prepare an isolated pinned Bend checkout and run step 2 regressions."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PIN = "7d24b8d0235cb9781140512c0f163c48ea84a719"
SOURCE = ROOT / "compiler-patches/step-02-known-callbacks"
PATCH = SOURCE / "compiler.patch"
CHECKOUT = ROOT / "build/bend-steps/step-02/bend"


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
        raise RuntimeError("step 2 requires its pinned revision; existing checkout was preserved")
    if git(CHECKOUT, "apply", "--reverse", "--check", str(PATCH), check=False).returncode:
        # --check refuses conflicting edits; never reset an existing experiment.
        git(CHECKOUT, "apply", "--check", str(PATCH))
        git(CHECKOUT, "apply", str(PATCH))
    return CHECKOUT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("setup", "check", "check-upstream"))
    args = parser.parse_args()
    if args.action == "setup":
        print(prepare())
    else:
        repo = Path(os.environ["BEND_REPO"]).resolve() if "BEND_REPO" in os.environ else prepare()
        env = {**os.environ, "BEND_REPO": str(repo), "BEND_NO_TELEMETRY": "1"}
        test = SOURCE / "check-upstream.py" if args.action == "check-upstream" else ROOT / "tests/bend_step02.py"
        return subprocess.run(["python3", str(test)], env=env).returncode
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as error:
        sys.exit(str(error))
