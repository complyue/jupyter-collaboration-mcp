from setuptools import setup, find_packages

setup(
    name="jupyter-collaboration-mcp",
    version="0.1.0",
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        "jupyter-server>=2.0.0",
        "jupyter-collaboration>=2.0.0",
        "mcp>=1.0.0",
        "starlette>=0.27.0",
        "uvicorn>=0.23.0",
        "pydantic>=2.0.0",
        "anyio>=4.0.0",
        "pyjwt>=2.8.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.21.0",
            "black>=23.0.0",
            "isort>=5.12.0",
            "flake8>=6.0.0",
            "mypy>=1.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "jupyter-collaboration-mcp=jupyter_collaboration_mcp.__main__:main",
        ],
        "jupyter_serverextensions": [
            "jupyter_collaboration_mcp = jupyter_collaboration_mcp:_load_jupyter_server_extension",
        ],
    },
    author="Jupyter Collaboration Team",
    author_email="jupyter@googlegroups.com",
    description="MCP server for Jupyter Collaboration features",
    long_description=open("DESIGN.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/jupyter/jupyter-collaboration-mcp",
    project_urls={
        "Documentation": "https://jupyter-collaboration-mcp.readthedocs.io",
        "Source": "https://github.com/jupyter/jupyter-collaboration-mcp",
        "Tracker": "https://github.com/jupyter/jupyter-collaboration-mcp/issues",
    },
    license="BSD-3-Clause",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: BSD License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.8",
)