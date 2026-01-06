"""MCP Gateway Demo - Modal Deployment

Deploys the MCP Gateway and FastHTML UI to Modal for public access.

Usage:
    # Install modal extra first
    uv sync --extra modal

    # Deploy to Modal (use uv run to ensure correct Modal version)
    uv run modal deploy modal_app.py

    # View deployment info
    uv run python modal_app.py

Configuration:
    After first deploy, create the gateway-config secret with your workspace URL:
        modal secret create gateway-config \\
            GATEWAY_URL=https://YOUR-WORKSPACE--mcp-gateway-demo-gateway.modal.run

    AI Agent Chat:
        Users provide their own OpenRouter API key in the browser (stored in localStorage).

Registry options (set REGISTRY_FILE env var before deploying):
    - modal-demo.json: Remote HTTP servers only (default, works best on Modal)
    - showcase.json: Full demo including subprocess servers
"""

import modal
import os

# Create Modal app
app = modal.App("mcp-gateway-demo")

# Configuration
REGISTRY_FILE = os.environ.get("REGISTRY_FILE", "modal-demo.json")

# Gateway image with Node.js for npx-based MCP servers
# Uses uv for fast, reproducible installs
gateway_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("nodejs", "npm", "curl")
    .run_commands("pip install uv")
    .run_commands(
        "uv pip install --system "
        "mcp>=1.17.0 "
        "uvicorn>=0.34.0 "
        "httpx>=0.27.0 "
        "httpx-auth>=0.22.0 "
        "jsonpath-ng>=1.6.0 "
        "'a2a-sdk[sqlite]>=0.3.16'"
    )
    .add_local_dir("src", "/app/src", copy=True)
    .add_local_dir("demo/registries", "/app/registries", copy=True)
    .env({"PYTHONPATH": "/app/src"})
)

# UI image - uses uv for fast installs
# No LLM SDK needed - we call OpenRouter via httpx with user's API key
ui_image = (
    modal.Image.debian_slim(python_version="3.11")
    .run_commands("pip install uv")
    .run_commands(
        "uv pip install --system "
        "python-fasthtml>=0.6.0 "
        "monsterui>=0.1.0 "
        "httpx>=0.27.0 "
        "sse-starlette>=1.6.0"
    )
    .add_local_dir("demo/ui", "/app", copy=True)
    .add_local_dir("demo/registries", "/app/registries", copy=True)
)


@app.function(
    image=gateway_image,
    scaledown_window=300,
    timeout=600,
)
@modal.concurrent(max_inputs=100)
@modal.web_server(port=8080, startup_timeout=120)
def gateway():
    """MCP Gateway server - aggregates backend MCP servers."""
    import subprocess
    import os as _os
    import logging

    # Suppress noisy DEBUG logs from HTTP/2 libraries
    logging.basicConfig(level=logging.INFO)
    for noisy in ("hpack", "httpcore", "httpx", "h2", "h11"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    env = _os.environ.copy()
    env["PATH"] = "/usr/local/bin:/usr/bin:/bin:" + env.get("PATH", "")
    env["PYTHONPATH"] = "/app/src"

    registry = _os.environ.get("REGISTRY_FILE", "modal-demo.json")
    registry_path = f"/app/registries/{registry}"

    print(f"Starting MCP Gateway with registry: {registry_path}")

    subprocess.Popen(
        [
            "python", "-m", "mcp_proxy",
            "--named-server-config", registry_path,
            "--host", "0.0.0.0",
            "--port", "8080",
            "--pass-environment",
        ],
        cwd="/app",
        env=env,
    )


@app.function(
    image=ui_image,
    scaledown_window=300,
    secrets=[modal.Secret.from_name("gateway-config")],
)
@modal.concurrent(max_inputs=100)
@modal.asgi_app()
def ui():
    """FastHTML UI for the MCP Gateway demo."""
    import os as _os
    import sys
    import logging

    # Suppress noisy DEBUG logs from HTTP/2 libraries
    logging.basicConfig(level=logging.INFO)
    for noisy in ("hpack", "httpcore", "httpx", "h2", "h11"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    sys.path.insert(0, "/app")
    _os.chdir("/app")

    # GATEWAY_URL must be set via the gateway-config secret
    # Fail fast if not configured - don't silently fall back to broken localhost
    gateway_url = _os.environ.get("GATEWAY_URL", "")

    if not gateway_url:
        raise RuntimeError(
            "GATEWAY_URL not set. Create the gateway-config secret:\n"
            "  modal secret create gateway-config "
            "GATEWAY_URL=https://YOUR-WORKSPACE--mcp-gateway-demo-gateway.modal.run\n"
            "Then redeploy: uv run modal deploy modal_app.py"
        )

    print(f"UI connecting to gateway at: {gateway_url}")

    _os.environ["GATEWAY_URL"] = gateway_url
    _os.environ["REGISTRIES_DIR"] = "/app/registries"

    from main import app as fasthtml_app
    return fasthtml_app


@app.local_entrypoint()
def main():
    """Print deployment info."""
    print("MCP Gateway Demo - Modal Deployment")
    print("=" * 50)
    print()
    print("DEPLOY:")
    print("  uv run modal deploy modal_app.py")
    print()
    print("REQUIRED - Configure gateway URL (after first deploy):")
    print("  modal secret create gateway-config \\")
    print("    GATEWAY_URL=https://YOUR-WORKSPACE--mcp-gateway-demo-gateway.modal.run")
    print()
    print("AI AGENT CHAT:")
    print("  Users provide their own OpenRouter API key in the browser.")
    print()
    print("USE FULL SHOWCASE (with subprocess servers):")
    print("  REGISTRY_FILE=showcase.json uv run modal deploy modal_app.py")


if __name__ == "__main__":
    print("MCP Gateway Demo - Modal Deployment")
    print("=" * 50)
    print()
    print("DEPLOY:")
    print("  uv run modal deploy modal_app.py")
    print()
    print("REQUIRED - Configure gateway URL (after first deploy):")
    print("  modal secret create gateway-config \\")
    print("    GATEWAY_URL=https://YOUR-WORKSPACE--mcp-gateway-demo-gateway.modal.run")
    print()
    print("AI AGENT CHAT:")
    print("  Users provide their own OpenRouter API key in the browser.")
    print()
    print("USE FULL SHOWCASE (with subprocess servers):")
    print("  REGISTRY_FILE=showcase.json uv run modal deploy modal_app.py")
