# MCP File Demo - Quick Start Guide

A simple demo that shows how to upload files through a chat interface. This project has 4 services that work together.

<img width="2118" height="1193" alt="image" src="https://github.com/user-attachments/assets/fc2a072c-e179-403e-9dcd-c7318d99a1ab" />


## What You Need

Before you start, make sure you have these installed on your computer:

- **Python 3.8 or newer** (check with: `python3 --version`)
- **Node.js 16 or newer** (check with: `node --version`)
- **npm** (comes with Node.js, check with: `npm --version`)
- **An OpenAI API key** (get one free at: https://platform.openai.com/api-keys)

## Step 1: Clone the Project

```bash
git clone <repository-url>
cd mcp_file_demo
```

## Step 2: Install Everything

You need to set up 4 different parts. Just follow these steps in order:

### 2.1 Install file-api (Python service)

```bash
cd file-api
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cd ..
```

**On Windows:** Use `venv\Scripts\activate` instead of `source venv/bin/activate`

### 2.2 Install mcp-server (Python service)

```bash
cd mcp-server
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cd ..
```

### 2.3 Install ai-service (Python service)

```bash
cd ai-service
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cd ..
```

### 2.4 Install file-upload-interface (React frontend)

```bash
cd file-upload-interface
npm install
cd ..
```

## Step 3: Set Your OpenAI API Key

You need to set your OpenAI API key before running the services:

```bash
export OPENAI_API_KEY="your-api-key-here"
```

**Important:** Replace `your-api-key-here` with your actual API key from OpenAI.

**On Windows:** Use `set OPENAI_API_KEY=your-api-key-here` instead

## Step 4: Run the Demo

### Easy Way (Recommended)

Open **2 terminal windows**:

**Terminal 1 - Start all Python services:**
```bash
./start-services.sh
```

**Terminal 2 - Start the web interface:**
```bash
cd file-upload-interface
npm start
```

The web browser should open automatically to `http://localhost:3000`

### Manual Way (If the script doesn't work)

If the script doesn't work, open **4 terminal windows** and run these commands:

**Terminal 1 - file-api:**
```bash
cd file-api
source venv/bin/activate
uvicorn main:app --port 8001
```

**Terminal 2 - mcp-server:**
```bash
cd mcp-server
source venv/bin/activate
uvicorn server:app --port 8002
```

**Terminal 3 - ai-service:**
```bash
cd ai-service
source venv/bin/activate
export OPENAI_API_KEY="your-api-key-here"
uvicorn main:app --port 8000
```

**Terminal 4 - React frontend:**
```bash
cd file-upload-interface
npm start
```

## Step 5: Use the Demo

1. The web page should open at `http://localhost:3000`
2. Type a message like "Process file" or "Upload file"
3. A file picker will open automatically
4. Choose a file to upload
5. You'll see a success message when it's done!

## Troubleshooting

### "Command not found" errors

- Make sure Python 3 is installed: `python3 --version`
- Make sure Node.js is installed: `node --version`
- On some systems, use `python` instead of `python3`

### "Port already in use" errors

This means something is already running on that port. You can either:
- Close the other program using that port
- Or wait a few seconds and try again

### "Connection refused" errors in the browser

1. Make sure all 4 services are running (check all 4 terminal windows)
2. Wait a few seconds after starting services - they need time to start up
3. Check the browser console (press F12) for error messages

### Services won't start

1. Make sure you activated the virtual environment: `source venv/bin/activate`
2. Make sure you installed requirements: `pip install -r requirements.txt`
3. Make sure your OpenAI API key is set: `echo $OPENAI_API_KEY` (should show your key)

### Test if services are working

Open a new terminal and test each service:

```bash
# Test ai-service
curl http://localhost:8000/health

# Test file-api
curl http://localhost:8001/health

# Test mcp-server
curl http://localhost:8002/health
```

Each should return `{"status":"ok"}`

## What Each Service Does

- **file-api** (port 8001): Receives and stores uploaded files
- **mcp-server** (port 8002): Handles file processing requests
- **ai-service** (port 8000): The brain that coordinates everything
- **file-upload-interface** (port 3000): The web page you see in your browser

## Need Help?

If you're stuck:
1. Check that all services are running
2. Check the terminal windows for error messages
3. Make sure your OpenAI API key is set correctly
4. Try restarting all services

## Technical Notes (For Reference)

- All services use HTTP (no special protocols needed)
- Default ports: ai-service=8000, file-api=8001, mcp-server=8002, frontend=3000
- You can change ports using environment variables, but defaults work fine for testing
