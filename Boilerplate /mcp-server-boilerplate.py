import asyncio
import json
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import Response, StreamingResponse
from starlette.requests import Request
import uvicorn
import argparse
from pydantic import BaseModel, Field, ValidationError


class BaseTool(ABC):
    """Abstract base class for MCP tools."""
    
    def __init__(
        self,
        name: str,
        description: str,
        input_schema: Dict[str, Any]
    ):
        """
        Initialize a tool.
        
        Args:
            name: Unique name of the tool
            description: Description of what the tool does
            input_schema: JSON schema for the tool's input parameters
        """
        self.name = name
        self.description = description
        self.input_schema = input_schema
    
    def to_mcp_tool(self) -> types.Tool:
        """Convert this tool to an MCP Tool type."""
        return types.Tool(
            name=self.name,
            description=self.description,
            inputSchema=self.input_schema
        )
    
    @abstractmethod
    async def execute(self, arguments: Dict[str, Any]) -> List[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        """
        Execute the tool with given arguments.
        
        Args:
            arguments: Tool arguments as a dictionary
            
        Returns:
            List of content items (text, image, or embedded resource)
            
        Raises:
            ValueError: If required arguments are missing or invalid
            Exception: For any execution errors
        """
        pass


# Global registry for tools (used by MCP server handlers)
_tools_registry: Dict[str, BaseTool] = {}

# Global server configuration (set in main())
_server_name: str = ""
_server_version: str = ""

# Create MCP server instance (name is just for identification, actual config is in globals)
mcp_server = Server("mcp-server")


@mcp_server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """List available tools."""
    return [tool.to_mcp_tool() for tool in _tools_registry.values()]


@mcp_server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Handle tool execution requests."""
    
    if name not in _tools_registry:
        raise ValueError(f"Unknown tool: {name}")
    
    if arguments is None:
        arguments = {}
    
    tool = _tools_registry[name]
    return await tool.execute(arguments)


# Store active sessions
sessions = {}


async def handle_sse(request: Request):
    """Handle SSE connections for MCP - GET request."""
    
    async def event_stream():
        """Generate SSE events."""
        session_id = id(request)
        
        # Send initial connection message
        yield f"data: {json.dumps({'type': 'connected'})}\n\n"
        
        try:
            # Keep connection alive
            while True:
                await asyncio.sleep(15)  # Send keepalive every 15 seconds
                yield f": keepalive\n\n"
        except asyncio.CancelledError:
            if session_id in sessions:
                del sessions[session_id]
    
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


async def handle_messages(request: Request):
    """Handle incoming POST messages from MCP clients."""
    try:
        body = await request.json()
        
        # Process MCP protocol messages
        method = body.get("method")
        
        if method == "tools/list":
            tools = await handle_list_tools()
            response = {
                "jsonrpc": "2.0",
                "id": body.get("id"),
                "result": {
                    "tools": [
                        {
                            "name": tool.name,
                            "description": tool.description,
                            "inputSchema": tool.inputSchema
                        }
                        for tool in tools
                    ]
                }
            }
        elif method == "tools/call":
            params = body.get("params", {})
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            
            result = await handle_call_tool(tool_name, arguments)
            
            response = {
                "jsonrpc": "2.0",
                "id": body.get("id"),
                "result": {
                    "content": [
                        {"type": "text", "text": content.text}
                        for content in result
                    ]
                }
            }
        elif method == "initialize":
            response = {
                "jsonrpc": "2.0",
                "id": body.get("id"),
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {}
                    },
                    "serverInfo": {
                        "name": _server_name,
                        "version": _server_version
                    }
                }
            }
        else:
            response = {
                "jsonrpc": "2.0",
                "id": body.get("id"),
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}"
                }
            }
        
        return Response(
            content=json.dumps(response),
            media_type="application/json"
        )
    
    except Exception as e:
        return Response(
            content=json.dumps({
                "jsonrpc": "2.0",
                "id": body.get("id") if "body" in locals() else None,
                "error": {
                    "code": -32603,
                    "message": f"Internal error: {str(e)}"
                }
            }),
            media_type="application/json",
            status_code=500
        )


async def health_check(request: Request):
    """Health check endpoint."""
    return Response(
        content=json.dumps({
            "status": "healthy",
            "service": _server_name,
            "version": _server_version
        }),
        media_type="application/json"
    )


async def handle_root(request: Request):
    """Handle root endpoint - serves as both info page and message handler."""
    if request.method == "GET":
        return Response(
            content=json.dumps({
                "service": f"{_server_name} MCP Server",
                "version": _server_version,
                "tools": list(_tools_registry.keys()),
                "endpoints": {
                    "/": "POST - MCP messages (JSON-RPC 2.0)",
                    "/sse": "GET - Server-Sent Events stream",
                    "/messages": "POST - Alternative message endpoint",
                    "/health": "GET - Health check"
                }
            }),
            media_type="application/json"
        )
    elif request.method == "POST":
        # Forward to message handler
        return await handle_messages(request)


# Example tool implementation (can be removed or kept as reference)
class ExampleTool(BaseTool):
    """Example tool implementation."""
    
    class InputSchema(BaseModel):
        message: str = Field(description="Message to echo back")
    
    def __init__(self):
        super().__init__(
            name="example_tool",
            description="An example tool that echoes back the input",
            input_schema=self.InputSchema.model_json_schema()
        )
    
    def validate_input(self, arguments: Dict[str, Any]) -> 'ExampleTool.InputSchema':
        """Validate and parse input arguments using Pydantic model."""
        try:
            return self.InputSchema(**arguments)
        except ValidationError as e:
            raise ValueError(f"Input validation error: {e}")
    
    async def execute(self, arguments: Dict[str, Any]) -> List[types.TextContent]:
        """Execute the example tool."""
        validated_input = self.validate_input(arguments)
        
        return [
            types.TextContent(
                type="text",
                text=f"Echo: {validated_input.message}"
            )
        ]


def main():
    """Main function to configure and run the MCP server."""
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Generic MCP Server")
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to run the server on (default: 8000)"
    )
    args = parser.parse_args()
    
    # ============================================
    # CONFIGURATION - Update these values as needed
    # ============================================
    global _server_name, _server_version
    
    _server_name = "my-mcp-server"  # Change this to your server name
    _server_version = "0.1.0"  # Change this to your server version
    
    # Register your tools here
    # Example:
    # tools = [
    #     ExampleTool(),
    #     YourCustomTool(),
    #     AnotherTool(),
    # ]
    tools = [
        ExampleTool(),  # Remove this and add your own tools
    ]
    
    # Register tools in the global registry
    for tool in tools:
        if tool.name in _tools_registry:
            raise ValueError(f"Tool '{tool.name}' is already registered")
        _tools_registry[tool.name] = tool
    # ============================================
    
    # Create the Starlette application
    app = Starlette(
        routes=[
            Route("/", endpoint=handle_root, methods=["GET", "POST"]),
            Route("/sse", endpoint=handle_sse, methods=["GET"]),
            Route("/messages", endpoint=handle_messages, methods=["POST"]),
            Route("/health", endpoint=health_check, methods=["GET"]),
        ]
    )
    
    # Print startup information
    print(f"Starting {_server_name} MCP Server on http://0.0.0.0:{args.port}")
    print(f"Version: {_server_version}")
    print(f"Registered tools: {', '.join(_tools_registry.keys())}")
    print(f"SSE endpoint: http://0.0.0.0:{args.port}/sse (GET)")
    print(f"Messages endpoint: http://0.0.0.0:{args.port}/messages (POST)")
    print(f"Health check: http://0.0.0.0:{args.port}/health")
    
    # Run the server
    uvicorn.run(app, host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    main()
