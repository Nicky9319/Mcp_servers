import asyncio
import json
from typing import Any
from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.responses import Response, StreamingResponse
from starlette.requests import Request
import uvicorn
from duckduckgo_search import DDGS
import argparse

# Create MCP server instance
mcp_server = Server("duckduckgo-search")

@mcp_server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """List available tools."""
    return [
        types.Tool(
            name="duckduckgo_search",
            description="Search the web using DuckDuckGo. Returns relevant search results for any query.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query to look up"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default: 5)",
                        "default": 5
                    }
                },
                "required": ["query"]
            }
        )
    ]

@mcp_server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Handle tool execution requests."""
    
    if name != "duckduckgo_search":
        raise ValueError(f"Unknown tool: {name}")
    
    if not arguments:
        raise ValueError("Missing arguments")
    
    query = arguments.get("query")
    if not query:
        raise ValueError("Missing required argument: query")
    
    max_results = arguments.get("max_results", 5)
    
    try:
        # Perform the search
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        
        # Format results
        formatted_results = []
        for i, result in enumerate(results, 1):
            formatted_results.append(
                f"{i}. {result.get('title', 'No title')}\n"
                f"   URL: {result.get('href', 'No URL')}\n"
                f"   Snippet: {result.get('body', 'No description')}\n"
            )
        
        search_output = "\n".join(formatted_results) if formatted_results else "No results found."
        
        return [
            types.TextContent(
                type="text",
                text=search_output
            )
        ]
    
    except Exception as e:
        return [
            types.TextContent(
                type="text",
                text=f"Error performing search: {str(e)}"
            )
        ]

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
                        "name": "duckduckgo-search",
                        "version": "0.1.0"
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
        content=json.dumps({"status": "healthy", "service": "duckduckgo-search"}),
        media_type="application/json"
    )

async def handle_root(request: Request):
    """Handle root endpoint - serves as both info page and message handler."""
    if request.method == "GET":
        return Response(
            content=json.dumps({
                "service": "duckduckgo-search MCP Server",
                "version": "0.1.0",
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

# Create Starlette app with proper routing
app = Starlette(
    routes=[
        Route("/", endpoint=handle_root, methods=["GET", "POST"]),
        Route("/sse", endpoint=handle_sse, methods=["GET"]),
        Route("/messages", endpoint=handle_messages, methods=["POST"]),
        Route("/health", endpoint=health_check, methods=["GET"]),
    ]
)
if __name__ == "__main__":
    
    parser = argparse.ArgumentParser(description="DuckDuckGo MCP Server")
    parser.add_argument("--port", type=int, default=8000, help="Port to run the server on (default: 8000)")
    args = parser.parse_args()
    
    print(f"Starting DuckDuckGo MCP Server on http://0.0.0.0:{args.port}")
    print(f"SSE endpoint: http://0.0.0.0:{args.port}/sse (GET)")
    print(f"Messages endpoint: http://0.0.0.0:{args.port}/messages (POST)")
    print(f"Health check: http://0.0.0.0:{args.port}/health")
    uvicorn.run(app, host="0.0.0.0", port=args.port)