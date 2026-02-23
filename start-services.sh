#!/bin/bash

# MCP File Demo - Service Startup Script
# This script helps start all services with proper port configuration

echo "Starting MCP File Demo Services..."
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if virtual environments exist
check_venv() {
    if [ ! -d "$1/venv" ]; then
        echo -e "${YELLOW}Warning: $1/venv not found. Creating virtual environment...${NC}"
        cd "$1"
        python3 -m venv venv
        source venv/bin/activate
        pip install -r requirements.txt
        cd ..
    fi
}

# Start file-api
echo -e "${GREEN}Starting file-api on port 8001...${NC}"
cd file-api
check_venv "."
source venv/bin/activate
export PORT=8001
uvicorn main:app --port 8001 &
FILE_API_PID=$!
cd ..
sleep 2

# Start mcp-server
echo -e "${GREEN}Starting mcp-server on port 8002...${NC}"
cd mcp-server
check_venv "."
source venv/bin/activate
export PORT=8002
export FILE_API_PORT=8001
uvicorn server:app --port 8002 &
MCP_SERVER_PID=$!
cd ..
sleep 2

# Start ai-service
echo -e "${GREEN}Starting ai-service on port 8000...${NC}"
if [ -z "$OPENAI_API_KEY" ]; then
    echo -e "${YELLOW}Warning: OPENAI_API_KEY not set. AI service will use fallback logic.${NC}"
    echo -e "${YELLOW}Set it with: export OPENAI_API_KEY='your-api-key'${NC}"
fi
cd ai-service
check_venv "."
source venv/bin/activate
export PORT=8000
export MCP_SERVER_PORT=8002
# OPENAI_API_KEY and OPENAI_MODEL should be set before running this script
uvicorn main:app --port 8000 &
AI_SERVICE_PID=$!
cd ..
sleep 2

echo ""
echo -e "${GREEN}All services started!${NC}"
echo "PIDs: file-api=$FILE_API_PID, mcp-server=$MCP_SERVER_PID, ai-service=$AI_SERVICE_PID"
echo ""
echo "To stop all services, run: kill $FILE_API_PID $MCP_SERVER_PID $AI_SERVICE_PID"
echo ""
echo "Now start the React client:"
echo "  cd file-upload-interface"
echo "  npm start"
echo ""
echo "Or if you need port 9000, start ai-service manually:"
echo "  cd ai-service"
echo "  source venv/bin/activate"
echo "  export PORT=9000"
echo "  export MCP_SERVER_PORT=8002"
echo "  uvicorn main:app --port 9000"
