import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(pathname)s:%(lineno)d\n  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stderr)],
)


for ln in (
    # "mcp",
    "jupyter_collaboration_mcp",
):
    logger = logging.getLogger(ln)
    logger.setLevel(logging.DEBUG)


sys.argv[:] = ["jupyter-lab", "--ip=127.0.0.1", "--no-browser", "--IdentityProvider.token=''"]

import jupyterlab.labapp

jupyterlab.labapp.main()
