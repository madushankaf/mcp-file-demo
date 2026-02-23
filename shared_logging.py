"""
Shared logging utilities for structured observability across MCP file upload flow.
Provides trace_id propagation, structured logging, and flow summary collection.
"""
import logging
import time
import uuid
from datetime import datetime
from typing import Optional, Dict, Any
from urllib.parse import urlparse
import json

# Global flow summary collector
_flow_summary = []


def generate_trace_id() -> str:
    """Generate a unique trace ID for end-to-end request tracking"""
    return str(uuid.uuid4())[:8]  # Short ID for readability


def redact_url(url: str) -> str:
    """Redact sensitive query params from URLs, return host + path only"""
    try:
        parsed = urlparse(url)
        # Return host + path, no query params or fragments
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    except:
        return url.split('?')[0]  # Fallback: remove query string


def log_structured(
    component: str,
    direction: str,
    event: str,
    summary: str,
    trace_id: Optional[str] = None,
    **kwargs
):
    """
    Log structured event with consistent format.
    
    Args:
        component: UI | MCP_SERVER | FILE_API | LLM | TOOL | MCP_CLIENT
        direction: → (outbound) | ← (inbound)
        event: Short event name (e.g., "user_message", "tool_call", "file_upload")
        summary: 1-2 line human-readable summary
        trace_id: Optional trace ID for request tracking
        **kwargs: Optional fields (tool_name, request_id, file_id, upload_url_host, status_code, duration_ms)
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    
    # Build log line
    parts = [f"[{timestamp}]"]
    if trace_id:
        parts.append(f"[trace_id={trace_id}]")
    parts.append(f"[{component}]")
    parts.append(direction)
    parts.append(f"[{event}]")
    parts.append(summary)
    
    # Add optional fields
    if kwargs:
        optional_parts = []
        for key, value in kwargs.items():
            if value is not None:
                # Redact URLs
                if 'url' in key.lower() and isinstance(value, str):
                    value = redact_url(value)
                optional_parts.append(f"{key}={value}")
        if optional_parts:
            parts.append("| " + " ".join(optional_parts))
    
    log_message = " ".join(parts)
    
    # Use appropriate log level
    logger = logging.getLogger(component.lower())
    if "error" in event.lower() or "failed" in event.lower():
        logger.error(log_message)
    elif "complete" in event.lower() or "success" in event.lower():
        logger.info(log_message)
    else:
        logger.info(log_message)


def add_flow_step(
    step_num: int,
    sender: str,
    receiver: str,
    what_happened: str,
    trace_id: Optional[str] = None,
    request_id: Optional[str] = None,
    file_id: Optional[str] = None,
    status: Optional[str] = None,
    duration_ms: Optional[float] = None,
    upload_url_host: Optional[str] = None,
):
    """Add a step to the flow summary"""
    _flow_summary.append({
        "step": step_num,
        "sender": sender,
        "receiver": receiver,
        "what_happened": what_happened,
        "trace_id": trace_id,
        "request_id": request_id,
        "file_id": file_id,
        "status": status,
        "duration_ms": duration_ms,
        "upload_url_host": upload_url_host,
    })


def get_flow_summary() -> list:
    """Get the current flow summary"""
    return _flow_summary.copy()


def clear_flow_summary():
    """Clear the flow summary (call at start of new request)"""
    _flow_summary.clear()


def print_flow_summary():
    """Print a formatted flow summary"""
    if not _flow_summary:
        return
    
    print("\n" + "=" * 80)
    print("MESSAGE FLOW SUMMARY")
    print("=" * 80)
    
    # Renumber steps sequentially
    step_num = 1
    for step in _flow_summary:
        sender = step.get("sender", "?")
        receiver = step.get("receiver", "?")
        what = step.get("what_happened", "?")
        trace_id = step.get("trace_id", "")
        request_id = step.get("request_id", "")
        file_id = step.get("file_id", "")
        status = step.get("status", "")
        duration = step.get("duration_ms")
        upload_url_host = step.get("upload_url_host", "")
        
        # Build identifiers line
        identifiers = []
        if trace_id and trace_id != "unknown":
            identifiers.append(f"trace_id={trace_id}")
        if request_id and request_id != "unknown":
            identifiers.append(f"request_id={request_id}")
        if file_id and file_id != "unknown":
            identifiers.append(f"file_id={file_id}")
        if upload_url_host:
            identifiers.append(f"url={upload_url_host}")
        
        # Build status line
        status_line = ""
        if status:
            status_line = f" | Status: {status}"
        if duration is not None:
            status_line += f" | Duration: {duration:.2f}ms"
        
        print(f"\nStep {step_num}: {sender} → {receiver}")
        print(f"  {what}")
        if identifiers:
            print(f"  Identifiers: {', '.join(identifiers)}{status_line}")
        
        step_num += 1
    
    print("\n" + "=" * 80 + "\n")
