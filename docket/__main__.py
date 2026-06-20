"""CLI dispatch: `docket tui` | `docket serve [--port] [--registry]`."""
import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="docket", description=__doc__)
    parser.add_argument("--registry", help="path to projects.json")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("tui", help="launch the Textual terminal UI")

    serve = sub.add_parser("serve", help="launch the localhost browser server")
    serve.add_argument("--port", type=int, default=8765)

    args = parser.parse_args(argv)

    if args.command == "tui":
        from docket.tui import run_tui
        return run_tui(registry=args.registry)
    if args.command == "serve":
        from docket.server import run_server
        return run_server(port=args.port, registry=args.registry)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
