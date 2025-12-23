"""Reusable UI components for the MCP Gateway demo."""

from fasthtml.common import *
from monsterui.all import *
import json


def ToolCard(tool: dict, selected: bool = False):
    """Render a tool as a selectable card."""
    name = tool.get("name", "unknown")
    source = tool.get("source")
    has_projection = "outputSchema" in tool
    defaults = tool.get("defaults", {})
    has_defaults = bool(defaults)
    server = tool.get("server")
    
    # Detect if this is a virtual tool that structures text output
    is_text_to_structured = source and has_projection and not server

    badges = []
    if is_text_to_structured:
        badges.append(Span("text→json", cls="badge badge-text-extract"))
    elif has_projection:
        badges.append(Span("projection", cls="badge badge-projection"))
    if has_defaults:
        badges.append(Span(f"{len(defaults)} hidden", cls="badge badge-hidden"))
    if source:
        badges.append(Span(f"→ {source}", cls="badge badge-source"))

    return Div(
        Div(
            UkIcon("terminal", height=14, width=14, cls="tool-icon"),
            Span(name, cls="tool-name"),
            cls="tool-card-header"
        ),
        Div(*badges, cls="tool-badges") if badges else None,
        cls=f"tool-card {'tool-card-selected' if selected else ''}",
        hx_get=f"/tool/{name}",
        hx_target="#tool-detail",
        hx_swap="innerHTML"
    )


def ToolDetail(tool: dict):
    """Render detailed tool view with schema and test form."""
    name = tool.get("name", "unknown")
    source = tool.get("source")
    description = tool.get("description", "No description provided")
    input_schema = tool.get("inputSchema", {})
    output_schema = tool.get("outputSchema")
    defaults = tool.get("defaults", {})
    server = tool.get("server")
    
    # Detect if this is a virtual tool that structures text output
    is_text_to_structured = source and output_schema and not server

    sections = []

    # Header section
    header_badges = []
    if is_text_to_structured:
        header_badges.append(Span("Text → Structured JSON", cls="header-badge badge-text-extract"))
    
    sections.append(
        Div(
            Div(
                UkIcon("terminal", height=20, width=20, cls="detail-icon"),
                H2(name, cls="detail-title"),
                *header_badges,
                cls="detail-header-row"
            ),
            Span(f"Source: {source}", cls="detail-source") if source else None,
            cls="detail-header"
        )
    )
    
    # Text-to-Structured explanation
    if is_text_to_structured:
        sections.append(
            Div(
                Div(
                    UkIcon("zap", height=14, width=14),
                    Span("JSON Extraction", cls="label-text"),
                    cls="detail-label"
                ),
                Div(
                    P(
                        f"This virtual tool extracts JSON from the text output of ",
                        Strong(source),
                        " and structures it according to the output schema.",
                        cls="extraction-desc"
                    ),
                    Div(
                        Div(
                            Span("1", cls="step-num"),
                            Span(f"{source} returns JSON in text", cls="step-text"),
                            cls="step"
                        ),
                        Div(
                            UkIcon("arrow-right", height=12, width=12),
                            cls="step-arrow"
                        ),
                        Div(
                            Span("2", cls="step-num"),
                            Span("Gateway extracts JSON", cls="step-text"),
                            cls="step"
                        ),
                        Div(
                            UkIcon("arrow-right", height=12, width=12),
                            cls="step-arrow"
                        ),
                        Div(
                            Span("3", cls="step-num"),
                            Span("Projects to output schema", cls="step-text"),
                            cls="step"
                        ),
                        cls="extraction-flow"
                    ),
                    cls="extraction-box"
                ),
                cls="detail-section"
            )
        )

    # Description section
    sections.append(
        Div(
            Div(
                UkIcon("file-text", height=14, width=14),
                Span("Description", cls="label-text"),
                cls="detail-label"
            ),
            P(description, cls="detail-description"),
            cls="detail-section"
        )
    )

    # Input Schema section
    sections.append(
        Div(
            Div(
                UkIcon("code", height=14, width=14),
                Span("Input Schema", cls="label-text"),
                cls="detail-label"
            ),
            Pre(json.dumps(input_schema, indent=2), cls="schema-box"),
            cls="detail-section"
        )
    )

    # Hidden defaults section
    if defaults:
        sections.append(
            Div(
                Div(
                    UkIcon("eye-off", height=14, width=14),
                    Span("Hidden Defaults", cls="label-text"),
                    cls="detail-label"
                ),
                Pre(json.dumps(defaults, indent=2), cls="schema-box schema-defaults"),
                cls="detail-section"
            )
        )

    # Output Schema section with source_field highlighting
    if output_schema:
        schema_html = format_output_schema(output_schema)
        sections.append(
            Div(
                Div(
                    UkIcon("filter", height=14, width=14),
                    Span("Output Projection", cls="label-text"),
                    cls="detail-label"
                ),
                Pre(NotStr(schema_html), cls="schema-box schema-projection"),
                cls="detail-section"
            )
        )

    # Test Form section
    test_form = build_test_form(name, input_schema)
    sections.append(
        Div(
            Div(
                UkIcon("play", height=14, width=14),
                Span("Test Tool", cls="label-text"),
                cls="detail-label"
            ),
            test_form,
            Div(id=f"test-result-{name}", cls="test-result"),
            cls="detail-section"
        )
    )

    return Div(*sections, cls="detail-content")


