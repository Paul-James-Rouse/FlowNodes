# app.py
from pathlib import Path
import os

from dash import Dash, html, dcc, Input, Output, State, callback_context, no_update

import dash_cytoscape as cyto
from wsp_to_cyto import wsp_to_cyto
from styles_cyto import cyto_stylesheet


# --- Helpers ---
def filter_out_leaves(all_elements, keep_root=True):
    """
    Returns (filtered_elements, leaf_ids).
    A leaf is any node that does not appear as an edge 'source'.
    """
    nodes = [el for el in all_elements if el.get("data") and "source" not in el["data"]]
    edges = [el for el in all_elements if el.get("data") and "source" in el["data"]]

    node_ids = {n["data"]["id"] for n in nodes}
    sources = {e["data"]["source"] for e in edges}

    leaves = node_ids - sources
    if keep_root and "root" in leaves:
        leaves.remove("root")

    kept_nodes = [n for n in nodes if n["data"]["id"] not in leaves]
    kept_edges = [
        e for e in edges
        if e["data"]["source"] not in leaves and e["data"]["target"] not in leaves
    ]
    return kept_nodes + kept_edges, sorted(leaves)


def show_node_info(data):
    """
    Display node information with name and color prominently.
    """
    if not data:
        return html.Div("Click a node to see details.", style={"padding": "1rem"})
    
    # Get node name (label)
    node_name = data.get("label", data.get("id", "Unknown"))
    
    # Get node color - check if node_colour is in data, otherwise use default
    node_color = data.get("node_colour", "#A0C4FF")
    
    # Build the display
    return html.Div(
        [
            html.H4("Node Information", style={"marginTop": 0, "marginBottom": "1rem"}),
            html.Div(
                [
                    html.Strong("Name: "),
                    html.Span(node_name, style={"fontSize": "1.1rem"}),
                ],
                style={"marginBottom": "1rem"},
            ),
            html.Div(
                [
                    html.Strong("Color: "),
                    html.Span(
                        node_color,
                        style={
                            "display": "inline-block",
                            "width": "20px",
                            "height": "20px",
                            "backgroundColor": node_color,
                            "border": "1px solid #333",
                            "marginLeft": "0.5rem",
                            "verticalAlign": "middle",
                        },
                    ),
                    html.Span(f" {node_color}", style={"marginLeft": "0.5rem"}),
                ],
                style={"marginBottom": "1rem"},
            ),
            html.Hr(),
            html.Div(
                [
                    html.Strong("Additional Details:"),
                    html.Div(
                        [
                            html.Div([html.Strong(f"{label}: "), html.Span(str(data.get(key, "N/A")))])
                            for key, label in [
                                ("panel", "Panel"),
                                ("primary_markers", "Markers"),
                                ("biological_role", "Biological role"),
                                ("id", "Full path"),
                            ]
                            if data.get(key)
                        ],
                        style={"marginTop": "0.5rem"},
                    ),
                ],
            ),
        ],
        style={"padding": "1rem"},
    )


def get_triggered_id():
    return (
        callback_context.triggered[0]["prop_id"].split(".")[0]
        if callback_context.triggered else None
    )


def make_layout(name: str, **params):
    """
    Create a Cytoscape layout configuration.
    
    Args:
        name: Layout type ("cose" or "breadthfirst")
        **params: Additional layout parameters (spacingFactor, padding, nodeRepulsion, etc.)
    """
    base_layout = {
        "name": name,
        "directed": True,
        "animate": False,
    }
    
    if name == "breadthfirst":
        base_layout.update({
            "spacingFactor": params.get("spacingFactor", 1.15),
            "padding": params.get("padding", 30),
        })
    else:  # cose
        base_layout.update({
            "padding": params.get("padding", 50),
            "randomize": False,
            "nodeOverlap": 1,
            "nodeRepulsion": params.get("nodeRepulsion", 20_000),
            "idealEdgeLength": params.get("idealEdgeLength", 200),
        })
    
    return base_layout


# --- App ---
app = Dash(__name__)

