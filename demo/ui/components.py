"""Reusable UI components for the MCP Gateway demo."""

from fasthtml.common import *
from monsterui.all import *
import json


def ToolCard(tool: dict, selected: bool = False, oauth_required: bool = False, oauth_authenticated: bool = False):
    """Render a tool as a selectable card.

    Args:
        tool: Tool configuration dict
        selected: Whether this card is currently selected
        oauth_required: Whether this tool requires OAuth authentication
        oauth_authenticated: Whether OAuth has been completed for this tool's server
    """
    name = tool.get("name", "unknown")
    source = tool.get("source")
    version = tool.get("version")
    has_projection = "outputSchema" in tool or "outputTransform" in tool
    defaults = tool.get("defaults", {})
    has_defaults = bool(defaults)
    server = tool.get("server")
    composition = tool.get("composition")
    referenced_tools = tool.get("referencedTools", [])

    # Detect if this is a virtual tool that structures text output
    is_text_to_structured = source and has_projection and not server

    badges = []
    if version:
        badges.append(Span(f"v{version}", cls="badge badge-version"))

    # Composition badge takes precedence
    if composition:
        comp_type = composition.get("type", "composition")
        comp_labels = {
            "pipeline": "pipeline",
            "scatter_gather": "scatter",
            "filter": "filter",
            "schema_map": "transform",
            "map_each": "map",
            "retry": "retry",
            "timeout": "timeout",
            "cache": "cache",
        }
        label = comp_labels.get(comp_type, comp_type)
        badges.append(Span(label, cls="badge badge-composition"))
        if referenced_tools:
            badges.append(Span(f"{len(referenced_tools)} tools", cls="badge badge-tools-count"))
    elif is_text_to_structured:
        badges.append(Span("text→json", cls="badge badge-text-extract"))
    elif has_projection:
        badges.append(Span("projection", cls="badge badge-projection"))

    if has_defaults:
        badges.append(Span(f"{len(defaults)} hidden", cls="badge badge-hidden"))
    if source:
        badges.append(Span(f"→ {source}", cls="badge badge-source"))

    # Show backend reference for agentgateway format tools
    backend_tool = tool.get("backendTool")
    if backend_tool and server:
        badges.append(Span(f"{server}:{backend_tool}", cls="badge badge-backend"))

    # OAuth status indicator
    oauth_indicator = None
    if oauth_required:
        if oauth_authenticated:
            oauth_indicator = Span(
                UkIcon("unlock", height=12, width=12),
                cls="oauth-indicator oauth-authenticated",
                title="OAuth connected"
            )
        else:
            oauth_indicator = Span(
                UkIcon("lock", height=12, width=12),
                cls="oauth-indicator oauth-required",
                title="OAuth required - click to authenticate"
            )

    return Div(
        Div(
            UkIcon("terminal", height=14, width=14, cls="tool-icon"),
            Span(name, cls="tool-name"),
            oauth_indicator,
            cls="tool-card-header"
        ),
        Div(*badges, cls="tool-badges") if badges else None,
        cls=f"tool-card {'tool-card-selected' if selected else ''}",
        hx_get=f"/tool/{name}",
        hx_target="#tool-detail",
        hx_swap="innerHTML"
    )


