# Jupyter Collaboration MCP Server

A JupyterLab extension that provides MCP (Model Context Protocol) server endpoints to expose Jupyter Collaboration's real-time collaboration (RTC) functionalities to AI agents.

## Overview

This project enables AI agents to interact with collaborative Jupyter notebooks and documents in real-time. It leverages the existing Jupyter Collaboration system's robust RTC capabilities using YDoc (CRDT) technology and exposes them through MCP endpoints.

## Features

- **Notebook Collaboration**: Real-time collaboration on Jupyter notebooks with AI agents
- **Document Collaboration**: Shared document editing with version control and forking
- **User Awareness**: Track user presence, cursor positions, and activity
- **Real-time Communication**: Streamable HTTP for bidirectional communication
- **Authentication & Authorization**: Integrated with Jupyter's security infrastructure
- **Resumable Streams**: Clients can reconnect and resume from where they left off

## Installation

### Prerequisites

- Python 3.10 or higher
- Jupyter Server 2.0.0 or higher
- Jupyter Collaboration 2.0.0 or higher

### From Conda (when published)

```bash
conda install -c conda-forge jupyter-collaboration-mcp
```

### From PyPI (when published)

```bash
pip install jupyter-collaboration-mcp
```

### From Source

```bash
git clone https://github.com/jupyter/jupyter-collaboration-mcp.git
cd jupyter-collaboration-mcp
pip install -e .
```

## Configuration

The MCP server is automatically loaded as a Jupyter server extension when installed. No manual configuration is required.

## Authentication

The MCP server uses simple token-based authentication. When running as a Jupyter server extension, it automatically uses the token provided via the `--IdentityProvider.token` command line option.

### Using Jupyter Lab Tokens

When starting Jupyter Lab, you can provide a token for authentication:

```bash
jupyter lab --IdentityProvider.token=your-secret-token
```

This token can then be used to authenticate with the MCP server.

### MCP Client Configuration

For MCP clients, you'll need to configure the server URL and authentication token. The exact configuration depends on your MCP client, but it typically looks like this:

#### Example MCP Client Configuration

```json
{
  "mcpServers": {
    "jupyter-collaboration": {
      "url": "http://localhost:8888/mcp",
      "type": "streamable-http",
      "headers": {
        "Authorization": "Identity.token your-secret-token"
      },
      "disabled": false
    }
  }
}
```

#### Configuration Parameters

- `url`: The URL of the MCP server endpoint
- `type`: The transport type, must be "streamable-http" for this server
- `headers`: HTTP headers to include in requests, typically including the Authorization header with the token
- `disabled`: Set to `true` to disable this server configuration
- `alwaysAllow`: Optional list of tools that should always be allowed (if supported by your client)

### Finding Your Server URL

- When running as a Jupyter server extension, the MCP endpoint is typically at `http://localhost:8888/mcp` (or whatever port your Jupyter server is running on)

## Provided MCP Tools

The server exposes the following MCP tools:

### Notebook Operations

- `list_notebooks`: List available notebooks
- `get_notebook`: Get notebook content
- `create_notebook_session`: Create or retrieve a collaboration session
- `update_notebook_cell`: Update a notebook cell
- `insert_notebook_cell`: Insert a new cell
- `delete_notebook_cell`: Delete a cell
- `execute_notebook_cell`: Execute a cell

### Document Operations

- `list_documents`: List available documents
- `get_document`: Get document content
- `create_document_session`: Create or retrieve a collaboration session
- `update_document`: Update document content
- `insert_text`: Insert text at a position
- `delete_text`: Delete text from a position
- `get_document_history`: Get document version history
- `restore_document_version`: Restore a document to a previous version
- `fork_document`: Create a fork of a document
- `merge_document_fork`: Merge a fork back into the original

### Awareness Operations

- `get_online_users`: Get list of online users
- `get_user_presence`: Get user presence information
- `set_user_presence`: Set current user's presence status
- `get_user_cursors`: Get cursor positions in a document
- `update_cursor_position`: Update current user's cursor position
- `get_user_activity`: Get recent user activities
- `broadcast_user_activity`: Broadcast user activity
- `get_active_sessions`: Get active collaboration sessions
- `join_session`: Join a collaboration session
- `leave_session`: Leave a collaboration session

## Development Setup

### Prerequisites

- Python 3.10 or higher
- Git
- Node.js (for JupyterLab extension development, if needed)

### Clone the Repository

```bash
git clone https://github.com/jupyter/jupyter-collaboration-mcp.git
cd jupyter-collaboration-mcp
```

### Create a Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### Install Dependencies

```bash
pip install -e ".[dev]"
```

This will install the package in development mode along with all development dependencies.

### Code Formatting

The project uses Black for code formatting and isort for import sorting. You can format code manually:

```bash
black jupyter_collaboration_mcp tests
isort jupyter_collaboration_mcp tests
```

#### Auto-formatting on Commit

To set up automatic code formatting on each commit, run the setup script:

```bash
./scripts/setup-git-hooks.sh
```

This will set up a Git hook that automatically formats your Python files with black and isort before each commit.

### Type Checking

The project uses mypy for type checking:

```bash
mypy jupyter_collaboration_mcp
```

## Troubleshooting

### Common Issues

1. **Authentication Errors**: Make sure you're using the correct token in your Authorization header
2. **Connection Refused**: Verify that your Jupyter server is running and the MCP extension is loaded
3. **CORS Errors**: If running in a browser environment, make sure the server's CORS configuration allows your client's origin

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [Jupyter Collaboration](https://github.com/jupyter/jupyter-collaboration) for the underlying RTC functionality
- [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) for the AI agent communication standard
- [Jupyter Server](https://github.com/jupyter/jupyter_server) for the server infrastructure
