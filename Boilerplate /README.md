# MCP Server Boilerplate

A generic, class-based boilerplate for creating Model Context Protocol (MCP) servers with support for multiple tools. This boilerplate provides a clean, async-ready architecture that makes it easy to build and deploy custom MCP servers.

## Features

- 🏗️ **Class-based architecture** - Clean, maintainable code structure
- 🔧 **Multiple tool support** - Register and manage multiple tools easily
- ⚡ **Async-ready** - Built with async/await for optimal performance
- 🐳 **Docker support** - Ready-to-use Dockerfile for containerization
- 📝 **Easy configuration** - Configure server info and tools in the main function
- 🔌 **HTTP-based** - Uses Starlette and Uvicorn for HTTP server functionality
- 📡 **SSE support** - Server-Sent Events for real-time communication

## Installation

### Prerequisites

- Python 3.11 or higher
- pip

### Install Dependencies

```bash
pip install -r requirements.txt
```

## Quick Start

1. **Clone or copy the boilerplate files**

2. **Configure your server** in `mcp-server-boilerplate.py`:
   ```python
   SERVER_NAME = "my-mcp-server"
   SERVER_VERSION = "0.1.0"
   ```

3. **Create your custom tools** (see "Creating Custom Tools" below)

4. **Run the server**:
   ```bash
   python mcp-server-boilerplate.py
   # Or with custom port:
   python mcp-server-boilerplate.py --port 9000
   ```

## Creating Custom Tools

To create a custom tool, inherit from the `BaseTool` class and implement the `execute` method:

```python
from typing import Any, Dict, List
import mcp.types as types

class MyCustomTool(BaseTool):
    """My custom tool description."""
    
    def __init__(self):
        super().__init__(
            name="my_custom_tool",
            description="What my tool does",
            input_schema={
                "type": "object",
                "properties": {
                    "param1": {
                        "type": "string",
                        "description": "Description of param1"
                    },
                    "param2": {
                        "type": "integer",
                        "description": "Description of param2",
                        "default": 10
                    }
                },
                "required": ["param1"]
            }
        )
    
    async def execute(self, arguments: Dict[str, Any]) -> List[types.TextContent]:
        """Execute the tool asynchronously."""
        param1 = arguments.get("param1")
        param2 = arguments.get("param2", 10)
        
        if not param1:
            raise ValueError("Missing required argument: param1")
        
        # Your tool logic here
        result = f"Processed {param1} with {param2}"
        
        return [
            types.TextContent(
                type="text",
                text=result
            )
        ]
```

Then register it in the `main()` function:

```python
tools = [
    MyCustomTool(),
    AnotherTool(),
]
```

## Configuration

Edit the configuration section in the `main()` function:

```python
# ============================================
# CONFIGURATION - Update these values as needed
# ============================================
SERVER_NAME = "my-mcp-server"  # Change this to your server name
SERVER_VERSION = "0.1.0"  # Change this to your server version
PROTOCOL_VERSION = "2024-11-05"  # MCP protocol version

# Register your tools here
tools = [
    ExampleTool(),  # Remove this and add your own tools
]
# ============================================
```

## Running the Server

### Local Development

```bash
# Run with default port (8000)
python mcp-server-boilerplate.py

# Run with custom port
python mcp-server-boilerplate.py --port 9000
```

### Using Docker

#### Build the image:

```bash
docker build -t mcp-server-boilerplate .
```

#### Run the container:

```bash
# Run with default port (8000)
docker run -p 8000:8000 mcp-server-boilerplate

# Run with custom port
docker run -p 9000:9000 mcp-server-boilerplate --port 9000
```

The `--port` argument works the same way as running locally - it's passed directly to the Python script.

## API Endpoints

Once the server is running, the following endpoints are available:

- **`GET /`** - Server information and available endpoints
- **`POST /`** - MCP messages (JSON-RPC 2.0)
- **`GET /sse`** - Server-Sent Events stream
- **`POST /messages`** - Alternative message endpoint
- **`GET /health`** - Health check endpoint

### Example: Health Check

```bash
curl http://localhost:8000/health
```

Response:
```json
{
  "status": "healthy",
  "service": "my-mcp-server",
  "version": "0.1.0"
}
```

### Example: List Tools

```bash
curl -X POST http://localhost:8000/messages \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/list"
  }'
```

## Project Structure

```
Boilerplate/
├── mcp-server-boilerplate.py  # Main server code
├── requirements.txt            # Python dependencies
├── dockerfile                  # Docker configuration
└── README.md                   # This file
```

## Dependencies

- `mcp` - Model Context Protocol support
- `starlette` - Web framework
- `uvicorn[standard]` - ASGI server

## Architecture

### BaseTool

Abstract base class that all tools must inherit from. Provides:
- Tool metadata (name, description, input schema)
- Conversion to MCP Tool type
- Abstract `execute()` method for async tool execution

### MCPServer

Main server class that:
- Manages tool registration and execution
- Handles HTTP routing and MCP protocol messages
- Provides SSE support for real-time communication
- Manages server configuration and metadata

## Example: Complete Tool Implementation

Here's a complete example of a tool that performs a simple calculation:

```python
class CalculatorTool(BaseTool):
    """Performs basic arithmetic operations."""
    
    def __init__(self):
        super().__init__(
            name="calculator",
            description="Performs basic arithmetic: add, subtract, multiply, divide",
            input_schema={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["add", "subtract", "multiply", "divide"],
                        "description": "The operation to perform"
                    },
                    "a": {
                        "type": "number",
                        "description": "First number"
                    },
                    "b": {
                        "type": "number",
                        "description": "Second number"
                    }
                },
                "required": ["operation", "a", "b"]
            }
        )
    
    async def execute(self, arguments: Dict[str, Any]) -> List[types.TextContent]:
        operation = arguments.get("operation")
        a = arguments.get("a")
        b = arguments.get("b")
        
        if operation == "add":
            result = a + b
        elif operation == "subtract":
            result = a - b
        elif operation == "multiply":
            result = a * b
        elif operation == "divide":
            if b == 0:
                raise ValueError("Division by zero is not allowed")
            result = a / b
        else:
            raise ValueError(f"Unknown operation: {operation}")
        
        return [
            types.TextContent(
                type="text",
                text=f"Result: {result}"
            )
        ]
```

## License

This is a boilerplate template - customize as needed for your project.

## Contributing

Feel free to fork and modify this boilerplate for your own MCP server projects!

