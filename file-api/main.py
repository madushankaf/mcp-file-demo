from fastapi import FastAPI, File, UploadFile, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import uuid
import os
import sys
import logging
import time
from datetime import datetime

# Add parent directory to path for shared_logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared_logging import log_structured, add_flow_step, redact_url

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("file_api")

app = FastAPI()

# Configuration from environment variables
PORT = int(os.getenv("PORT", "8001"))
logger.info(f"🚀 file-api starting on port {PORT}")

# Enable CORS for all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create uploads directory if it doesn't exist
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@app.post("/upload")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    x_trace_id: Optional[str] = Header(None, alias="X-Trace-ID")
):
    """Accept multipart/form-data file upload and save locally"""
    start_time = time.time()
    trace_id = x_trace_id or "unknown"
    file_id = str(uuid.uuid4())
    file_path = os.path.join(UPLOAD_DIR, file_id)
    
    # Get file size info (approximate from headers if available)
    file_size_header = request.headers.get("content-length")
    file_size_str = f"{file_size_header} bytes" if file_size_header else "unknown size"
    
    log_structured(
        component="FILE_API",
        direction="←",
        event="file_upload_received",
        summary=f"Received multipart file upload: {file.filename} ({file_size_str})",
        trace_id=trace_id,
        file_id=file_id,
        upload_url_host=redact_url(str(request.url))
    )
    
    # Save the file
    with open(file_path, "wb") as f:
        content = await file.read()
        file_size = len(content)
        f.write(content)
    
    duration_ms = (time.time() - start_time) * 1000
    
    log_structured(
        component="FILE_API",
        direction="→",
        event="file_upload_complete",
        summary=f"File saved successfully: {file.filename} ({file_size} bytes)",
        trace_id=trace_id,
        file_id=file_id,
        status_code=200,
        duration_ms=duration_ms
    )
    
    add_flow_step(
        step_num=0,  # Will be renumbered in summary
        sender="UI",
        receiver="FILE_API",
        what_happened=f"Multipart file upload: {file.filename} ({file_size} bytes)",
        trace_id=trace_id,
        file_id=file_id,
        status="success",
        duration_ms=duration_ms
    )
    
    response = {"status": "success", "file_id": file_id}
    return response


@app.get("/health")
async def health():
    logger.debug("💚 [HEALTH] Health check requested")
    return {"status": "ok"}
