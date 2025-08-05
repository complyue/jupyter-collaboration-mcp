# AI Agent Guide for Jupyter Collaboration MCP Server

This guide provides AI agents with the essential information needed to understand, contribute to, and work effectively with the Jupyter Collaboration MCP Server project.

## Project Overview

The Jupyter Collaboration MCP Server is a JupyterLab extension that provides MCP (Model Context Protocol) server endpoints to expose Jupyter Collaboration's real-time collaboration (RTC) functionalities to AI agents. This project enables AI agents to interact with collaborative Jupyter notebooks and documents in real-time, leveraging the existing Jupyter Collaboration system's robust RTC capabilities using YDoc (CRDT) technology.

### Key Concepts for AI Agents

1. **MCP (Model Context Protocol)**: The communication standard between AI agents and the server
2. **RTC (Real-Time Collaboration)**: The underlying technology enabling multiple users to collaborate simultaneously
3. **YDoc**: CRDT (Conflict-free Replicated Data Type) technology used for synchronization
4. **Jupyter Collaboration**: The existing system providing collaborative features for Jupyter notebooks

## Project Structure

Based on the design document, the project follows this structure:

```
jupyter-collaboration-mcp/
├── pyproject.toml
├── setup.py
├── jupyter_collaboration_mcp/
│   ├── __init__.py
│   ├── __main__.py
│   ├── app.py              # Main MCP server application
│   ├── handlers.py         # MCP request handlers
│   ├── rtc_adapter.py      # Adapter to existing RTC functionality
│   ├── event_store.py     # For resumability
│   ├── auth.py            # Authentication and authorization
│   └── utils.py           # Utility functions
└── tests/
    ├── __init__.py
    ├── test_app.py
    ├── test_handlers.py
    └── test_auth.py
```

## Key Components

### 1. MCP Server (StreamableHTTP)
- Located in [`app.py`](jupyter_collaboration_mcp/app.py)
- Uses HTTP with Server-Sent Events (SSE) for real-time communication
- Based on the MCP StreamableHTTP example

### 2. RTC Adapter Layer
- Located in [`rtc_adapter.py`](jupyter_collaboration_mcp/rtc_adapter.py)
- Translates MCP requests into operations on the existing collaboration system
- Bridges the gap between MCP protocol and Jupyter Collaboration

### 3. Event Store
- Located in [`event_store.py`](jupyter_collaboration_mcp/event_store.py)
- Provides resumability and state management
- Similar to the example's `InMemoryEventStore`

### 4. Authentication & Authorization
- Located in [`auth.py`](jupyter_collaboration_mcp/auth.py)
- Integrated with Jupyter's existing security infrastructure
- Uses simple token-based authentication

## MCP Endpoints

### Notebook Operations

The server exposes the following MCP tools for notebook collaboration:

- `list_notebooks`: List available notebooks
- `get_notebook`: Get notebook content
- `create_notebook_session`: Create or retrieve a collaboration session
- `update_notebook_cell`: Update a notebook cell
- `insert_notebook_cell`: Insert a new cell
- `delete_notebook_cell`: Delete a cell
- `execute_notebook_cell`: Execute a cell

### Document Operations

The server exposes the following MCP tools for document collaboration:

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

The server exposes the following MCP tools for user awareness:

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

- Python 3.8 or higher
- Jupyter Server 2.0.0 or higher
- Jupyter Collaboration 2.0.0 or higher

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/jupyter/jupyter-collaboration-mcp.git
   cd jupyter-collaboration-mcp
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -e ".[dev]"
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

## Authentication

All MCP requests must include a token in the Authorization header:

```
Authorization: Identity.token your-secret-token
```

The token must match the one provided when starting Jupyter Lab with `--IdentityProvider.token=your-secret-token`. The server integrates with Jupyter's authentication system, using the same token for MCP requests.

## Code Quality and Testing

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

## Contributing

When contributing to this project:

1. Follow the development workflow outlined in the [README](README.md:289)
2. Ensure all tests pass
3. Maintain code quality standards (formatting, type checking)
4. Update documentation as needed
5. Follow the existing code patterns and architecture

## Common Tasks for AI Agents

### Adding New MCP Tools

1. Define the tool schema in the appropriate handler (notebook, document, or awareness)
2. Implement the tool logic in the handler class
3. Add corresponding methods to the RTC adapter if needed
4. Write tests for the new tool
5. Update documentation

### Modifying Existing Functionality

1. Identify the component to modify (handlers, RTC adapter, etc.)
2. Understand the existing implementation and its relation to the MCP protocol
3. Make changes while maintaining backward compatibility when possible
4. Update tests to reflect changes
5. Test with actual MCP clients if possible

### Debugging Issues

1. Enable debug logging:
   ```bash
   jupyter lab --IdentityProvider.token=your-token --log-level=DEBUG
   ```

2. Check authentication if receiving 401 errors
3. Check rate limiting if receiving 429 errors
3. Verify the RTC adapter is properly initialized
4. Check the event store for resumability issues
5. Use the test suite to isolate issues

## Integration with AI Systems

### MCP Client Configuration

To connect an AI agent to this MCP server:

```json
{
  "mcpServers": {
    "jupyter-collaboration": {
      "url": "http://localhost:8888/mcp",
      "headers": {
        "Authorization": "Identity.token your-secret-token"
      },
      "disabled": false
    }
  }
}
```

Replace `your-secret-token` with the actual token you used when starting Jupyter Lab.

### Example Use Cases

1. **AI Assistant Integration**: AI agents can view and edit notebooks in real-time alongside human users
2. **Automated Documentation**: AI can generate documentation while observing document changes
3. **Collaborative Analysis**: Multiple AI agents can collaborate on data analysis tasks
4. **Code Review Automation**: AI can provide real-time feedback on code changes

## Important Considerations

1. **Security**: Always follow Jupyter's security model and ensure proper authentication
2. **Token Management**: Ensure the token is kept secure and only shared with authorized clients
3. **Real-time Nature**: Remember that operations affect live collaboration sessions
4. **CRDT Operations**: Understand how YDoc operations work when modifying the RTC adapter
5. **Resumability**: Ensure the event store properly handles disconnections and reconnections
6. **Performance**: Consider the impact of operations on real-time collaboration

## Additional Resources

- [README.md](README.md): General project information and setup instructions
- [DESIGN.md](DESIGN.md): Detailed design document with architecture and implementation plans
- [Jupyter Collaboration](https://github.com/jupyter/jupyter-collaboration): The underlying RTC functionality
- [Model Context Protocol (MCP)](https://modelcontextprotocol.io/): The AI agent communication standard
