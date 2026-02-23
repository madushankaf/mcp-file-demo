"""
MCP Server that provides request_file_process tool.
When called, it initiates an elicitation flow with mode: "url"
Uses HTTP transport instead of stdio.
"""
from fastapi import FastAPI, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import Optional
import json
import os
import sys
import logging
import time
from typing import Any, Dict, List

# Add parent directory to path for shared_logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared_logging import log_structured, add_flow_step, redact_url

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("mcp_server")

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration from environment variables
FILE_API_PORT = os.getenv("FILE_API_PORT", "8001")
FILE_API_URL = f"http://localhost:{FILE_API_PORT}/upload"
PORT = int(os.getenv("PORT", "8002"))
logger.info(f"🚀 mcp-server starting on port {PORT}")
logger.info(f"📎 FILE_API_URL configured: {FILE_API_URL}")


@app.post("/mcp")
async def handle_mcp_request(
    request: Request,
    x_trace_id: Optional[str] = Header(None, alias="X-Trace-ID")
):
    """Handle MCP JSON-RPC 2.0 requests"""
    start_time = time.time()
    data = await request.json()
    
    method = data.get("method")
    request_id = str(data.get("id", "unknown"))
    params = data.get("params", {})
    trace_id = x_trace_id or "unknown"
    
    log_structured(
        component="MCP_SERVER",
        direction="←",
        event="mcp_request",
        summary=f"Received MCP request: {method}",
        trace_id=trace_id,
        request_id=request_id
    )
    
    if method == "initialize":
        protocol_version = params.get('protocolVersion', 'unknown')
        log_structured(
            component="MCP_SERVER",
            direction="→",
            event="mcp_initialize",
            summary=f"MCP client initialized with protocol {protocol_version}",
            trace_id=trace_id,
            request_id=request_id
        )
        # Return server capabilities
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2025-11-25",
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": "mcp-file-server",
                    "version": "1.0.0"
                }
            }
        })
    
    elif method == "tools/list":
        log_structured(
            component="MCP_SERVER",
            direction="→",
            event="tools_list",
            summary="Returning available tools list",
            trace_id=trace_id,
            request_id=request_id
        )
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "tools": [
                    {
                        "name": "request_file_process",
                        "description": "Initiates a file processing request that requires user to upload a file",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "message": {
                                    "type": "string",
                                    "description": "Message to display to the user"
                                },
                                "mode": {
                                    "type": "string",
                                    "enum": ["ui", "stream"],
                                    "description": "Upload mode: 'ui' for browser UI file picker, 'stream' for direct streaming to API"
                                }
                            },
                            "required": ["message", "mode"]
                        }
                    }
                ]
            }
        })
    
    elif method == "tools/call":
        # Handle tool calls
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        duration_ms = (time.time() - start_time) * 1000
        
        log_structured(
            component="MCP_SERVER",
            direction="←",
            event="tool_call",
            summary=f"Tool call received: {tool_name}",
            trace_id=trace_id,
            request_id=request_id,
            tool_name=tool_name
        )
        
        if tool_name == "request_file_process":
            message = arguments.get("message", "Please upload a file for processing")
            upload_mode = arguments.get("mode", "ui")  # Default to UI mode
            
            if upload_mode == "ui":
                # URL Mode Elicitation Flow (per MCP spec 2025-11-25):
                # 1. Client calls tools/call
                # 2. Server returns URLElicitationRequiredError (-32042) with mode="url" and url in error.data
                # 3. Client presents URL to user and opens it
                # 4. For simple demo: Client uses URL directly (no retry needed)
                # 
                # Reference: https://modelcontextprotocol.io/specification/2025-11-25/client/elicitation#url-mode-flow
                upload_url_host = redact_url(FILE_API_URL)
                
                log_structured(
                    component="MCP_SERVER",
                    direction="→",
                    event="elicitation_url_required",
                    summary=f"Returning URL-mode elicitation (URLElicitationRequiredError)",
                    trace_id=trace_id,
                    request_id=request_id,
                    tool_name=tool_name,
                    upload_url_host=upload_url_host,
                    status_code=200
                )
                
                add_flow_step(
                    step_num=0,  # Will be renumbered
                    sender="MCP_CLIENT",
                    receiver="MCP_SERVER",
                    what_happened=f"Tool call: {tool_name} (mode={upload_mode})",
                    trace_id=trace_id,
                    request_id=request_id,
                    status="success"
                )
                
                add_flow_step(
                    step_num=0,  # Will be renumbered
                    sender="MCP_SERVER",
                    receiver="MCP_CLIENT",
                    what_happened=f"URLElicitationRequiredError with upload URL (mode=url)",
                    trace_id=trace_id,
                    request_id=request_id,
                    upload_url_host=upload_url_host,
                    status="elicitation_required"
                )
                
                # Per MCP spec 2025-11-25: Return URLElicitationRequiredError when tool call
                # cannot be processed until elicitation is completed.
                # Error code -32042 with mode="url" and url in error.data
                elicitation_error = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32042,
                        "message": "URLElicitationRequiredError",
                        "data": {
                            "mode": "url",
                            "message": message,
                            "url": FILE_API_URL
                        }
                    }
                }
                return JSONResponse(elicitation_error)
            
            elif upload_mode == "stream":
                # Stream mode: return direct upload URL (no elicitation)
                upload_url_host = redact_url(FILE_API_URL)
                
                log_structured(
                    component="MCP_SERVER",
                    direction="→",
                    event="stream_upload_url",
                    summary=f"Returning direct stream upload URL",
                    trace_id=trace_id,
                    request_id=request_id,
                    tool_name=tool_name,
                    upload_url_host=upload_url_host,
                    status_code=200
                )
                
                add_flow_step(
                    step_num=0,  # Will be renumbered
                    sender="MCP_CLIENT",
                    receiver="MCP_SERVER",
                    what_happened=f"Tool call: {tool_name} (mode={upload_mode})",
                    trace_id=trace_id,
                    request_id=request_id,
                    status="success"
                )
                
                add_flow_step(
                    step_num=0,  # Will be renumbered
                    sender="MCP_SERVER",
                    receiver="MCP_CLIENT",
                    what_happened=f"Stream upload URL returned (mode=stream)",
                    trace_id=trace_id,
                    request_id=request_id,
                    upload_url_host=upload_url_host,
                    status="success"
                )
                
                stream_response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps({
                                    "type": "stream_upload",
                                    "mode": "stream",
                                    "message": message,
                                    "url": FILE_API_URL,
                                    "metadata": {
                                        "description": "Direct file upload endpoint",
                                        "method": "POST",
                                        "contentType": "multipart/form-data"
                                    }
                                })
                            }
                        ],
                        "isError": False
                    }
                }
                return JSONResponse(stream_response)
        
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32601,
                "message": f"Unknown tool: {tool_name}"
            }
        })
    
    elif method == "elicitation/accept":
        log_structured(
            component="MCP_SERVER",
            direction="←",
            event="elicitation_accept",
            summary="Elicitation accepted by client",
            trace_id=trace_id,
            request_id=request_id
        )
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {}
        })
    
    elif method == "elicitation/decline":
        log_structured(
            component="MCP_SERVER",
            direction="←",
            event="elicitation_decline",
            summary="Elicitation declined by client",
            trace_id=trace_id,
            request_id=request_id
        )
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {}
        })
    
    return JSONResponse({
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {
            "code": -32601,
            "message": f"Method not found: {method}"
        }
    })


@app.get("/health")
async def health():
    logger.debug("💚 [HEALTH] Health check requested")
    return {"status": "ok"}
