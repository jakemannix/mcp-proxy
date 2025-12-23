#!/bin/bash
# MCP Gateway Demo - One-liner setup
#
# Usage:
#   ./run-demo.sh           # Start UI + Gateway (Docker)
#   ./run-demo.sh local     # Start UI locally (no Docker, for development)
#   ./run-demo.sh agent     # Start with agent chat enabled
#
# Environment:
#   ANTHROPIC_API_KEY       # Required for agent chat
#   REGISTRY_PATH           # Override default registry

set -e
cd "$(dirname "$0")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=== MCP Gateway Demo ===${NC}"

# Check for API key warning
if [[ -z "$ANTHROPIC_API_KEY" ]]; then
    echo -e "${YELLOW}Note: ANTHROPIC_API_KEY not set - agent chat will be disabled${NC}"
fi

case "${1:-docker}" in
    docker|ui)
        echo -e "${GREEN}Starting with Docker Compose...${NC}"
        echo "Gateway will be at: http://localhost:8080"
        echo "UI will be at:      http://localhost:5001"
        echo ""
        docker compose up --build gateway ui
        ;;

    local)
        echo -e "${GREEN}Starting locally (development mode)...${NC}"

        # Check if gateway is needed
        if ! curl -s http://localhost:8080/status > /dev/null 2>&1; then
            echo -e "${YELLOW}Starting gateway in background...${NC}"
            cd ..
            uv run mcp-proxy --named-server-config demo/registries/showcase.json --port 8080 &
            GATEWAY_PID=$!
            cd demo
            sleep 3
            trap "kill $GATEWAY_PID 2>/dev/null || true" EXIT
        else
            echo -e "${GREEN}Gateway already running at :8080${NC}"
        fi

        echo "Starting UI at http://localhost:5001"
        cd ui
        GATEWAY_URL=http://localhost:8080 REGISTRIES_DIR=../registries uv run python main.py
        ;;

    agent)
        echo -e "${GREEN}Starting with agent chat enabled...${NC}"
        if [[ -z "$ANTHROPIC_API_KEY" ]]; then
            echo -e "${RED}Error: ANTHROPIC_API_KEY required for agent mode${NC}"
            echo "Set it with: ANTHROPIC_API_KEY=sk-... ./run-demo.sh agent"
            exit 1
        fi
        docker compose up --build
        ;;

    stop)
        echo "Stopping all demo processes..."
        docker compose down 2>/dev/null || true
        lsof -ti:8080 | xargs kill -9 2>/dev/null || true
        lsof -ti:5001 | xargs kill -9 2>/dev/null || true
        echo -e "${GREEN}Stopped${NC}"
        ;;

    restart)
        echo "Restarting demo..."
        $0 stop
        sleep 1
        $0 local
        ;;

    *)
        echo "Usage: ./run-demo.sh [docker|local|agent|stop|restart]"
        echo ""
        echo "Commands:"
        echo "  docker  - Start UI + Gateway with Docker (default)"
        echo "  local   - Start UI locally for development"
        echo "  agent   - Start with agent chat (requires ANTHROPIC_API_KEY)"
        echo "  stop    - Stop all processes (Docker + local)"
        echo "  restart - Stop and restart locally"
        ;;
esac
