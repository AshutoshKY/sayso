"""Do not run the product on the host. The decide API lives in Docker."""

import sys


def main(argv=None):
    del argv
    print(
        "laya-app-opener does not run locally.\n"
        "Start the stack:\n"
        "  docker compose up -d\n"
        "  docker compose ps\n"
        "Then open the notch UI:\n"
        "  ./launch",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