# --- Data ---
# Load gating tree directly from a FlowJo .wsp file
# Resolve path relative to project root (works when running from src/ or project root)
project_root = Path(__file__).parent.parent
wsp_path = project_root / 'inputs' / 'FlowJo_tutorial.wsp'
# wsp_to_cyto returns: { "nodes": [...], "edges": [...] }
cy = wsp_to_cyto(wsp_path)
# Cytoscape wants a single list containing both node + edge elements
elements_all = cy["nodes"] + cy["edges"]

# Remove leaves initially
elements_filtered, initial_leaves = filter_out_leaves(elements_all, keep_root=True)
print(f"⚡ Loaded WSP with {len(elements_filtered)} elements (removed {len(initial_leaves)} leaves)")

elements = elements_filtered  # start with leaves hidden

# --- Client-side stores & controls ---
stores = [
    dcc.Store(id="all-elements", data=elements_all),
    dcc.Store(id="leaves-hidden", data=True),  # start with leaves already hidden
    dcc.Store(id="current-layout-type", data="breadthfirst"),  # track current layout type
    dcc.Store(id="layout-params", data={"spacingFactor": 1.15, "padding": 30, "nodeRepulsion": 20000, "idealEdgeLength": 200}),
]

# Window styling constants
WINDOW_STYLE = {
    "border": "1px solid #ddd",
    "borderRadius": "4px",
    "padding": "1rem",
    "backgroundColor": "#fafafa",
    "overflow": "auto",
}

# --- Layout ---
app.layout = html.Div(
    [
        *stores,
        html.Div(
            [
                # Top Left: Cytoscape Graph
                html.Div(
                    [
                        html.H4("Network Visualization", style={"marginTop": 0}),
                        cyto.Cytoscape(
                            id="cyto-graph",
                            elements=elements,
                            layout=make_layout("breadthfirst"),
                            stylesheet=cyto_stylesheet(),
                            style={"height": "calc(70vh - 80px)", "width": "100%"},
                            minZoom=0.2,
                            maxZoom=2.5,
                            boxSelectionEnabled=True,
                        ),
                    ],
                    style={
                        **WINDOW_STYLE,
                        "gridColumn": "1",
                        "gridRow": "1",
                    },
                ),
                # Top Right: Node Information
                html.Div(
                    [
                        html.Div(id="node-info-panel", children="Click a node to see details."),
                    ],
                    style={
                        **WINDOW_STYLE,
                        "gridColumn": "2",
                        "gridRow": "1",
                    },
                ),
                # Bottom Left: Layout Controls
                html.Div(
                    [
                        html.H4("Layout Controls", style={"marginTop": 0}),
                        html.Div(id="layout-type-display", style={"marginBottom": "1rem"}),
                        html.Button("Switch Layout", id="btn-toggle-layout", n_clicks=0, style={"marginBottom": "1rem"}),
                        # All sliders always exist, but will be shown/hidden based on layout type
                        html.Div(
                            [
                                html.Div(
                                    [
                                        html.Label("Spacing Factor:", style={"display": "block", "marginTop": "0.5rem"}),
                                        dcc.Slider(
                                            id="slider-spacing-factor",
                                            min=0.5,
                                            max=3.0,
                                            step=0.05,
                                            value=1.15,
                                            marks={0.5: "0.5", 1.5: "1.5", 3.0: "3.0"},
                                            tooltip={"placement": "bottom", "always_visible": True},
                                        ),
                                        html.Label("Padding:", style={"display": "block", "marginTop": "1rem"}),
                                        dcc.Slider(
                                            id="slider-padding-bf",
                                            min=0,
                                            max=100,
                                            step=5,
                                            value=30,
                                            marks={0: "0", 50: "50", 100: "100"},
                                            tooltip={"placement": "bottom", "always_visible": True},
                                        ),
                                    ],
                                    id="breadthfirst-controls",
                                ),
                                html.Div(
                                    [
                                        html.Label("Node Repulsion:", style={"display": "block", "marginTop": "0.5rem"}),
                                        dcc.Slider(
                                            id="slider-node-repulsion",
                                            min=1000,
                                            max=50000,
                                            step=1000,
                                            value=20000,
                                            marks={1000: "1k", 25000: "25k", 50000: "50k"},
                                            tooltip={"placement": "bottom", "always_visible": True},
                                        ),
                                        html.Label("Ideal Edge Length:", style={"display": "block", "marginTop": "1rem"}),
                                        dcc.Slider(
                                            id="slider-edge-length",
                                            min=50,
                                            max=500,
                                            step=10,
                                            value=200,
                                            marks={50: "50", 250: "250", 500: "500"},
                                            tooltip={"placement": "bottom", "always_visible": True},
                                        ),
                                        html.Label("Padding:", style={"display": "block", "marginTop": "1rem"}),
                                        dcc.Slider(
                                            id="slider-padding-cose",
                                            min=0,
                                            max=100,
                                            step=5,
                                            value=50,
                                            marks={0: "0", 50: "50", 100: "100"},
                                            tooltip={"placement": "bottom", "always_visible": True},
                                        ),
                                    ],
                                    id="cose-controls",
                                ),
                            ],
                            id="layout-parameter-controls",
                        ),
                    ],
                    style={
                        **WINDOW_STYLE,
                        "gridColumn": "1",
                        "gridRow": "2",
                    },
                ),
                # Bottom Right: Action Buttons
                html.Div(
                    [
                        html.H4("Actions", style={"marginTop": 0}),
                        html.Button("Toggle Leaf Nodes", id="btn-toggle-leaves", n_clicks=0, style={"marginBottom": "0.5rem", "width": "100%"}),
                        html.Div(id="leaf-status", style={"fontSize": "0.9rem", "opacity": 0.75, "marginBottom": "1rem"}),
                        html.Button("Export PNG", id="btn-export-png", n_clicks=0, style={"width": "100%"}),
                    ],
                    style={
                        **WINDOW_STYLE,
                        "gridColumn": "2",
                        "gridRow": "2",
                    },
                ),
            ],
            style={
                "display": "grid",
                "gridTemplateColumns": "1fr 1fr",
                "gridTemplateRows": "calc(65vh - 0.5rem) calc(30vh - 0.5rem)",
                "gap": "1rem",
                "padding": "1rem",
                "paddingBottom": "15rem",
                "height": "calc(100vh - 2rem)",
                "boxSizing": "border-box",
            },
        ),
    ],
    style={"margin": 0, "padding": 0, "paddingBottom": "2rem", "height": "100vh", "overflow": "auto"},
)