def ToolDetail(tool: dict, oauth_required: bool = False, oauth_authenticated: bool = False, oauth_url: str = None):
    """Render detailed tool view with schema and test form.

    Args:
        tool: Tool configuration dict
        oauth_required: Whether this tool requires OAuth authentication
        oauth_authenticated: Whether OAuth has been completed for this tool's server
        oauth_url: URL for OAuth authentication if required
    """
    name = tool.get("name", "unknown")
    source = tool.get("source")
    version = tool.get("version")
    source_version_pin = tool.get("sourceVersionPin")
    validation_mode = tool.get("validationMode", "warn")
    description = tool.get("description", "No description provided")
    input_schema = tool.get("inputSchema", {})
    output_schema = tool.get("outputSchema")
    output_transform = tool.get("outputTransform")
    defaults = tool.get("defaults", {})
    server = tool.get("server")
    composition = tool.get("composition")
    referenced_tools = tool.get("referencedTools", [])

    # Detect if this is a virtual tool that structures text output
    is_text_to_structured = source and output_schema and not server
    is_composition = composition is not None

    sections = []

    # Header section
    header_badges = []
    if version:
        header_badges.append(Span(f"v{version}", cls="header-badge badge-version"))
    if is_composition:
        comp_type = composition.get("type", "composition")
        comp_labels = {
            "pipeline": "Pipeline Composition",
            "scatter_gather": "Scatter-Gather Composition",
            "filter": "Filter Pattern",
            "schema_map": "Schema Transform",
            "map_each": "Map-Each Pattern",
            "retry": "Retry Pattern",
            "timeout": "Timeout Pattern",
            "cache": "Cache Pattern",
        }
        label = comp_labels.get(comp_type, f"{comp_type} Composition")
        header_badges.append(Span(label, cls="header-badge badge-composition"))
    elif is_text_to_structured:
        header_badges.append(Span("Text → Structured JSON", cls="header-badge badge-text-extract"))

    # Build source info with version pin
    source_info = None
    if source:
        if source_version_pin:
            source_info = Span(f"Source: {source} (pinned to v{source_version_pin})", cls="detail-source")
        else:
            source_info = Span(f"Source: {source}", cls="detail-source")

    # Backend reference for agentgateway format
    backend_tool = tool.get("backendTool")
    if backend_tool and server:
        source_info = Span(f"Backend: {server} → {backend_tool}", cls="detail-source")

    sections.append(
        Div(
            Div(
                UkIcon("terminal", height=20, width=20, cls="detail-icon"),
                H2(name, cls="detail-title"),
                *header_badges,
                cls="detail-header-row"
            ),
            source_info,
            cls="detail-header"
        )
    )

    # OAuth status banner
    if oauth_required and not oauth_authenticated:
        sections.append(
            Div(
                Div(
                    UkIcon("lock", height=16, width=16),
                    Span("OAuth Authentication Required", cls="oauth-banner-title"),
                    cls="oauth-banner-header"
                ),
                P(
                    "This tool requires OAuth authentication. ",
                    A("Connect now", href=f"/oauth/start?url={oauth_url}", cls="oauth-connect-link") if oauth_url else "",
                    " to use this tool.",
                    cls="oauth-banner-text"
                ),
                cls="oauth-banner oauth-banner-warning"
            )
        )
    elif oauth_required and oauth_authenticated:
        sections.append(
            Div(
                Div(
                    UkIcon("unlock", height=16, width=16),
                    Span("OAuth Connected", cls="oauth-banner-title"),
                    cls="oauth-banner-header"
                ),
                cls="oauth-banner oauth-banner-success"
            )
        )

    # Composition structure display
    if is_composition:
        comp_type = composition.get("type", "unknown")
        spec = composition.get("spec", {})
        sections.append(
            Div(
                Div(
                    UkIcon("git-merge", height=14, width=14),
                    Span("Composition Structure", cls="label-text"),
                    cls="detail-label"
                ),
                format_composition_spec(comp_type, spec, referenced_tools),
                cls="detail-section"
            )
        )

    # Text-to-Structured explanation
    elif is_text_to_structured:
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
    elif output_transform:
        # New output transform format
        transform_html = format_output_transform(output_transform)
        sections.append(
            Div(
                Div(
                    UkIcon("filter", height=14, width=14),
                    Span("Output Transform", cls="label-text"),
                    cls="detail-label"
                ),
                transform_html,
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


def format_composition_spec(comp_type: str, spec: dict, referenced_tools: list) -> Div:
    """Format a composition specification for display."""

    if comp_type == "pipeline":
        return format_pipeline(spec.get("pipeline", {}))
    elif comp_type == "scatter_gather":
        sg_spec = spec.get("scatterGather") or spec.get("scatter_gather", {})
        return format_scatter_gather(sg_spec)
    elif comp_type == "filter":
        return format_filter(spec.get("filter", {}))
    elif comp_type == "map_each":
        me_spec = spec.get("mapEach") or spec.get("map_each", {})
        return format_map_each(me_spec)
    else:
        # Generic JSON display for unknown types
        return Div(
            Pre(json.dumps(spec, indent=2), cls="schema-box composition-spec"),
            cls="composition-box"
        )


def format_pipeline(pipeline: dict) -> Div:
    """Format a pipeline composition."""
    steps = pipeline.get("steps", [])

    step_elements = []
    for i, step in enumerate(steps):
        step_id = step.get("id", f"step_{i+1}")
        operation = step.get("operation", {})

        # Extract tool name from operation
        tool_info = operation.get("tool", {})
        if isinstance(tool_info, dict):
            tool_name = tool_info.get("name", "?")
        elif isinstance(tool_info, str):
            tool_name = tool_info
        else:
            # Check if it's a nested pattern
            tool_name = "[pattern]"

        step_elements.append(
            Div(
                Span(str(i + 1), cls="step-num"),
                Div(
                    Span(step_id, cls="step-id"),
                    Span(f"→ {tool_name}", cls="step-tool"),
                    cls="step-info"
                ),
                cls="pipeline-step"
            )
        )

        # Add arrow between steps (except after last)
        if i < len(steps) - 1:
            step_elements.append(
                Div(UkIcon("arrow-down", height=16, width=16), cls="step-arrow-down")
            )

    return Div(
        Div(
            P("Steps execute in sequence, each receiving output from the previous.", cls="composition-desc"),
            cls="composition-intro"
        ),
        Div(*step_elements, cls="pipeline-flow"),
        cls="composition-box"
    )


def format_scatter_gather(sg: dict) -> Div:
    """Format a scatter-gather composition."""
    targets = sg.get("targets", [])
    aggregation = sg.get("aggregation", {})
    timeout_ms = sg.get("timeout_ms") or sg.get("timeoutMs")
    fail_fast = sg.get("fail_fast") or sg.get("failFast", False)

    # Extract target names
    target_elements = []
    for target in targets:
        if isinstance(target, dict):
            if "tool" in target:
                tool_name = target["tool"] if isinstance(target["tool"], str) else target["tool"].get("name", "?")
                target_elements.append(
                    Span(tool_name, cls="scatter-target")
                )
            elif "pattern" in target:
                target_elements.append(
                    Span("[pattern]", cls="scatter-target scatter-pattern")
                )
        elif isinstance(target, str):
            target_elements.append(
                Span(target, cls="scatter-target")
            )

    # Format aggregation ops
    agg_ops = aggregation.get("ops", [])
    agg_labels = []
    for op in agg_ops:
        if isinstance(op, dict):
            if "flatten" in op:
                agg_labels.append("flatten")
            elif "sort" in op:
                agg_labels.append("sort")
            elif "dedupe" in op:
                agg_labels.append("dedupe")
            elif "limit" in op:
                agg_labels.append(f"limit({op['limit'].get('count', '?')})")
            elif "merge" in op:
                agg_labels.append("merge")

    return Div(
        Div(
            P("Fan-out to multiple tools in parallel, then aggregate results.", cls="composition-desc"),
            cls="composition-intro"
        ),
        Div(
            Div(
                Span("Input", cls="sg-label"),
                UkIcon("arrow-down", height=14, width=14),
                cls="sg-input"
            ),
            Div(
                *[Div(t, UkIcon("arrow-down", height=12, width=12), cls="sg-branch") for t in target_elements],
                cls="sg-branches"
            ),
            Div(
                Span("Aggregate", cls="sg-label"),
                Span(", ".join(agg_labels) if agg_labels else "concat", cls="sg-agg-ops"),
                cls="sg-aggregate"
            ),
            cls="scatter-gather-flow"
        ),
        Div(
            Span(f"Timeout: {timeout_ms}ms", cls="sg-config") if timeout_ms else None,
            Span(f"Fail-fast: {fail_fast}", cls="sg-config"),
            cls="sg-config-row"
        ) if timeout_ms or fail_fast else None,
        cls="composition-box"
    )


def format_filter(filter_spec: dict) -> Div:
    """Format a filter pattern."""
    predicate = filter_spec.get("predicate", {})
    field = predicate.get("field", "?")
    op = predicate.get("op", "?")
    value = predicate.get("value", "?")

    return Div(
        Div(
            P("Filter array elements based on a predicate.", cls="composition-desc"),
            cls="composition-intro"
        ),
        Div(
            Code(f"{field} {op} {json.dumps(value)}", cls="filter-predicate"),
            cls="filter-display"
        ),
        cls="composition-box"
    )


def format_map_each(me_spec: dict) -> Div:
    """Format a map-each pattern."""
    inner = me_spec.get("inner", {})

    if isinstance(inner, str):
        inner_desc = f"tool: {inner}"
    elif isinstance(inner, dict):
        if "tool" in inner:
            inner_desc = f"tool: {inner['tool']}"
        else:
            inner_desc = "[nested pattern]"
    else:
        inner_desc = str(inner)

    return Div(
        Div(
            P("Apply an operation to each element of an array.", cls="composition-desc"),
            cls="composition-intro"
        ),
        Div(
            Span("[", cls="array-bracket"),
            Span("item", cls="array-item"),
            Span("]", cls="array-bracket"),
            UkIcon("arrow-right", height=14, width=14),
            Span(inner_desc, cls="map-each-inner"),
            UkIcon("arrow-right", height=14, width=14),
            Span("[", cls="array-bracket"),
            Span("result", cls="array-item"),
            Span("]", cls="array-bracket"),
            cls="map-each-flow"
        ),
        cls="composition-box"
    )


def format_output_transform(transform: dict) -> Div:
    """Format an output transform specification."""
    mappings = transform.get("mappings", {})

    if not mappings:
        return Pre("{}", cls="schema-box schema-projection")

    rows = []
    for field_name, source in mappings.items():
        if isinstance(source, dict):
            if "path" in source:
                source_desc = Span(source["path"], cls="transform-path")
            elif "literal" in source:
                lit = source["literal"]
                if "stringValue" in lit:
                    source_desc = Span(f'"{lit["stringValue"]}"', cls="transform-literal")
                elif "numberValue" in lit:
                    source_desc = Span(str(lit["numberValue"]), cls="transform-literal")
                elif "boolValue" in lit:
                    source_desc = Span(str(lit["boolValue"]).lower(), cls="transform-literal")
                else:
                    source_desc = Span(json.dumps(lit), cls="transform-literal")
            elif "template" in source:
                source_desc = Span(f'template: {source["template"]}', cls="transform-template")
            else:
                source_desc = Span(json.dumps(source), cls="transform-other")
        elif isinstance(source, str):
            source_desc = Span(source, cls="transform-path")
        else:
            source_desc = Span(str(source), cls="transform-other")

        rows.append(
            Div(
                Span(field_name, cls="transform-field-name"),
                UkIcon("arrow-left", height=12, width=12, cls="transform-arrow"),
                source_desc,
                cls="transform-row"
            )
        )

    return Div(*rows, cls="transform-mappings")


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

    # JavaScript for localStorage API key management
    api_key_script = Script("""
        // Load API key from localStorage on page load
        document.addEventListener('DOMContentLoaded', function() {
            const savedKey = localStorage.getItem('openrouter_api_key');
            const input = document.getElementById('api-key-input');
            if (savedKey && input) {
                input.value = savedKey;
            }
        });

        // Save API key to localStorage when changed
        function saveApiKey(input) {
            if (input.value) {
                localStorage.setItem('openrouter_api_key', input.value);
            } else {
                localStorage.removeItem('openrouter_api_key');
            }
        }

        // Add API key header to HTMX requests for chat
        document.body.addEventListener('htmx:configRequest', function(evt) {
            if (evt.detail.path === '/agent/send') {
                const apiKey = localStorage.getItem('openrouter_api_key');
                if (apiKey) {
                    evt.detail.headers['X-OpenRouter-Key'] = apiKey;
                }
            }
        });
    """)

    # API key input section
    api_key_section = Div(
        Div(
            UkIcon("key", height=14, width=14),
            Span("OpenRouter API Key", cls="label-text"),
            A("(get one)", href="https://openrouter.ai/keys", target="_blank", cls="api-key-link"),
            cls="api-key-label"
        ),
        Input(
            type="password",
            id="api-key-input",
            placeholder="sk-or-...",
            cls="api-key-input",
            onchange="saveApiKey(this)",
            oninput="saveApiKey(this)"
        ),
        P("Stored in your browser only. Never sent to our server except for LLM calls.", cls="api-key-hint"),
        cls="api-key-section"
    )

    return Div(
        api_key_script,
        Div(
            UkIcon("bot", height=16, width=16),
            Span("Agent Chat", cls="section-title"),
            cls="section-header"
        ),
        api_key_section,
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
