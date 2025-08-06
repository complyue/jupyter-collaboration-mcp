"""
Main entry point for the Jupyter Collaboration MCP Server.

This module provides a standalone server that can be run independently
or as a Jupyter server extension.
"""

import argparse
import logging
import sys

from jupyter_server.serverapp import ServerApp
from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop
from tornado.web import Application

from .app import MCPServer, MCPHandler

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def create_parser():
    """Create and configure the argument parser."""
    parser = argparse.ArgumentParser(
        description="Jupyter Collaboration MCP Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)")

    parser.add_argument("--port", type=int, default=8000, help="Port to bind to (default: 8000)")

    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)",
    )

    parser.add_argument("--jupyter-config", help="Path to Jupyter server configuration file")

    return parser

def run_standalone_server(host: str, port: int, jupyter_config: str = None):
    """Run the MCP server as a standalone application."""
    logger.info(f"Starting Jupyter Collaboration MCP Server on {host}:{port}")

    # Create a minimal Jupyter server app for RTC integration
    server_app = ServerApp.instance()
    if jupyter_config:
        server_app.load_config_file(jupyter_config)

    # Create and configure the MCP server
    mcp_server = MCPServer()
    
    # Initialize the RTC adapter
    IOLoop.current().run_sync(mcp_server.rtc_adapter.initialize, server_app)

    # Create Tornado application
    app = Application([
        (r"/mcp.*", MCPHandler, {"session_manager": mcp_server.session_manager})
    ])

    # Create HTTP server
    server = HTTPServer(app)
    server.listen(port, host)

    logger.info(f"MCP Server running at http://{host}:{port}/mcp")
    
    # Start the event loop
    IOLoop.current().start()


def main():
    """Main entry point for the standalone MCP server."""
    parser = create_parser()
    args = parser.parse_args()

    # Set log level
    logging.getLogger().setLevel(getattr(logging, args.log_level))

    try:
        # Run the server
        run_standalone_server(
            host=args.host, port=args.port, jupyter_config=args.jupyter_config
        )
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