# --- Callbacks ---
@app.callback(
    Output("cyto-graph", "elements"),
    Output("leaves-hidden", "data"),
    Output("btn-toggle-leaves", "children"),
    Output("leaf-status", "children"),
    Input("btn-toggle-leaves", "n_clicks"),
    State("leaves-hidden", "data"),
    State("all-elements", "data"),
    prevent_initial_call=False,
)
def toggle_leaves(n_clicks, leaves_hidden, all_elements):
    # Safety on first render
    if not all_elements:
        return [], False, "Hide leaf nodes", ""

    triggered_id = get_triggered_id()

    # Initial page load (no trigger): start with leaves hidden
    if triggered_id is None:
        filtered, leaves = filter_out_leaves(all_elements, keep_root=True)
        return (
            filtered,  # elements
            True,  # leaves-hidden
            "Show all nodes",  # button label
            f"Hidden {len(leaves)} leaf node(s) on load.",  # status
        )

    # Button clicked -> toggle
    if triggered_id == "btn-toggle-leaves":
        new_hidden = not bool(leaves_hidden)
        if new_hidden:
            filtered, leaves = filter_out_leaves(all_elements, keep_root=True)
            return filtered, True, "Show all nodes", f"Hidden {len(leaves)} leaf node(s)."
        else:
            return all_elements, False, "Hide leaf nodes", "Showing all nodes."

    # Default: unchanged if another control triggered this callback
    return all_elements, bool(leaves_hidden), (
        "Show all nodes" if leaves_hidden else "Hide leaf nodes"
    ), ""


@app.callback(
    Output("node-info-panel", "children"),
    Input("cyto-graph", "tapNodeData"),
)
def update_node_info_panel(tap_node_data):
    return show_node_info(tap_node_data)


@app.callback(
    Output("cyto-graph", "generateImage"),
    Input("btn-export-png", "n_clicks"),
    prevent_initial_call=True,
)
def export_current_view(n_clicks):
    if not n_clicks:
        return no_update
    # Export exactly what's on screen (viewport)
    return {
        "type": "png",
        "action": "download",
        "filename": f"gating_network_view_{n_clicks}",
        "scale": 1000,  # dpi
        "full": True
    }


