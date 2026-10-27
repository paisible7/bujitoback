"""Rewrite HEAD commit message without Co-authored-by trailer."""
from __future__ import annotations

import subprocess
import sys

GIT = r"C:\Program Files\Git\mingw64\bin\git.exe"


def run(args: list[str]) -> str:
    out = subprocess.check_output([GIT, *args], stderr=subprocess.STDOUT)
    return out.decode("utf-8", errors="replace").strip()


def main() -> int:
    tree = run(["rev-parse", "HEAD^{tree}"])
    parent = run(["HEAD~1"] if False else ["rev-parse", "HEAD~1"])
    author_name = run(["log", "-1", "--format=%an"])
    author_email = run(["log", "-1", "--format=%ae"])
    author_date = run(["log", "-1", "--format=%ad", "--date=raw"])
    msg = "feat: notifications client et admin pour expédition et arrivée entrepôt\n"
    env = {
        **dict(**{k: v for k, v in __import__("os").environ.items()}),
        "GIT_AUTHOR_NAME": author_name,
        "GIT_AUTHOR_EMAIL": author_email,
        "GIT_AUTHOR_DATE": author_date,
        "GIT_COMMITTER_NAME": author_name,
        "GIT_COMMITTER_EMAIL": author_email,
    }
    proc = subprocess.run(
        [GIT, "commit-tree", tree, "-p", parent, "-m", msg],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr or proc.stdout or "commit-tree failed\n")
        return proc.returncode
    new = (proc.stdout or "").strip()
    if not new or " " in new or len(new) < 7:
        sys.stderr.write(f"unexpected commit-tree output: {new!r}\n")
        return 1
    subprocess.check_call([GIT, "reset", "--soft", new])
    print(run(["log", "-1", "--format=full"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
