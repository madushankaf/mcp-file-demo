"""
AI Service that acts as MCP Client/Host.
Connects to mcp-server and exposes /chat endpoint for React frontend.
Uses LangChain with OpenAI to process user messages and call MCP tools.
"""
from fastapi import FastAPI, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from typing import Optional
import httpx
import json
import os
import sys
import logging
import time
import uuid

# Add parent directory to path for shared_logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared_logging import log_structured, add_flow_step, redact_url, generate_trace_id, print_flow_summary, clear_flow_summary

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("ai_service")

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
MCP_SERVER_PORT = os.getenv("MCP_SERVER_PORT", "8002")
MCP_SERVER_URL = f"http://localhost:{MCP_SERVER_PORT}/mcp"
PORT = int(os.getenv("PORT", "8000"))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

logger.info(f"🚀 ai-service starting on port {PORT}")
logger.info(f"🔗 MCP_SERVER_URL configured: {MCP_SERVER_URL}")

request_counter = 0
llm = None

# Initialize LangChain LLM
if OPENAI_API_KEY:
    llm = ChatOpenAI(model=OPENAI_MODEL, temperature=0, api_key=OPENAI_API_KEY)
    logger.info(f"🤖 [INIT] LangChain initialized with model: {OPENAI_MODEL}")
else:
    logger.warning("⚠️  [INIT] OPENAI_API_KEY not set. AI service will use fallback logic.")


class ChatRequest(BaseModel):
    message: str
    has_attached_file: bool = False


class ChatResponse(BaseModel):
    response: str
    elicitation: Optional[dict] = None


async def call_mcp_tool(tool_name: str, arguments: dict, trace_id: str) -> dict:
    """Call an MCP tool via HTTP"""
    global request_counter
    request_counter += 1
    mcp_request_id = request_counter
    
    log_structured(
        component="MCP_CLIENT",
        direction="→",
        event="mcp_initialize",
        summary="Initializing MCP connection",
        trace_id=trace_id,
        request_id=str(mcp_request_id)
    )
    
    async with httpx.AsyncClient() as client:
        # Initialize MCP connection
        await client.post(
            MCP_SERVER_URL,
            headers={"X-Trace-ID": trace_id},
            json={
                "jsonrpc": "2.0",
                "id": mcp_request_id,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {
                        "elicitation": {
                            "url": {},
                            "form": {}
                        }
                    },
                    "clientInfo": {
                        "name": "ai-service",
                        "version": "1.0.0"
                    }
                }
            }
        )
        
        # Call the tool
        request_counter += 1
        tool_request_id = request_counter
        tool_start_time = time.time()
        
        log_structured(
            component="MCP_CLIENT",
            direction="→",
            event="tool_call",
            summary=f"Calling MCP tool: {tool_name}",
            trace_id=trace_id,
            request_id=str(tool_request_id),
            tool_name=tool_name
        )
        
        tool_response = await client.post(
            MCP_SERVER_URL,
            headers={"X-Trace-ID": trace_id},
            json={
                "jsonrpc": "2.0",
                "id": tool_request_id,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments
                }
            }
        )
        
        duration_ms = (time.time() - tool_start_time) * 1000
        response_data = tool_response.json()
        
        # Determine response type
        if "error" in response_data:
            error_code = response_data.get("error", {}).get("code")
            if error_code == -32042:
                log_structured(
                    component="MCP_CLIENT",
                    direction="←",
                    event="elicitation_required",
                    summary=f"Received URLElicitationRequiredError from MCP server",
                    trace_id=trace_id,
                    request_id=str(tool_request_id),
                    tool_name=tool_name,
                    status_code=200,
                    duration_ms=duration_ms
                )
            else:
                log_structured(
                    component="MCP_CLIENT",
                    direction="←",
                    event="tool_error",
                    summary=f"MCP tool returned error: {response_data.get('error', {}).get('message')}",
                    trace_id=trace_id,
                    request_id=str(tool_request_id),
                    tool_name=tool_name,
                    status_code=error_code,
                    duration_ms=duration_ms
                )
        else:
            log_structured(
                component="MCP_CLIENT",
                direction="←",
                event="tool_response",
                summary=f"Received tool response from MCP server",
                trace_id=trace_id,
                request_id=str(tool_request_id),
                tool_name=tool_name,
                status_code=200,
                duration_ms=duration_ms
            )
        
        return response_data


