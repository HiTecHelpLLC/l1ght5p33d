"""Launch with the installed dependency set, before importing the Flow runtime."""

import subprocess
import sys


def main() -> int:
    if not sys.flags.isolated or (sys.platform == "win32" and not sys.flags.utf8_mode):
        child = subprocess.Popen(
            [sys.executable, "-I", "-X", "utf8", "-m", "l1ght5p33d", *sys.argv[1:]]
        )
        try:
            return child.wait()
        except KeyboardInterrupt:
            # Console cancellation reaches the child too. Allow its verification
            # and checkpoint shutdown to finish instead of killing a UI write.
            try:
                child.wait(timeout=60)
            except subprocess.TimeoutExpired:
                print(
                    "Runner still shutting down; inspect its receipt.", file=sys.stderr
                )
            return 130
    from l1ght5p33d.cli import main as run_cli

    return run_cli()


if __name__ == "__main__":
    raise SystemExit(main())
