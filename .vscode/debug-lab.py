import logging
import sys


# Configure logging for the mcp package and its subpackages to debug level
def configure_mcp_debug_logging():
    """Configure logging for the mcp package and its subpackages to debug level."""
    # Set up the root logger to a reasonable default (INFO)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    for ln in ("mcp", "jupyter_collaboration_mcp"):
        logger = logging.getLogger(ln)
        logger.setLevel(logging.DEBUG)


# Configure logging when this module is imported
configure_mcp_debug_logging()

sys.argv[:] = ["jupyter-lab", "--ip=127.0.0.1", "--no-browser", "--IdentityProvider.token=''"]

import jupyterlab.labapp

jupyterlab.labapp.main()
