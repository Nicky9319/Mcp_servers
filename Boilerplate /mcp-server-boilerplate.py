import asyncio
import json
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import mcp.types as types
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import Response, StreamingResponse
from starlette.requests import Request
import uvicorn
import argparse


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


class MCPServer:
    """Generic MCP Server that can handle multiple tools."""
    
    def __init__(
        self,
        server_name: str,
        server_version: str,
        protocol_version: str = "2024-11-05",
        tools: Optional[List[BaseTool]] = None
    ):
        """
        Initialize the MCP Server.
        
        Args:
            server_name: Name of the MCP server
            server_version: Version of the server
            protocol_version: MCP protocol version
            tools: List of tools to register
        """
        self.server_name = server_name
        self.server_version = server_version
        self.protocol_version = protocol_version
        self.tools: Dict[str, BaseTool] = {}
        self.sessions: Dict[int, Any] = {}
        
        # Register tools
        if tools:
            for tool in tools:
                self.register_tool(tool)
    
    def register_tool(self, tool: BaseTool):
        """Register a tool with the server."""
        if tool.name in self.tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")
        self.tools[tool.name] = tool
    
    def unregister_tool(self, tool_name: str):
        """Unregister a tool from the server."""
        if tool_name in self.tools:
            del self.tools[tool_name]
    
    async def list_tools(self) -> List[types.Tool]:
        """List all registered tools."""
        return [tool.to_mcp_tool() for tool in self.tools.values()]
    
    async def call_tool(
        self,
        name: str,
        arguments: Optional[Dict[str, Any]]
    ) -> List[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        """
        Call a registered tool.
        
        Args:
            name: Name of the tool to call
            arguments: Tool arguments
            
        Returns:
            List of content items from tool execution
        """
        if name not in self.tools:
            raise ValueError(f"Unknown tool: {name}")
        
        tool = self.tools[name]
        
        if arguments is None:
            arguments = {}
        
        # Execute tool asynchronously
        return await tool.execute(arguments)
    
    async def handle_sse(self, request: Request) -> StreamingResponse:
        """Handle SSE connections for MCP - GET request."""
        
        async def event_stream():
            """Generate SSE events."""
            session_id = id(request)
            self.sessions[session_id] = request
            
            # Send initial connection message
            yield f"data: {json.dumps({'type': 'connected'})}\n\n"
            
            try:
                # Keep connection alive
                while True:
                    await asyncio.sleep(15)  # Send keepalive every 15 seconds
                    yield f": keepalive\n\n"
            except asyncio.CancelledError:
                if session_id in self.sessions:
                    del self.sessions[session_id]
        
        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    
    async def handle_messages(self, request: Request) -> Response:
        """Handle incoming POST messages from MCP clients."""
        try:
            body = await request.json()
            
            # Process MCP protocol messages
            method = body.get("method")
            request_id = body.get("id")
            
            if method == "tools/list":
                tools = await self.list_tools()
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
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
                
                try:
                    result = await self.call_tool(tool_name, arguments)
                    response = {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {
                            "content": [
                                {"type": "text", "text": content.text}
                                if isinstance(content, types.TextContent)
                                else {"type": content.type, **content.__dict__}
                                for content in result
                            ]
                        }
                    }
                except Exception as e:
                    response = {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {
                            "code": -32603,
                            "message": f"Tool execution error: {str(e)}"
                        }
                    }
            elif method == "initialize":
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": self.protocol_version,
                        "capabilities": {
                            "tools": {}
                        },
                        "serverInfo": {
                            "name": self.server_name,
                            "version": self.server_version
                        }
                    }
                }
            else:
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
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
    
    async def health_check(self, request: Request) -> Response:
        """Health check endpoint."""
        return Response(
            content=json.dumps({
                "status": "healthy",
                "service": self.server_name,
                "version": self.server_version
            }),
            media_type="application/json"
        )
    
    async def handle_root(self, request: Request) -> Response:
        """Handle root endpoint - serves as both info page and message handler."""
        if request.method == "GET":
            return Response(
                content=json.dumps({
                    "service": f"{self.server_name} MCP Server",
                    "version": self.server_version,
                    "tools": list(self.tools.keys()),
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
            return await self.handle_messages(request)
    
    def create_app(self) -> Starlette:
        """Create and return the Starlette application."""
        return Starlette(
            routes=[
                Route("/", endpoint=self.handle_root, methods=["GET", "POST"]),
                Route("/sse", endpoint=self.handle_sse, methods=["GET"]),
                Route("/messages", endpoint=self.handle_messages, methods=["POST"]),
                Route("/health", endpoint=self.health_check, methods=["GET"]),
            ]
        )


# Example tool implementation (can be removed or kept as reference)
class ExampleTool(BaseTool):
    """Example tool implementation."""
    
    def __init__(self):
        super().__init__(
            name="example_tool",
            description="An example tool that echoes back the input",
            input_schema={
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "Message to echo back"
                    }
                },
                "required": ["message"]
            }
        )
    
    async def execute(self, arguments: Dict[str, Any]) -> List[types.TextContent]:
        """Execute the example tool."""
        message = arguments.get("message")
        if not message:
            raise ValueError("Missing required argument: message")
        
        return [
            types.TextContent(
                type="text",
                text=f"Echo: {message}"
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
    SERVER_NAME = "my-mcp-server"  # Change this to your server name
    SERVER_VERSION = "0.1.0"  # Change this to your server version
    PROTOCOL_VERSION = "2024-11-05"  # MCP protocol version
    
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
    # ============================================
    
    # Create and configure the MCP server
    mcp_server = MCPServer(
        server_name=SERVER_NAME,
        server_version=SERVER_VERSION,
        protocol_version=PROTOCOL_VERSION,
        tools=tools
    )
    
    # Create the Starlette application
    app = mcp_server.create_app()
    
    # Print startup information
    print(f"Starting {SERVER_NAME} MCP Server on http://0.0.0.0:{args.port}")
    print(f"Version: {SERVER_VERSION}")
    print(f"Registered tools: {', '.join(mcp_server.tools.keys())}")
    print(f"SSE endpoint: http://0.0.0.0:{args.port}/sse (GET)")
    print(f"Messages endpoint: http://0.0.0.0:{args.port}/messages (POST)")
    print(f"Health check: http://0.0.0.0:{args.port}/health")
    
    # Run the server
    uvicorn.run(app, host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    main()
