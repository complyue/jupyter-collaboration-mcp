"""
Jupyter Collaboration MCP Server

A JupyterLab extension that provides MCP (Model Context Protocol) server endpoints
to expose Jupyter Collaboration's real-time collaboration (RTC) functionalities to AI agents.
"""

__version__ = "0.1.0"


def _load_jupyter_server_extension(server_app):
    """Load the MCP server as a Jupyter server extension."""
    from .app import MCPServer
    
    # Create and configure the MCP server
    mcp_server = MCPServer()
    app = mcp_server.create_app()
    
    # Add the MCP server to the Jupyter server app
    server_app.web_app.add_handlers(
        host_pattern=r".*",
        handler_tuples=[(r"/mcp/.*", app)]
    )
    
    # Initialize the RTC adapter
    if hasattr(server_app, 'io_loop'):
        # For older Jupyter Server versions
        server_app.io_loop.add_callback(
            mcp_server.rtc_adapter.initialize,
            server_app
        )
    else:
        # For newer Jupyter Server versions
        import asyncio
        asyncio.create_task(mcp_server.rtc_adapter.initialize(server_app))
    
    server_app.log.info("Jupyter Collaboration MCP Server extension loaded")


# JupyterLab extension entry point
def _jupyter_lab_extension_paths():
    """Returns the paths to the JupyterLab extension."""
    return []