def format_output_schema(schema: dict, indent: int = 0) -> str:
    """Format output schema with source_field highlighting."""
    lines = []
    prefix = "  " * indent

    if isinstance(schema, dict):
        if "source_field" in schema:
            sf = schema["source_field"]
            lines.append(f'{prefix}<span class="source-field">source_field: "{sf}"</span>')

        for key, value in schema.items():
            if key == "source_field":
                continue
            if isinstance(value, dict):
                lines.append(f"{prefix}<span class='schema-key'>{key}:</span>")
                lines.append(format_output_schema(value, indent + 1))
            elif isinstance(value, list):
                lines.append(f"{prefix}<span class='schema-key'>{key}:</span> [...]")
            else:
                lines.append(f"{prefix}<span class='schema-key'>{key}:</span> <span class='schema-value'>{json.dumps(value)}</span>")

    return "\n".join(lines)


def build_test_form(tool_name: str, input_schema: dict):
    """Build a test form for the tool's input schema."""
    properties = input_schema.get("properties", {})
    required = input_schema.get("required", [])

    if not properties:
        return Form(
            Button(
                UkIcon("play", height=16, width=16),
                "Execute",
                type="submit",
                cls="btn-execute"
            ),
            hx_post=f"/tool/{tool_name}/test",
            hx_target=f"#test-result-{tool_name}",
            hx_swap="outerHTML",
            cls="test-form"
        )

    inputs = []
    for prop_name, prop_schema in properties.items():
        prop_type = prop_schema.get("type", "string")
        prop_desc = prop_schema.get("description", "")
        is_required = prop_name in required

        placeholder = prop_desc if prop_desc else f"Enter {prop_name}..."

        inputs.append(
            Div(
                Label(
                    prop_name,
                    Span(" *", cls="required-mark") if is_required else None,
                    cls="input-label"
                ),
                Input(
                    type="text",
                    name=prop_name,
                    placeholder=placeholder,
                    required=is_required,
                    cls="test-input"
                ),
                cls="form-field"
            )
        )

    return Form(
        *inputs,
        Button(
            UkIcon("play", height=16, width=16),
            "Execute",
            type="submit",
            cls="btn-execute"
        ),
        hx_post=f"/tool/{tool_name}/test",
        hx_target=f"#test-result-{tool_name}",
        hx_swap="outerHTML",
        cls="test-form"
    )


def ServerStatus(server_id: str, status: str = "online"):
    """Render server status indicator."""
    is_online = status != "offline"
    return Div(
        Span(cls=f"status-indicator {'status-online' if is_online else 'status-offline'}"),
        Span(server_id, cls="server-name"),
        cls="server-item"
    )


def ChatMessage(content: str, role: str = "user", tool_name: str = None):
    """Render a chat message."""
    if tool_name:
        return Div(
            Div(
                UkIcon("wrench", height=12, width=12),
                Span(f"Using: {tool_name}", cls="tool-call-name"),
                cls="tool-call-header"
            ),
            Pre(content, cls="tool-call-content") if content else None,
            cls="chat-message chat-tool"
        )

    icon = "user" if role == "user" else "bot"
    return Div(
        Div(
            UkIcon(icon, height=14, width=14, cls="message-icon"),
            cls="message-avatar"
        ),
        Div(content, cls="message-content"),
        cls=f"chat-message chat-{role}"
    )


def ChatPanel(messages: list = None, scenarios: list = None):
    """Render the agent chat panel."""
    messages = messages or []
    scenarios = scenarios or []

    if messages:
        message_elements = [ChatMessage(**msg) for msg in messages]
    else:
        message_elements = [
            Div(
                UkIcon("message-circle", height=24, width=24, cls="empty-icon"),
                P("Ask the agent about your tools", cls="empty-text"),
                cls="chat-empty"
            )
        ]

    scenario_options = [Option("Select a scenario...", value="", disabled=True, selected=True)]
    scenario_options.extend([
        Option(name, value=key) for key, name in scenarios
    ])

    return Div(
        Div(
            UkIcon("bot", height=16, width=16),
            Span("Agent Chat", cls="section-title"),
            cls="section-header"
        ),
        Div(*message_elements, id="chat-messages", cls="chat-messages"),
        Form(
            Textarea(
                placeholder="Ask the agent something...",
                name="prompt",
                id="chat-input",
                rows=3,
                cls="chat-input"
            ),
            Div(
                Select(*scenario_options, cls="scenario-select", id="scenario-select",
                       hx_get="/agent/scenario",
                       hx_target="#chat-input",
                       hx_swap="innerHTML"),
                Button(
                    UkIcon("send", height=16, width=16),
                    "Send",
                    type="submit",
                    cls="btn-send",
                ),
                cls="chat-controls"
            ),
            hx_post="/agent/send",
            hx_target="#chat-messages",
            hx_swap="beforeend",
            cls="chat-input-area"
        ),
        cls="sidebar right-sidebar"
    )
