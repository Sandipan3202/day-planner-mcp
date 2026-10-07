"""focus-planner: a local MCP server that finds focus time in a day."""


def main() -> None:
    """Entry point: run the MCP server over stdio.

    Never print() here or anywhere in the server: stdout carries the
    JSON-RPC protocol. Log to stderr instead.
    """
    from focus_planner.server import run

    run()
