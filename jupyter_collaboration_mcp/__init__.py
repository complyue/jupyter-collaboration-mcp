"""
Jupyter Collaboration MCP Server

A JupyterLab extension that provides MCP (Model Context Protocol) server endpoints
to expose Jupyter Collaboration's real-time collaboration (RTC) functionalities to AI agents.
"""

from typing import Any, Dict, List

from .app import MCPServerExtension

__version__ = "0.1.0"


def _jupyter_server_extension_points():
    """Jupyter server extension points."""
    return [{"module": "jupyter_collaboration_mcp", "app": MCPServerExtension}]


# JupyterLab extension entry point
def _jupyter_lab_extension_paths():
    """Returns the paths to the JupyterLab extension."""
    return []