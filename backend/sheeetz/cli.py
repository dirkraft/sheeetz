"""CLI for managing the sheeetz dev stack."""

import argparse
import subprocess
import sys


SESSION = "sheeetz"


def tmux(*args: str) -> int:
    return subprocess.call(["tmux", *args])


def is_session_running() -> bool:
    return subprocess.call(
        ["tmux", "has-session", "-t", SESSION],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ) == 0


def cmd_up(args: argparse.Namespace) -> None:
    if is_session_running():
        if args.restart:
            tmux("kill-session", "-t", SESSION)
        else:
            print(f"tmux session '{SESSION}' is already running. Attach with: tmux attach -t {SESSION}")
            print(f"  Use --restart / -r to replace it.")
            return

    # Resolve paths relative to this file (backend/sheeetz/cli.py → backend/)
    from pathlib import Path
    backend_dir = Path(__file__).resolve().parent.parent
    frontend_dir = backend_dir.parent / "frontend"

    backend_cmd = f"cd {backend_dir} && .venv/bin/uvicorn sheeetz.main:app --port 8000 --reload"
    frontend_cmd = f"cd {frontend_dir} && npm run dev"

    # Create session with backend in first window
    tmux("new-session", "-d", "-s", SESSION, "-n", "backend", backend_cmd)
    # Add frontend in second window
    tmux("new-window", "-t", SESSION, "-n", "frontend", frontend_cmd)
    # Select backend window
    tmux("select-window", "-t", f"{SESSION}:backend")

    print(f"Started sheeetz dev stack in tmux session '{SESSION}'")
    print(f"  Attach: tmux attach -t {SESSION}")
    print(f"  Backend: http://localhost:8000")
    print(f"  Frontend: http://localhost:5173")


def cmd_down(args: argparse.Namespace) -> None:
    if not is_session_running():
        print(f"No tmux session '{SESSION}' running.")
        return
    tmux("kill-session", "-t", SESSION)
    print(f"Stopped sheeetz dev stack.")


def cmd_status(args: argparse.Namespace) -> None:
    if is_session_running():
        print(f"sheeetz is running.")
        tmux("list-windows", "-t", SESSION)
    else:
        print(f"sheeetz is not running.")


def main() -> None:
    parser = argparse.ArgumentParser(prog="sheeetz", description="Sheeetz dev stack manager")
    sub = parser.add_subparsers(dest="command")

    up_parser = sub.add_parser("up", help="Start the dev stack in a tmux session")
    up_parser.add_argument("-r", "--restart", action="store_true", help="Kill existing session and restart")
    sub.add_parser("down", help="Stop the dev stack")
    sub.add_parser("status", help="Check if the dev stack is running")

    args = parser.parse_args()

    commands = {"up": cmd_up, "down": cmd_down, "status": cmd_status}
    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
