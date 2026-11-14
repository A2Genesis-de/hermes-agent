"""``a2assistant logs`` subcommand parser."""

from __future__ import annotations

import argparse
from typing import Callable


def build_logs_parser(subparsers, *, cmd_logs: Callable) -> None:
    """Attach the ``logs`` subcommand to ``subparsers``."""
    logs_parser = subparsers.add_parser(
        "logs",
        help="View and filter A2Assistant log files",
        description="View, tail, and filter agent.log / errors.log / gateway.log / gui.log / desktop.log / update.log / desktop-update-handoff.log",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
    a2assistant logs                    Show last 50 lines of agent.log
    a2assistant logs -f                 Follow agent.log in real time
    a2assistant logs errors             Show last 50 lines of errors.log
    a2assistant logs gateway -n 100     Show last 100 lines of gateway.log
    a2assistant logs gui -f             Follow gui.log in real time
    a2assistant logs desktop -f         Follow desktop.log (Electron app boot/backend)
    a2assistant logs update             Show last 50 lines of update.log (a2assistant update mirror)
    a2assistant logs handoff            Show last 50 lines of desktop-update-handoff.log
    a2assistant logs --level WARNING    Only show WARNING and above
    a2assistant logs --session abc123   Filter by session ID
    a2assistant logs --component tools  Only show tool-related lines
    a2assistant logs --since 1h         Lines from the last hour
    a2assistant logs --since 30m -f     Follow, starting from 30 min ago
    a2assistant logs list               List available log files with sizes
""")
    logs_parser.add_argument(
        "log_name",
        nargs="?",
        default="agent",
        help="Log to view: agent (default), errors, gateway, gui, desktop, update, handoff, or 'list' to show available files",
    )
    logs_parser.add_argument(
        "-n", "--lines", type=int, default=50, help="Number of lines to show (default: 50)")
    logs_parser.add_argument(
        "-f", "--follow", action="store_true", help="Follow the log in real time (like tail -f)")
    logs_parser.add_argument(
        "--level", metavar="LEVEL", help="Minimum log level to show (DEBUG, INFO, WARNING, ERROR)")
    logs_parser.add_argument(
        "--session", metavar="ID", help="Filter lines containing this session ID substring")
    logs_parser.add_argument(
        "--since", metavar="TIME", help="Show lines since TIME ago (e.g. 1h, 30m, 2d)")
    logs_parser.add_argument(
        "--component", metavar="NAME",
        help="Filter by component: gateway, agent, tools, cli, cron, gui")
    logs_parser.set_defaults(func=cmd_logs)
