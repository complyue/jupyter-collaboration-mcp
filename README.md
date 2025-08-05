# Jupyter Collaboration MCP Server

A JupyterLab extension that provides MCP (Model Context Protocol) server endpoints to expose Jupyter Collaboration's real-time collaboration (RTC) functionalities to AI agents.

## Overview

This project enables AI agents to interact with collaborative Jupyter notebooks and documents in real-time. It leverages the existing Jupyter Collaboration system's robust RTC capabilities using YDoc (CRDT) technology and exposes them through MCP endpoints.

## Features

- **Notebook Collaboration**: Real-time collaboration on Jupyter notebooks with AI agents
- **Document Collaboration**: Shared document editing with version control and forking
- **User Awareness**: Track user presence, cursor positions, and activity
- **Real-time Communication**: Server-sent events for live updates
- **Authentication & Authorization**: Integrated with Jupyter's security infrastructure
- **Resumable Streams**: Clients can reconnect and resume from where they left off

## Installation

### Prerequisites

- Python 3.8 or higher
- Jupyter Server 2.0.0 or higher
- Jupyter Collaboration 2.0.0 or higher

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

The extension will be automatically loaded when you start Jupyter Server. No additional configuration is required.

## Configuration

The MCP server is automatically loaded as a Jupyter server extension when installed. No manual configuration is required.

### Standalone Server

You can also run the MCP server as a standalone application:

```bash
jupyter-collaboration-mcp --host 0.0.0.0 --port 8000
```

#### Command Line Options

```
--host HOST                Host to bind to (default: 127.0.0.1)
--port PORT                Port to bind to (default: 8000)
--log-level LEVEL         Logging level (default: INFO)
--jupyter-config PATH     Path to Jupyter server configuration file
```

## Authentication

The MCP server uses JWT tokens for authentication. When running as a Jupyter server extension, it automatically uses Jupyter's authentication system.

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
      "headers": {
        "Authorization": "Bearer your-secret-token"
      },
      "disabled": false
    }
  }
}
```

#### Configuration Parameters

- `url`: The URL of the MCP server endpoint
- `headers`: HTTP headers to include in requests, typically including the Authorization header with the JWT token
- `disabled`: Set to `true` to disable this server configuration
- `alwaysAllow`: Optional list of tools that should always be allowed (if supported by your client)

### Finding Your Server URL

- If running as a Jupyter server extension, the MCP endpoint is typically at `http://localhost:8888/mcp` (or whatever port your Jupyter server is running on)
- If running as a standalone server, the endpoint is at the host and port you specified when starting the server (e.g., `http://localhost:8000/mcp`)

## Development Setup

### Prerequisites

- Python 3.8 or higher
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

### Running Tests

```bash
pytest
```

### Code Formatting

The project uses Black for code formatting and isort for import sorting:

```bash
black jupyter_collaboration_mcp tests
isort jupyter_collaboration_mcp tests
```

### Type Checking

The project uses mypy for type checking:

```bash
mypy jupyter_collaboration_mcp
```

### Running in Development Mode

#### As a Jupyter Server Extension

```bash
# Start Jupyter server with the extension and a token
# The extension is automatically loaded when installed
jupyter lab --IdentityProvider.token=dev-token
```

#### As a Standalone Server

```bash
# Run the MCP server in development mode
python -m jupyter_collaboration_mcp --host 127.0.0.1 --port 8000 --log-level DEBUG
```

## API Usage

### MCP Tools

The server exposes the following MCP tools:

#### Notebook Operations

- `list_notebooks`: List available notebooks
- `get_notebook`: Get notebook content
- `create_notebook_session`: Create or retrieve a collaboration session
- `update_notebook_cell`: Update a notebook cell
- `insert_notebook_cell`: Insert a new cell
- `delete_notebook_cell`: Delete a cell
- `execute_notebook_cell`: Execute a cell

#### Document Operations

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

#### Awareness Operations

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

### MCP Resources

The server exposes the following MCP resources for real-time updates:

- `collaboration://notebooks`: Notebook resources
- `collaboration://documents`: Document resources
- `collaboration://awareness`: User awareness resources

### Authentication

All MCP requests must include a JWT token in the Authorization header:

```
Authorization: Bearer your-secret-token
```

## Example Usage

### MCP Client Configuration Example

Here's a complete example of how to configure an MCP client to connect to the Jupyter Collaboration MCP Server:

```json
{
  "mcpServers": {
    "jupyter-collaboration": {
      "url": "http://localhost:8888/mcp",
      "headers": {
        "Authorization": "Bearer your-secret-token"
      },
      "disabled": false
    }
  }
}
```

Replace `your-secret-token` with the actual token you used when starting Jupyter Lab.

### Testing the Connection

Once configured, you can test the connection by listing available notebooks through your MCP client. The exact method depends on your client, but it typically involves calling the `list_notebooks` tool.

## Troubleshooting

### Common Issues

1. **Authentication Errors**: Make sure you're using the correct token in your Authorization header
2. **Connection Refused**: Verify that your Jupyter server is running and the MCP extension is loaded
3. **CORS Errors**: If running in a browser environment, make sure the server's CORS configuration allows your client's origin

### Debug Mode

To enable debug logging, you can:

1. Set the log level to DEBUG when starting the server:
   ```bash
   jupyter lab --IdentityProvider.token=your-token --log-level=DEBUG
   ```

2. Or add this to your `jupyter_server_config.py`:
   ```python
   c.Application.log_level = 'DEBUG'
   ```

## Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Development Workflow

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests and ensure code quality (`pytest`, `black`, `isort`, `mypy`)
5. Commit your changes (`git commit -m 'Add some amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## License

This project is licensed under the BSD 3-Clause License - see the [LICENSE](LICENSE) file for details.

## Support

- Documentation: [Jupyter Collaboration MCP Server Documentation](https://jupyter-collaboration-mcp.readthedocs.io)
- Issues: [GitHub Issues](https://github.com/jupyter/jupyter-collaboration-mcp/issues)
- Discussions: [GitHub Discussions](https://github.com/jupyter/jupyter-collaboration-mcp/discussions)

## Acknowledgments

- [Jupyter Collaboration](https://github.com/jupyter/jupyter-collaboration) for the underlying RTC functionality
- [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) for the AI agent communication standard
- [Jupyter Server](https://github.com/jupyter/jupyter_server) for the server infrastructure
