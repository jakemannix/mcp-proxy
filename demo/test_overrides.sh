#!/bin/bash
# Demo script to test MCP Gateway override functionality
#
# This script:
# 1. Uses a registry config with tool renaming (source field)
# 2. Starts the gateway
# 3. Uses curl to hit the MCP endpoint and list tools
# 4. Verifies the renamed tool appears

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PORT=${TEST_PORT:-8766}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}=== MCP Gateway Override Demo ===${NC}"
echo "Using registry: $SCRIPT_DIR/test_registry.json"
cat "$SCRIPT_DIR/test_registry.json"
echo ""

# Cleanup function
cleanup() {
    echo -e "\n${YELLOW}Cleaning up...${NC}"
    if [ -n "$GATEWAY_PID" ]; then
        kill $GATEWAY_PID 2>/dev/null || true
        wait $GATEWAY_PID 2>/dev/null || true
    fi
}
trap cleanup EXIT

# Kill any existing process on this port
lsof -ti:$PORT | xargs kill -9 2>/dev/null || true
sleep 1

# Start the gateway
echo -e "${YELLOW}Starting MCP Gateway on port $PORT...${NC}"
cd "$PROJECT_DIR"
uv run mcp-proxy --named-server-config "$SCRIPT_DIR/test_registry.json" --port $PORT --pass-environment 2>&1 &
GATEWAY_PID=$!

# Wait for gateway to start
echo "Waiting for gateway to start (PID: $GATEWAY_PID)..."
sleep 5

# Check if gateway is running
if ! kill -0 $GATEWAY_PID 2>/dev/null; then
    echo -e "${RED}Gateway failed to start!${NC}"
    exit 1
fi

echo -e "${GREEN}Gateway started successfully${NC}"

# Test the status endpoint
echo -e "\n${YELLOW}Testing /status endpoint...${NC}"
STATUS=$(curl -s "http://127.0.0.1:$PORT/status")
echo "Status: $STATUS"

# For MCP streamable HTTP, we need to POST to /mcp/ and track session ID
echo -e "\n${YELLOW}Testing MCP initialize...${NC}"

# Use -i to capture headers including Mcp-Session-Id
INIT_FULL=$(curl -si -X POST "http://127.0.0.1:$PORT/mcp/" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -d '{
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0.0"}
        }
    }')

# Extract session ID from response headers
SESSION_ID=$(echo "$INIT_FULL" | grep -i "mcp-session-id:" | cut -d' ' -f2 | tr -d '\r')
INIT_RESPONSE=$(echo "$INIT_FULL" | sed -n '/^{/,$p')

echo "Session ID: $SESSION_ID"
echo "Initialize response:"
echo "$INIT_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$INIT_RESPONSE"

# Send initialized notification (required by MCP protocol)
echo -e "\n${YELLOW}Sending initialized notification...${NC}"
curl -s -X POST "http://127.0.0.1:$PORT/mcp/" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -H "Mcp-Session-Id: $SESSION_ID" \
    -d '{
        "jsonrpc": "2.0",
        "method": "notifications/initialized"
    }' > /dev/null

# List tools with session ID
echo -e "\n${YELLOW}Listing tools...${NC}"
TOOLS_RESPONSE=$(curl -s -X POST "http://127.0.0.1:$PORT/mcp/" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -H "Mcp-Session-Id: $SESSION_ID" \
    -d '{
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {}
    }')

echo "Tools response:"
echo "$TOOLS_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$TOOLS_RESPONSE"

# Check results
echo -e "\n${YELLOW}=== Results ===${NC}"

if echo "$TOOLS_RESPONSE" | grep -q '"get_webpage"'; then
    echo -e "${GREEN}✓ Found renamed tool 'get_webpage' (alias for 'fetch')${NC}"
else
    echo -e "${RED}✗ Did not find renamed tool 'get_webpage'${NC}"
fi

if echo "$TOOLS_RESPONSE" | grep -q '"fetch"'; then
    echo -e "${YELLOW}! Original 'fetch' tool is also visible (expected in registry mode)${NC}"
else
    echo -e "${GREEN}✓ Original 'fetch' tool is hidden${NC}"
fi

if echo "$TOOLS_RESPONSE" | grep -q 'RENAMED:'; then
    echo -e "${GREEN}✓ Custom description applied${NC}"
else
    echo -e "${RED}✗ Custom description not found${NC}"
fi

echo -e "\n${YELLOW}Demo complete!${NC}"
