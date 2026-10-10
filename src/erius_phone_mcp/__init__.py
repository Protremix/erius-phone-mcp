"""ERIUS PHONE MCP server — a real Android device as MCP tools."""
__version__ = "0.2.0"  # set before importing .server, which reads it

from .server import main, mcp

__all__ = ["mcp", "main"]