@tool
def request_file_process(message: str = "Please select a file to upload for processing", mode: str = "ui") -> str:
    """Initiates a file processing request. Use this when the user wants to upload, process, or work with a file.
    
    Args:
        message: A friendly message to display to the user asking them to select a file
        mode: Upload mode - "ui" for browser UI file picker (elicitation flow), "stream" for direct streaming to API
    """
    # Return a marker that we'll detect in the chat endpoint
    return f"FILE_PROCESS:{mode}:{message}"


@app.post("/chat", response_model=ChatResponse)
async def chat(
    chat_request: ChatRequest,
    request: Request,
    x_trace_id: Optional[str] = Header(None, alias="X-Trace-ID")
):
    """Handle chat messages from React frontend using LangChain.
    Accepts JSON only with text message. Files are NOT sent to this service.
    When MCP tool returns an upload URL, the frontend streams the file directly to that URL.
    """
    start_time = time.time()
    trace_id = x_trace_id or generate_trace_id()
    clear_flow_summary()
    
    user_message = chat_request.message
    has_attached_file = chat_request.has_attached_file
    
    log_structured(
        component="UI",
        direction="→",
        event="user_message",
        summary=f"User message: {user_message[:100]}{'...' if len(user_message) > 100 else ''}",
        trace_id=trace_id,
        file_attached=has_attached_file
    )
    
    add_flow_step(
        step_num=1,
        sender="UI",
        receiver="AI_SERVICE",
        what_happened=f"User message: '{user_message[:50]}...' (file_attached={has_attached_file})",
        trace_id=trace_id
    )
    
    # Fallback logic if OpenAI is not configured
    if not llm:
        log_structured(
            component="AI_SERVICE",
            direction="→",
            event="fallback_response",
            summary="Using fallback logic (no LLM configured)",
            trace_id=trace_id
        )
        user_message_lower = user_message.lower()
        if "file" in user_message_lower or "process" in user_message_lower or "upload" in user_message_lower:
            return ChatResponse(
                response="Please attach a file using the '+' button, then send your message to process it.",
                elicitation=None
            )
        else:
            return ChatResponse(
                response="Hello! Say 'process file' or 'upload file' to start a file upload. Note: OpenAI API key not configured.",
                elicitation=None
            )
    
    # Use LangChain with tool calling
    try:
        llm_start_time = time.time()
        
        log_structured(
            component="LLM",
            direction="→",
            event="llm_request",
            summary=f"Sending message to LLM (model: {OPENAI_MODEL})",
            trace_id=trace_id
        )
        
        add_flow_step(
            step_num=2,
            sender="AI_SERVICE",
            receiver="LLM",
            what_happened=f"LLM request: {user_message[:50]}...",
            trace_id=trace_id
        )
        
        # Bind tools to the LLM
        llm_with_tools = llm.bind_tools([request_file_process])
        system_prompt = f"""You are a helpful assistant that can help users upload and process files.

IMPORTANT RULES:
1. When the user wants to upload or process a file, use the request_file_process tool. The tool will return an upload URL.

2. The tool accepts a mode parameter:
   - "stream" mode: Use this when a file is ALREADY ATTACHED in the UI. The frontend will automatically upload it.
   - "ui" mode: Use this when NO FILE is attached. The frontend will automatically open a file picker.

3. CURRENT SESSION STATUS:
   - File attached: {"YES - use mode='stream'" if has_attached_file else "NO - use mode='ui'"}
   
4. If a file is attached (has_attached_file=True), ALWAYS use mode="stream" - do NOT ask the user to attach a file.

5. If no file is attached (has_attached_file=False), use mode="ui" - the file picker will open automatically, no need to ask the user to click anything.

6. The frontend will handle streaming the file directly to the upload URL provided by the tool - you don't need to handle the file data.

7. When a file is attached, be direct and process it immediately. When no file is attached, use mode="ui" and the file picker will open automatically."""
        
        response = await llm_with_tools.ainvoke([
            ("system", system_prompt),
            ("human", user_message)
        ])
        
        llm_duration_ms = (time.time() - llm_start_time) * 1000
        response_text = response.content or ""
        tool_calls = response.tool_calls if hasattr(response, 'tool_calls') else []
        
        log_structured(
            component="LLM",
            direction="←",
            event="llm_response",
            summary=f"LLM response: {response_text[:100]}{'...' if len(response_text) > 100 else ''}",
            trace_id=trace_id,
            duration_ms=llm_duration_ms,
            tool_calls_count=len(tool_calls)
        )
        
        add_flow_step(
            step_num=3,
            sender="LLM",
            receiver="AI_SERVICE",
            what_happened=f"LLM response with {len(tool_calls)} tool call(s)",
            trace_id=trace_id,
            duration_ms=llm_duration_ms
        )
        
        elicitation_data = None
        
        # Check if the model wants to call a tool
        if response.tool_calls:
            for tool_call in response.tool_calls:
                if tool_call["name"] == "request_file_process":
                    tool_start_time = time.time()
                    
                    # Get the tool arguments
                    tool_args = tool_call.get("args", {})
                    tool_message = tool_args.get("message", "Please select a file to upload for processing")
                    upload_mode = tool_args.get("mode", "ui")
                    
                    # Override mode based on file attachment status if needed
                    if has_attached_file and upload_mode != "stream":
                        upload_mode = "stream"
                    elif not has_attached_file and upload_mode != "ui":
                        upload_mode = "ui"
                    
                    log_structured(
                        component="TOOL",
                        direction="→",
                        event="tool_execute",
                        summary=f"Executing tool: request_file_process (mode={upload_mode})",
                        trace_id=trace_id,
                        tool_name="request_file_process"
                    )
                    
                    add_flow_step(
                        step_num=4,
                        sender="AI_SERVICE",
                        receiver="TOOL",
                        what_happened=f"Tool execution: request_file_process (mode={upload_mode})",
                        trace_id=trace_id
                    )
                    
                    # Call the MCP tool
                    try:
                        mcp_response = await call_mcp_tool(
                            "request_file_process",
                            {"message": tool_message, "mode": upload_mode},
                            trace_id
                        )
                        
                        tool_duration_ms = (time.time() - tool_start_time) * 1000
                        
                        # Extract response data - handle both success and elicitation error
                        if "error" in mcp_response:
                            error = mcp_response.get("error", {})
                            error_code = error.get("code")
                            
                            # Check if it's URLElicitationRequiredError (-32042) per MCP spec 2025-11-25
                            if error_code == -32042:
                                error_data = error.get("data", {})
                                if error_data.get("mode") == "url":
                                    upload_url = error_data.get("url", "")
                                    upload_url_host = redact_url(upload_url)
                                    
                                    # URL mode elicitation - extract from error data
                                    elicitation_data = {
                                        "type": "elicitation",
                                        "mode": error_data.get("mode"),
                                        "message": error_data.get("message", tool_message),
                                        "url": upload_url
                                    }
                                    
                                    log_structured(
                                        component="TOOL",
                                        direction="←",
                                        event="elicitation_url_received",
                                        summary=f"Received URL-mode elicitation from MCP server",
                                        trace_id=trace_id,
                                        tool_name="request_file_process",
                                        upload_url_host=upload_url_host,
                                        duration_ms=tool_duration_ms
                                    )
                                    
                                    add_flow_step(
                                        step_num=5,
                                        sender="TOOL",
                                        receiver="AI_SERVICE",
                                        what_happened=f"Elicitation URL received (mode=url)",
                                        trace_id=trace_id,
                                        upload_url_host=upload_url_host
                                    )
                                    
                                    if not response_text:
                                        response_text = "Please select a file to upload."
                                else:
                                    log_structured(
                                        component="TOOL",
                                        direction="←",
                                        event="tool_error",
                                        summary=f"Unexpected elicitation mode: {error_data.get('mode')}",
                                        trace_id=trace_id,
                                        tool_name="request_file_process"
                                    )
                            else:
                                log_structured(
                                    component="TOOL",
                                    direction="←",
                                    event="tool_error",
                                    summary=f"MCP tool error: {error.get('message')}",
                                    trace_id=trace_id,
                                    tool_name="request_file_process",
                                    status_code=error_code
                                )
                                response_text = f"Error calling tool: {error.get('message', 'Unknown error')}"
                        else:
                            # Success response - extract from result
                            result = mcp_response.get("result", {})
                            content = result.get("content", [])
                            
                            if content:
                                text_content = content[0].get("text", "")
                                try:
                                    parsed = json.loads(text_content)
                                    if parsed.get("type") == "stream_upload":
                                        upload_url = parsed.get("url", "")
                                        upload_url_host = redact_url(upload_url)
                                        
                                        # Stream mode - direct upload URL
                                        elicitation_data = parsed
                                        
                                        log_structured(
                                            component="TOOL",
                                            direction="←",
                                            event="stream_url_received",
                                            summary=f"Received stream upload URL from MCP server",
                                            trace_id=trace_id,
                                            tool_name="request_file_process",
                                            upload_url_host=upload_url_host,
                                            duration_ms=tool_duration_ms
                                        )
                                        
                                        add_flow_step(
                                            step_num=5,
                                            sender="TOOL",
                                            receiver="AI_SERVICE",
                                            what_happened=f"Stream upload URL received (mode=stream)",
                                            trace_id=trace_id,
                                            upload_url_host=upload_url_host
                                        )
                                        
                                        if not response_text:
                                            if has_attached_file:
                                                response_text = "Processing your attached file..."
                                            else:
                                                response_text = tool_message
                                except Exception as e:
                                    log_structured(
                                        component="TOOL",
                                        direction="←",
                                        event="parse_error",
                                        summary=f"Failed to parse MCP response: {str(e)}",
                                        trace_id=trace_id,
                                        tool_name="request_file_process"
                                    )
                    except Exception as e:
                        log_structured(
                            component="TOOL",
                            direction="←",
                            event="tool_error",
                            summary=f"Error calling MCP tool: {str(e)}",
                            trace_id=trace_id,
                            tool_name="request_file_process"
                        )
                        response_text = f"I tried to initiate a file upload, but encountered an error: {str(e)}"
        
        total_duration_ms = (time.time() - start_time) * 1000
        
        log_structured(
            component="AI_SERVICE",
            direction="→",
            event="chat_response",
            summary=f"Sending response to UI (elicitation={elicitation_data is not None})",
            trace_id=trace_id,
            duration_ms=total_duration_ms
        )
        
        add_flow_step(
            step_num=6,
            sender="AI_SERVICE",
            receiver="UI",
            what_happened=f"Chat response with {'elicitation' if elicitation_data else 'no elicitation'}",
            trace_id=trace_id,
            duration_ms=total_duration_ms
        )
        
        # Print flow summary
        print_flow_summary()
        
        return ChatResponse(
            response=response_text,
            elicitation=elicitation_data
        )
        
    except Exception as e:
        log_structured(
            component="AI_SERVICE",
            direction="→",
            event="chat_error",
            summary=f"Error processing message: {str(e)}",
            trace_id=trace_id
        )
        print_flow_summary()
        return ChatResponse(
            response=f"Error processing your message: {str(e)}",
            elicitation=None
        )


@app.post("/elicitation/complete")
async def elicitation_complete(
    data: dict,
    x_trace_id: Optional[str] = Header(None, alias="X-Trace-ID")
):
    """Handle elicitation completion from React frontend"""
    trace_id = x_trace_id or "unknown"
    file_id = data.get("file_id", "unknown")
    
    log_structured(
        component="AI_SERVICE",
        direction="←",
        event="elicitation_complete",
        summary=f"Elicitation completed: file uploaded",
        trace_id=trace_id,
        file_id=file_id
    )
    
    add_flow_step(
        step_num=7,
        sender="UI",
        receiver="AI_SERVICE",
        what_happened=f"Elicitation completion notification (file_id={file_id})",
        trace_id=trace_id,
        file_id=file_id,
        status="success"
    )
    
    return {"status": "success", "message": "File upload completed"}


@app.get("/health")
async def health():
    logger.debug("💚 [HEALTH] Health check requested")
    return {"status": "ok"}