@app.callback(
    Output("cyto-graph", "layout"),
    Output("current-layout-type", "data"),
    Output("layout-type-display", "children"),
    Output("breadthfirst-controls", "style"),
    Output("cose-controls", "style"),
    Input("btn-toggle-layout", "n_clicks"),
    Input("layout-params", "data"),
    State("current-layout-type", "data"),
    prevent_initial_call=False,
)
def update_layout(n_clicks, layout_params, current_layout_type):
    """
    Update layout type and parameters, and show/hide appropriate controls.
    """
    triggered_id = get_triggered_id()
    
    # Determine layout type
    if triggered_id == "btn-toggle-layout" and n_clicks:
        # Toggle layout type
        new_layout_type = "cose" if current_layout_type == "breadthfirst" else "breadthfirst"
    else:
        # Use current layout type (initial load or parameter update)
        new_layout_type = current_layout_type or "breadthfirst"
    
    # Ensure layout_params is not None
    if layout_params is None:
        layout_params = {"spacingFactor": 1.15, "padding": 30, "nodeRepulsion": 20000, "idealEdgeLength": 200}
    
    # Create layout with current parameters
    layout = make_layout(new_layout_type, **layout_params)
    
    # Create layout type display
    layout_display = html.Div(
        [
            html.Strong("Current Layout: "),
            html.Span(new_layout_type.upper(), style={"fontSize": "1.1rem", "fontWeight": "bold"}),
        ],
    )
    
    # Show/hide controls based on layout type
    if new_layout_type == "breadthfirst":
        bf_style = {"display": "block"}
        cose_style = {"display": "none"}
    else:  # cose
        bf_style = {"display": "none"}
        cose_style = {"display": "block"}
    
    return layout, new_layout_type, layout_display, bf_style, cose_style


@app.callback(
    Output("layout-params", "data"),
    Input("slider-spacing-factor", "value"),
    Input("slider-padding-bf", "value"),
    Input("slider-node-repulsion", "value"),
    Input("slider-edge-length", "value"),
    Input("slider-padding-cose", "value"),
    State("layout-params", "data"),
    State("current-layout-type", "data"),
    prevent_initial_call=True,
)
def update_layout_params(spacing_factor, padding_bf, node_repulsion, edge_length, padding_cose, current_params, layout_type):
    """
    Update layout parameters when sliders change.
    """
    if not current_params:
        current_params = {"spacingFactor": 1.15, "padding": 30, "nodeRepulsion": 20000, "idealEdgeLength": 200}
    
    # Create a copy to avoid mutating the state
    updated_params = current_params.copy()
    
    # Update parameters based on which slider was triggered
    triggered_id = get_triggered_id()
    
    if triggered_id == "slider-spacing-factor" and spacing_factor is not None:
        updated_params["spacingFactor"] = spacing_factor
    elif triggered_id == "slider-padding-bf" and padding_bf is not None:
        updated_params["padding"] = padding_bf
    elif triggered_id == "slider-node-repulsion" and node_repulsion is not None:
        updated_params["nodeRepulsion"] = node_repulsion
    elif triggered_id == "slider-edge-length" and edge_length is not None:
        updated_params["idealEdgeLength"] = edge_length
    elif triggered_id == "slider-padding-cose" and padding_cose is not None:
        updated_params["padding"] = padding_cose
    
    return updated_params


@app.callback(
    Output("slider-spacing-factor", "value"),
    Output("slider-padding-bf", "value"),
    Output("slider-node-repulsion", "value"),
    Output("slider-edge-length", "value"),
    Output("slider-padding-cose", "value"),
    Input("layout-params", "data"),
    prevent_initial_call=True,
)
def update_slider_values(layout_params):
    """
    Update slider values when layout parameters change (e.g., when switching layouts).
    """
    if not layout_params:
        layout_params = {"spacingFactor": 1.15, "padding": 30, "nodeRepulsion": 20000, "idealEdgeLength": 200}
    
    return (
        layout_params.get("spacingFactor", 1.15),
        layout_params.get("padding", 30),
        layout_params.get("nodeRepulsion", 20000),
        layout_params.get("idealEdgeLength", 200),
        layout_params.get("padding", 50),
    )


# --- Main ---
if __name__ == "__main__":
    app.run(debug=True)
