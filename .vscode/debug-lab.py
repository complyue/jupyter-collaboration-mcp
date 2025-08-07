import logging
import sys

for ln in (
    # "mcp",
    "jupyter_collaboration_mcp",
):
    logger = logging.getLogger(ln)
    logger.setLevel(logging.DEBUG)


sys.argv[:] = ["jupyter-lab", "--ip=127.0.0.1", "--no-browser", "--IdentityProvider.token=''"]

import jupyterlab.labapp

jupyterlab.labapp.main()
