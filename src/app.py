# app.py
from pathlib import Path
import os
import io
import base64
import tempfile

import pandas as pd
import matplotlib
import matplotlib.cm as cm
import matplotlib.colors as mcolors

from dash import Dash, html, dcc, Input, Output, State, callback_context, no_update, ALL, clientside_callback, ClientsideFunction

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


def get_all_downstream_nodes(node_id, all_elements):
    """
    Find all downstream nodes (descendants) from a given node.
    Uses breadth-first search to traverse the graph.
    
    Args:
        node_id: The ID of the starting node
        all_elements: List of all graph elements (nodes + edges)
        
    Returns:
        Set of node IDs that are downstream from the given node
    """
    if not all_elements or not node_id:
        return set()
    
    # Build adjacency list (parent -> children)
    edges = [el["data"] for el in all_elements if "source" in el.get("data", {})]
    children_map = {}
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if source not in children_map:
            children_map[source] = []
        children_map[source].append(target)
    
    # BFS to find all descendants
    downstream_nodes = set()
    queue = [node_id]
    
    while queue:
        current = queue.pop(0)
        if current in children_map:
            for child in children_map[current]:
                if child not in downstream_nodes:
                    downstream_nodes.add(child)
                    queue.append(child)
    
    return downstream_nodes


def get_all_upstream_nodes(node_id, all_elements):
    """
    Find all upstream nodes (ancestors) from a given node.
    Uses breadth-first search to traverse the graph backwards.
    
    Args:
        node_id: The ID of the starting node
        all_elements: List of all graph elements (nodes + edges)
        
    Returns:
        Set of node IDs that are upstream from the given node
    """
    if not all_elements or not node_id:
        return set()
    
    # Build reverse adjacency list (child -> parent)
    edges = [el["data"] for el in all_elements if "source" in el.get("data", {})]
    parent_map = {}
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        parent_map[target] = source
    
    # BFS to find all ancestors
    upstream_nodes = set()
    queue = [node_id]
    
    while queue:
        current = queue.pop(0)
        if current in parent_map:
            parent = parent_map[current]
            if parent not in upstream_nodes:
                upstream_nodes.add(parent)
                queue.append(parent)
    
    return upstream_nodes


def get_color_palette():
    """
    Generate a colour palette for the colour picker.
    Returns a list of hex colour codes organised in rows.
    """
    # Common colours for scientific visualisation
    return [
        "#FF6B6B", "#4ECDC4", "#45B7D1", "#FFA07A", "#98D8C8", "#F7DC6F", "#BB8FCE", "#85C1E2",
        "#E74C3C", "#1ABC9C", "#3498DB", "#E67E22", "#27AE60", "#F39C12", "#9B59B6", "#16A085",
        "#C0392B", "#138D75", "#2874A6", "#D35400", "#229954", "#D68910", "#7D3C98", "#117A65",
        "#A93226", "#0E6655", "#1F618D", "#BA4A00", "#1E8449", "#B9770E", "#633974", "#0B5345",
        "#922B21", "#0B5345", "#154360", "#A04000", "#186A3B", "#9C640C", "#512E5F", "#0A3D2E",
        "#7B241C", "#0A3D2E", "#0C4A6E", "#873600", "#145A32", "#7E5109", "#3E2723", "#08302A",
        "#641E16", "#08302A", "#0A2E4A", "#6E2C00", "#0F5132", "#5E3F08", "#2C1810", "#062520",
        "#A0C4FF", "#B19CD9", "#FFB3BA", "#BAFFC9", "#FFFFBA", "#FFDFBA", "#BAE1FF", "#F0F0F0",
    ]


def create_color_picker_modal():
    """
    Create the colour picker modal component.
    """
    colors = get_color_palette()
    
    # Create colour swatches
    color_swatches = []
    for i, color in enumerate(colors):
        color_swatches.append(
            html.Button(
                "",
                id={"type": "color-swatch", "index": i},
                n_clicks=0,
                style={
                    "width": "40px",
                    "height": "40px",
                    "backgroundColor": color,
                    "border": "2px solid #ddd",
                    "borderRadius": "4px",
                    "cursor": "pointer",
                    "margin": "2px",
                    "transition": "all 0.2s",
                    "padding": 0,
                },
                title=color,
            )
        )
    
    return html.Div(
        id="color-picker-modal-overlay",
        style={
            "display": "none",  # Controlled by callback
            "position": "fixed",
            "top": 0,
            "left": 0,
            "width": "100%",
            "height": "100%",
            "backgroundColor": "rgba(0, 0, 0, 0.5)",
            "zIndex": 1000,
            "justifyContent": "center",
            "alignItems": "center",
        },
        children=[
            html.Div(
                id="color-picker-modal-content",
                style={
                    "backgroundColor": "#fff",
                    "borderRadius": "8px",
                    "padding": "2rem",
                    "maxWidth": "500px",
                    "width": "90%",
                    "boxShadow": "0 4px 6px rgba(0, 0, 0, 0.1)",
                    "position": "relative",
                },
                children=[
                    html.Div(
                        [
                            html.H3("Pick a Colour", style={"margin": 0, "marginBottom": "1rem"}),
                            html.Button(
                                "×",
                                id="btn-close-color-picker",
                                n_clicks=0,
                                style={
                                    "position": "absolute",
                                    "top": "1rem",
                                    "right": "1rem",
                                    "background": "none",
                                    "border": "none",
                                    "fontSize": "2rem",
                                    "cursor": "pointer",
                                    "color": "#666",
                                    "lineHeight": "1",
                                    "padding": "0",
                                    "width": "30px",
                                    "height": "30px",
                                },
                            ),
                        ],
                        style={"position": "relative", "marginBottom": "1.5rem"},
                    ),
                    html.Div(
                        [
                            html.Label("Colour Palette:", style={"display": "block", "marginBottom": "0.5rem", "fontWeight": "bold"}),
                            html.Div(
                                color_swatches,
                                style={
                                    "display": "grid",
                                    "gridTemplateColumns": "repeat(8, 1fr)",
                                    "gap": "4px",
                                    "marginBottom": "1.5rem",
                                    "maxHeight": "300px",
                                    "overflowY": "auto",
                                },
                            ),
                        ],
                    ),
                    html.Div(
                        [
                            html.Label("Custom Hex:", style={"display": "block", "marginBottom": "0.5rem", "fontWeight": "bold"}),
                            html.Div(
                                [
                                    html.Div(
                                        id="color-picker-preview",
                                        style={
                                            "width": "60px",
                                            "height": "50px",
                                            "backgroundColor": "#A0C4FF",
                                            "border": "2px solid #333",
                                            "borderRadius": "4px",
                                            "marginRight": "0.5rem",
                                            "flexShrink": 0,
                                        },
                                    ),
                                    dcc.Input(
                                        id="color-picker-hex-input",
                                        type="text",
                                        placeholder="#A0C4FF",
                                        style={
                                            "flex": "1",
                                            "padding": "0.5rem",
                                            "fontSize": "0.9rem",
                                            "fontFamily": "monospace",
                                            "border": "1px solid #ccc",
                                            "borderRadius": "4px",
                                        },
                                    ),
                                ],
                                style={"display": "flex", "alignItems": "center", "marginBottom": "1.5rem"},
                            ),
                        ],
                    ),
                    html.Div(
                        [
                            html.Button(
                                "Cancel",
                                id="btn-cancel-color-picker",
                                n_clicks=0,
                                style={
                                    "padding": "0.5rem 1.5rem",
                                    "marginRight": "0.5rem",
                                    "cursor": "pointer",
                                    "border": "1px solid #ccc",
                                    "borderRadius": "4px",
                                    "backgroundColor": "#f5f5f5",
                                    "color": "#333",
                                },
                            ),
                            html.Button(
                                "Apply",
                                id="btn-apply-color-picker",
                                n_clicks=0,
                                style={
                                    "padding": "0.5rem 1.5rem",
                                    "cursor": "pointer",
                                    "border": "1px solid #4CAF50",
                                    "borderRadius": "4px",
                                    "backgroundColor": "#4CAF50",
                                    "color": "#fff",
                                },
                            ),
                        ],
                        style={"display": "flex", "justifyContent": "flex-end"},
                    ),
                ],
            ),
        ],
    )


def show_node_info(data, all_elements=None, hidden_state=None):
    """
    Display node information with name, colour, parent, and children.
    """
    if not data:
        return html.Div("Click a node to see details.")
    
    # Get node name (label)
    node_name = data.get("label", data.get("id", "Unknown"))
    node_id = data.get("id", "")
    
    # Get node color - check if node_colour is in data, otherwise use default
    node_color = data.get("node_colour", "#A0C4FF")
    
    # Find parent and children from graph structure
    parent_node = None
    children_nodes = []
    
    if all_elements and node_id:
        # Separate nodes and edges
        nodes = {el["data"]["id"]: el["data"] for el in all_elements if "source" not in el.get("data", {})}
        edges = [el["data"] for el in all_elements if "source" in el.get("data", {})]
        
        # Find parent (edge where this node is the target)
        for edge in edges:
            if edge.get("target") == node_id:
                parent_id = edge.get("source")
                if parent_id in nodes:
                    parent_node = nodes[parent_id]
                break
        
        # Find children (edges where this node is the source)
        for edge in edges:
            if edge.get("source") == node_id:
                child_id = edge.get("target")
                if child_id in nodes:
                    children_nodes.append(nodes[child_id])
    
    # Get node shape - check if node_shape is in data, otherwise use default
    node_shape = data.get("node_shape", "ellipse")
    
    # Build the display
    info_sections = [
        html.H4("Node Information", style={"marginTop": 0, "marginBottom": "1rem"}),
        html.Div(
            [
                html.Label("Name:", style={"display": "block", "marginBottom": "0.25rem", "fontWeight": "bold"}),
                dcc.Input(
                    id={"type": "node-edit-input", "field": "label", "node_id": node_id},
                    type="text",
                    value=node_name,
                    style={
                        "width": "100%",
                        "padding": "0.5rem",
                        "fontSize": "1rem",
                        "border": "1px solid #ccc",
                        "borderRadius": "4px",
                    },
                ),
            ],
            style={"marginBottom": "1rem"},
        ),
        html.Div(
            [
                html.Label("Colour:", style={"display": "block", "marginBottom": "0.25rem", "fontWeight": "bold"}),
                html.Button(
                    "",
                    id={"type": "btn-open-color-picker", "node_id": node_id},
                    n_clicks=0,
                    style={
                        "width": "50px",
                        "height": "40px",
                        "backgroundColor": node_color,
                        "border": "1px solid #333",
                        "borderRadius": "4px",
                        "cursor": "pointer",
                        "padding": 0,
                        "transition": "all 0.2s",
                    },
                    title="Click to pick a colour",
                ),
            ],
            style={"marginBottom": "1rem"},
        ),
        html.Div(
            [
                html.Label("Shape:", style={"display": "block", "marginBottom": "0.25rem", "fontWeight": "bold"}),
                dcc.Dropdown(
                    id={"type": "node-edit-input", "field": "node_shape", "node_id": node_id},
                    options=[
                        {"label": "Ellipse", "value": "ellipse"},
                        {"label": "Rectangle", "value": "rectangle"},
                        {"label": "Round Rectangle", "value": "round-rectangle"},
                        {"label": "Triangle", "value": "triangle"},
                        {"label": "Diamond", "value": "diamond"},
                        {"label": "Pentagon", "value": "pentagon"},
                        {"label": "Hexagon", "value": "hexagon"},
                        {"label": "Star", "value": "star"},
                    ],
                    value=node_shape,
                    clearable=False,
                    style={"width": "100%"},
                ),
            ],
            style={"marginBottom": "1rem"},
        ),
        html.Div(
            [
                html.Label("Apply to all downstream:", style={"display": "block", "marginBottom": "0.5rem", "fontWeight": "bold"}),
                html.Div(
                    [
                        html.Button(
                            "Apply Colour",
                            id={"type": "btn-apply-downstream", "action": "color", "node_id": node_id},
                            n_clicks=0,
                            style={
                                "flex": "1",
                                "marginRight": "0.5rem",
                                "padding": "0.5rem 1rem",
                                "fontSize": "0.85rem",
                                "cursor": "pointer",
                                "border": "1px solid #4CAF50",
                                "borderRadius": "4px",
                                "backgroundColor": "#4CAF50",
                                "color": "#fff",
                            },
                        ),
                        html.Button(
                            "Apply Shape",
                            id={"type": "btn-apply-downstream", "action": "shape", "node_id": node_id},
                            n_clicks=0,
                            style={
                                "flex": "1",
                                "padding": "0.5rem 1rem",
                                "fontSize": "0.85rem",
                                "cursor": "pointer",
                                "border": "1px solid #2196F3",
                                "borderRadius": "4px",
                                "backgroundColor": "#2196F3",
                                "color": "#fff",
                            },
                        ),
                    ],
                    style={"display": "flex", "width": "100%"},
                ),
            ],
            style={"marginBottom": "1rem"},
        ),
        html.Div(
            [
                html.Label("Hide nodes in visualiser:", style={"display": "block", "marginBottom": "0.5rem", "fontWeight": "bold"}),
                html.Div(
                    [
                        html.Button(
                            "Show Upstream" if (hidden_state and hidden_state.get("upstream") and hidden_state.get("node_id") == node_id) else "Hide Upstream",
                            id={"type": "btn-hide-nodes", "direction": "upstream", "node_id": node_id},
                            n_clicks=0,
                            style={
                                "flex": "1",
                                "marginRight": "0.5rem",
                                "padding": "0.5rem 1rem",
                                "fontSize": "0.9rem",
                                "cursor": "pointer",
                                "border": "1px solid #ccc",
                                "borderRadius": "4px",
                                "backgroundColor": "#fff",
                                "color": "#333",
                            },
                        ),
                        html.Button(
                            "Show Downstream" if (hidden_state and hidden_state.get("downstream") and hidden_state.get("node_id") == node_id) else "Hide Downstream",
                            id={"type": "btn-hide-nodes", "direction": "downstream", "node_id": node_id},
                            n_clicks=0,
                            style={
                                "flex": "1",
                                "padding": "0.5rem 1rem",
                                "fontSize": "0.9rem",
                                "cursor": "pointer",
                                "border": "1px solid #ccc",
                                "borderRadius": "4px",
                                "backgroundColor": "#fff",
                                "color": "#333",
                            },
                        ),
                    ],
                    style={"display": "flex", "width": "100%"},
                ),
            ],
            style={"marginBottom": "1rem"},
        ),
        html.Hr(),
    ]
    
    # Add parent section
    if parent_node:
        parent_name = parent_node.get("label", parent_node.get("id", "Unknown"))
        info_sections.append(
            html.Div(
                [
                    html.Strong("Parent: "),
                    html.Span(parent_name, style={"fontSize": "1rem"}),
                ],
                style={"marginBottom": "1rem"},
            )
        )
    else:
        info_sections.append(
            html.Div(
                [
                    html.Strong("Parent: "),
                    html.Span("None (root node)", style={"fontSize": "1rem", "fontStyle": "italic", "color": "#666"}),
                ],
                style={"marginBottom": "1rem"},
            )
        )
    
    # Add children section
    if children_nodes:
        children_list = html.Ul(
            [
                html.Li(child.get("label", child.get("id", "Unknown")), style={"marginBottom": "0.25rem"})
                for child in children_nodes
            ],
            style={"marginTop": "0.5rem", "paddingLeft": "1.5rem"},
        )
        info_sections.append(
            html.Div(
                [
                    html.Strong("Children: "),
                    children_list,
                ],
            )
        )
    else:
        info_sections.append(
            html.Div(
                [
                    html.Strong("Children: "),
                    html.Span("None (leaf node)", style={"fontSize": "1rem", "fontStyle": "italic", "color": "#666"}),
                ],
            )
        )
    
    return html.Div(info_sections)


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
            "padding": params.get("padding", 75),
        })
    else:  # cose
        base_layout.update({
            "padding": params.get("padding", 75),
            "randomize": False,
        "nodeOverlap": 1,
            "nodeRepulsion": params.get("nodeRepulsion", 20_000),
            "idealEdgeLength": params.get("idealEdgeLength", 1),
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
    dcc.Store(id="current-layout-type", data="cose"),  # track current layout type
    dcc.Store(id="layout-params", data={"spacingFactor": 1.15, "padding": 75, "nodeRepulsion": 20000, "idealEdgeLength": 1}),
    dcc.Store(id="selected-node-id", data=None),  # track currently selected node for editing
    dcc.Store(id="color-picker-modal-open", data=False),  # track if colour picker modal is open
    dcc.Store(id="color-picker-selected", data=None),  # temporarily store selected colour before applying
    dcc.Store(id="hidden-nodes-state", data={"upstream": False, "downstream": False, "node_id": None}),  # track which nodes are hidden
    dcc.Store(id="fullscreen-mode", data=False),  # track fullscreen mode state
]

# Window styling constants
WINDOW_STYLE = {
    "border": "1px solid #ddd",
    "borderRadius": "4px",
    "padding": "1rem",
    "backgroundColor": "#fafafa",
    "overflow": "auto",
}

# --- App Configuration ---
# Add Inter font and global styles
app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap">
        <style>
            * {
                font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            }
            /* Colour picker swatch hover effects */
            [id*="color-swatch"]:hover {
                transform: scale(1.1);
                border-color: #333 !important;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
                z-index: 10;
                position: relative;
            }
            /* Colour preview button hover effect */
            [id*="btn-open-color-picker"]:hover {
                transform: scale(1.05);
                box-shadow: 0 2px 6px rgba(0, 0, 0, 0.2);
            }
            /* Fullscreen mode styles */
            #visualiser-container.fullscreen {
                position: fixed !important;
                top: 0 !important;
                left: 0 !important;
                width: 100vw !important;
                height: 100vh !important;
                z-index: 9999 !important;
                gridColumn: unset !important;
                gridRow: unset !important;
                margin: 0 !important;
                border: none !important;
                borderRadius: 0 !important;
                padding: 1rem !important;
            }
            #visualiser-container.fullscreen #cyto-graph {
                height: calc(100vh - 100px) !important;
            }
            /* Position fullscreen button in top right corner */
            #visualiser-container.fullscreen #btn-fullscreen {
                position: fixed !important;
                top: 1rem !important;
                right: 1rem !important;
                z-index: 10000 !important;
                margin: 0 !important;
            }
        </style>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
'''

# --- Layout ---
app.layout = html.Div(
    [
        *stores,
        dcc.Download(id="download-csv"),
        html.Div(
            [
                # Top Left: Cytoscape Graph
                html.Div(
                    id="visualiser-container",
                    children=[
                        html.Div(
                            [
                                html.H4("Network Visualisation", style={"marginTop": 0, "flex": "1"}),
                                html.Button(
                                    "⛶",
                                    id="btn-fullscreen",
                                    n_clicks=0,
                                    title="Toggle fullscreen",
                                    style={
                                        "padding": "0.25rem 0.5rem",
                                        "fontSize": "1.2rem",
                                        "cursor": "pointer",
                                        "border": "1px solid #ccc",
                                        "borderRadius": "4px",
                                        "backgroundColor": "#fff",
                                        "color": "#333",
                                        "marginLeft": "0.5rem",
                                    },
                                ),
                            ],
                            style={"display": "flex", "alignItems": "center", "marginBottom": "0.5rem"},
                        ),
                cyto.Cytoscape(
                    id="cyto-graph",
                    elements=elements,
                            layout=make_layout("cose"),
                    stylesheet=cyto_stylesheet(),
                            style={"height": "calc(70vh - 80px)", "width": "100%", "backgroundColor": "#ffffff"},
                    minZoom=0.2,
                    maxZoom=2.5,
                    boxSelectionEnabled=True,
                ),
            ],
                    style={
                        **WINDOW_STYLE,
                        "gridColumn": "1",
                        "gridRow": "1",
                        "backgroundColor": "#ffffff",
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
                        html.Div(
                            [
                                html.Button(
                                    "Breadthfirst",
                                    id="btn-layout-breadthfirst",
                                    n_clicks=0,
                                    style={
                                        "flex": "1",
                                        "marginRight": "0.5rem",
                                        "padding": "0.5rem 1rem",
                                        "fontSize": "0.9rem",
                                    },
                                ),
                                html.Button(
                                    "Cose",
                                    id="btn-layout-cose",
                                    n_clicks=0,
                                    style={
                                        "flex": "1",
                                        "padding": "0.5rem 1rem",
                                        "fontSize": "0.9rem",
                                    },
                                ),
                            ],
                            style={"display": "flex", "width": "100%", "marginBottom": "1rem"},
                        ),
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
                                            value=75,
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
                                            min=1,
                                            max=500,
                                            step=1,
                                            value=1,
                                            marks={1: "1", 250: "250", 500: "500"},
                                            tooltip={"placement": "bottom", "always_visible": True},
                                        ),
                                        html.Label("Padding:", style={"display": "block", "marginTop": "1rem"}),
                                        dcc.Slider(
                                            id="slider-padding-cose",
                                            min=0,
                                            max=100,
                                            step=5,
                                            value=75,
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
                        html.Div(
                            [
                                html.Button(
                                    "Show all nodes",
                                    id="btn-show-all-nodes",
                                    n_clicks=0,
                                    style={
                                        "flex": "1",
                                        "marginRight": "0.5rem",
                                        "padding": "0.5rem 1rem",
                                        "fontSize": "0.9rem",
                                    },
                                ),
                                html.Button(
                                    "Hide leaf nodes",
                                    id="btn-hide-leaf-nodes",
                                    n_clicks=0,
                                    style={
                                        "flex": "1",
                                        "padding": "0.5rem 1rem",
                                        "fontSize": "0.9rem",
                                    },
                                ),
                            ],
                            style={"display": "flex", "width": "100%", "marginBottom": "1rem"},
                        ),
                        html.Button(
                            "Export PNG",
                            id="btn-export-png",
                            n_clicks=0,
                            style={
                                "width": "100%",
                                "padding": "0.5rem 1rem",
                                "fontSize": "0.9rem",
                                "cursor": "pointer",
                                "border": "1px solid #ccc",
                                "borderRadius": "4px",
                                "backgroundColor": "#fff",
                                "color": "#333",
                                "marginBottom": "1rem",
                            },
                        ),
                        html.Div(
                            [
                                html.Button(
                                    "Export CSV",
                                    id="btn-export-csv",
                                    n_clicks=0,
                                    style={
                                        "flex": "1",
                                        "marginRight": "0.5rem",
                                        "padding": "0.5rem 1rem",
                                        "fontSize": "0.9rem",
                                        "cursor": "pointer",
                                        "border": "1px solid #ccc",
                                        "borderRadius": "4px",
                                        "backgroundColor": "#fff",
                                        "color": "#333",
                                    },
                                ),
                                dcc.Upload(
                                    id="upload-csv",
                                    children=html.Div("Import CSV with Viridis Colouring"),
                                    style={
                                        "flex": "1",
                                        "padding": "0.5rem 1rem",
                                        "lineHeight": "1.5",
                                        "borderWidth": "1px",
                                        "borderStyle": "dashed",
                                        "borderRadius": "4px",
                                        "textAlign": "center",
                                        "cursor": "pointer",
                                        "backgroundColor": "#fafafa",
                                        "borderColor": "#ccc",
                                        "color": "#333",
                                        "display": "flex",
                                        "alignItems": "center",
                                        "justifyContent": "center",
                                        "fontSize": "0.9rem",
                                    },
                                    multiple=False,
                                ),
                            ],
                            style={"display": "flex", "width": "100%", "marginBottom": "1rem", "alignItems": "stretch"},
                        ),
                        dcc.Upload(
                            id="upload-wsp",
                            children=html.Div("Import New WSP"),
                            style={
                                "width": "100%",
                                "padding": "0.5rem 1rem",
                                "lineHeight": "1.5",
                                "borderWidth": "1px",
                                "borderStyle": "dashed",
                                "borderRadius": "4px",
                                "textAlign": "center",
                                "cursor": "pointer",
                                "backgroundColor": "#fafafa",
                                "borderColor": "#ccc",
                                "color": "#333",
                                "display": "flex",
                                "alignItems": "center",
                                "justifyContent": "center",
                                "fontSize": "0.9rem",
                            },
                            accept=".wsp",
                            multiple=False,
                        ),
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
        create_color_picker_modal(),
    ],
    style={
        "margin": 0, 
        "padding": 0, 
        "paddingBottom": "2rem", 
        "height": "100vh", 
        "overflow": "auto",
        "fontFamily": '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
    },
)


# --- Callbacks ---
@app.callback(
    Output("cyto-graph", "elements"),
    Output("leaves-hidden", "data"),
    Output("btn-show-all-nodes", "style"),
    Output("btn-hide-leaf-nodes", "style"),
    Input("btn-show-all-nodes", "n_clicks"),
    Input("btn-hide-leaf-nodes", "n_clicks"),
    State("leaves-hidden", "data"),
    State("all-elements", "data"),
    prevent_initial_call=False,
)
def toggle_leaves(show_all_clicks, hide_leaves_clicks, leaves_hidden, all_elements):
    # Safety on first render
    if not all_elements:
        base_style = {
            "flex": "1",
            "marginRight": "0.5rem",
            "padding": "0.5rem 1rem",
            "fontSize": "0.9rem",
            "cursor": "pointer",
            "border": "1px solid #ccc",
            "borderRadius": "4px",
        }
        return [], False, base_style, {**base_style, "backgroundColor": "#e0e0e0", "color": "#666", "opacity": 0.7, "cursor": "not-allowed", "boxShadow": "inset 0 2px 4px rgba(0,0,0,0.1)"}

    triggered_id = get_triggered_id()

    # Determine which button was clicked or initial state
    if triggered_id == "btn-show-all-nodes":
        new_hidden = False
    elif triggered_id == "btn-hide-leaf-nodes":
        new_hidden = True
    else:
        # Initial page load (no trigger): start with leaves hidden
        new_hidden = True

    # Filter elements based on new state
    if new_hidden:
        filtered, leaves = filter_out_leaves(all_elements, keep_root=True)
        elements = filtered
    else:
        elements = all_elements

    # Style buttons - active button is greyed out/disabled style, inactive is normal
    base_button_style = {
        "flex": "1",
        "marginRight": "0.5rem",
        "padding": "0.5rem 1rem",
        "fontSize": "0.9rem",
        "cursor": "pointer",
        "border": "1px solid #ccc",
        "borderRadius": "4px",
    }
    
    # First button always has marginRight, second button never does
    show_all_base = {**base_button_style}
    hide_leaves_base = {**base_button_style.copy()}
    hide_leaves_base.pop("marginRight", None)

    if new_hidden:
        # Hide leaf nodes is active
        show_all_style = {
            **show_all_base,
            "backgroundColor": "#fff",
            "color": "#333",
        }
        hide_leaves_style = {
            **hide_leaves_base,
            "backgroundColor": "#e0e0e0",
            "color": "#666",
            "opacity": 0.7,
            "cursor": "not-allowed",
            "boxShadow": "inset 0 2px 4px rgba(0,0,0,0.1)",
        }
    else:
        # Show all nodes is active
        show_all_style = {
            **show_all_base,
            "backgroundColor": "#e0e0e0",
            "color": "#666",
            "opacity": 0.7,
            "cursor": "not-allowed",
            "boxShadow": "inset 0 2px 4px rgba(0,0,0,0.1)",
        }
        hide_leaves_style = {
            **hide_leaves_base,
            "backgroundColor": "#fff",
            "color": "#333",
        }

    return elements, new_hidden, show_all_style, hide_leaves_style


@app.callback(
    Output("node-info-panel", "children"),
    Output("selected-node-id", "data"),
    Output("hidden-nodes-state", "data", allow_duplicate=True),
    Output("cyto-graph", "elements", allow_duplicate=True),
    Input("cyto-graph", "tapNodeData"),
    State("all-elements", "data"),
    State("hidden-nodes-state", "data"),
    State("cyto-graph", "elements"),
    State("leaves-hidden", "data"),
    prevent_initial_call='initial_duplicate',
)
def update_node_info_panel(tap_node_data, all_elements, hidden_state, current_elements, leaves_hidden):
    node_id = tap_node_data.get("id") if tap_node_data else None
    
    # If selecting a different node, reset hidden state but preserve current visible elements
    if node_id and hidden_state and hidden_state.get("node_id") and hidden_state.get("node_id") != node_id:
        # Reset hidden state (since it's tied to the previous node)
        new_hidden_state = {"upstream": False, "downstream": False, "node_id": None}
        # Preserve current visible elements (which already have upstream/downstream filtering applied)
        # Ensure leaves are filtered if needed (current_elements should already have this, but verify)
        elements_to_return = current_elements if current_elements else all_elements
        if leaves_hidden and elements_to_return == all_elements:
            # Only filter if we fell back to all_elements and leaves should be hidden
            elements_to_return, _ = filter_out_leaves(all_elements, keep_root=True)
        return show_node_info(tap_node_data, all_elements, new_hidden_state), node_id, new_hidden_state, elements_to_return
    
    # Otherwise, keep current state
    return show_node_info(tap_node_data, all_elements, hidden_state), node_id, no_update, no_update


@app.callback(
    Output("cyto-graph", "elements", allow_duplicate=True),
    Output("all-elements", "data", allow_duplicate=True),
    Input({"type": "node-edit-input", "field": "label", "node_id": ALL}, "value"),
    Input({"type": "node-edit-input", "field": "node_shape", "node_id": ALL}, "value"),
    State("all-elements", "data"),
    State("cyto-graph", "elements"),
    State("selected-node-id", "data"),
    prevent_initial_call=True,
)
def update_node_properties(label_values, shape_values, all_elements, current_elements, selected_node_id):
    """
    Update node properties (name, colour, shape) when edited in the node info panel.
    """
    if not all_elements or not current_elements or not selected_node_id:
        return no_update, no_update, []
    
    triggered = callback_context.triggered[0] if callback_context.triggered else None
    if not triggered:
        return no_update, no_update, []
    
    # Parse the triggered prop_id to get which field was changed
    prop_id = triggered["prop_id"]
    if "node-edit-input" not in prop_id:
        return no_update, no_update, []
    
    # Extract field from the prop_id
    import json
    try:
        json_part = prop_id.split(".value")[0]
        input_info = json.loads(json_part)
        field = input_info.get("field")
        node_id = input_info.get("node_id")
    except:
        return no_update, no_update
    
    # Use selected_node_id to find the correct value
    # Since we're using ALL, we need to find which input corresponds to selected_node_id
    # For simplicity, if there's only one input (the selected node), use the first value
    new_value = None
    
    if field == "label" and label_values:
        # Find the value for the selected node
        for i, val in enumerate(label_values):
            if val is not None:
                new_value = val
                break
    elif field == "node_shape" and shape_values:
        for i, val in enumerate(shape_values):
            if val is not None:
                new_value = val
                break
    
    if new_value is None:
        return no_update, no_update
    
    # Use selected_node_id (from Store) as the node to update
    node_id = selected_node_id
    
    # Update all_elements
    updated_all = []
    for el in all_elements:
        el_copy = el.copy()
        if "source" not in el.get("data", {}):  # It's a node
            if el["data"].get("id") == node_id:
                el_copy["data"] = el["data"].copy()
                if field == "label":
                    el_copy["data"]["label"] = new_value
                elif field == "node_colour":
                    el_copy["data"]["node_colour"] = new_value
                elif field == "node_shape":
                    el_copy["data"]["node_shape"] = new_value
        updated_all.append(el_copy)
    
    # Update current_elements (visible elements)
    updated_current = []
    for el in current_elements:
        el_copy = el.copy()
        if "source" not in el.get("data", {}):  # It's a node
            if el["data"].get("id") == node_id:
                el_copy["data"] = el["data"].copy()
                if field == "label":
                    el_copy["data"]["label"] = new_value
                elif field == "node_colour":
                    el_copy["data"]["node_colour"] = new_value
                elif field == "node_shape":
                    el_copy["data"]["node_shape"] = new_value
        updated_current.append(el_copy)
    
    return updated_current, updated_all


@app.callback(
    Output("cyto-graph", "generateImage"),
    Input("btn-export-png", "n_clicks"),
    prevent_initial_call=True,
)
def export_current_view(n_clicks):
    if not n_clicks:
        return no_update
    # Export full graph at high resolution
    return {
        "type": "png",
        "action": "download",
        "filename": f"gating_network_view_{n_clicks}",
        "options": {
            "full": True,
            "scale": 10,  # 10x multiplier for very high resolution
            "maxWidth": 8000,  # Prevent browser crashes on very large networks
            "maxHeight": 8000,
            "bg": "#ffffff"  # Explicit white background
        }
    }


@app.callback(
    Output("download-csv", "data"),
    Input("btn-export-csv", "n_clicks"),
    State("all-elements", "data"),
    prevent_initial_call=True,
)
def export_network_to_csv(n_clicks, all_elements):
    """
    Export network nodes to CSV with columns: node_name, shape, colour, parameter
    """
    if not n_clicks or not all_elements:
        return no_update
    
    # Extract all nodes
    nodes = [el for el in all_elements if el.get("data") and "source" not in el.get("data", {})]
    
    # Build DataFrame
    rows = []
    for node in nodes:
        data = node.get("data", {})
        rows.append({
            "node_name": data.get("label", data.get("id", "Unknown")),
            "shape": data.get("node_shape", "ellipse"),
            "colour": data.get("node_colour", "#A0C4FF"),
            "parameter": ""  # Empty column for user to fill
        })
    
    df = pd.DataFrame(rows)
    
    # Convert to CSV string
    csv_string = df.to_csv(index=False)
    
    # Return download data
    return {
        "content": csv_string,
        "filename": f"network_export_{n_clicks}.csv",
        "type": "text/csv"
    }


@app.callback(
    Output("cyto-graph", "elements", allow_duplicate=True),
    Output("all-elements", "data", allow_duplicate=True),
    Output("upload-csv", "children", allow_duplicate=True),
    Input("upload-csv", "contents"),
    State("upload-csv", "filename"),
    State("all-elements", "data"),
    State("cyto-graph", "elements"),
    prevent_initial_call=True,
)
def import_csv_and_apply_colors(contents, filename, all_elements, current_elements):
    """
    Import CSV file and apply viridis colour scheme based on parameter column
    """
    if not contents or not filename:
        return no_update, no_update, no_update
    
    # Parse uploaded file
    try:
        content_type, content_string = contents.split(',')
        decoded = base64.b64decode(content_string)
        
        # Read CSV with pandas
        df = pd.read_csv(io.StringIO(decoded.decode('utf-8')))
        
        # Validate required columns
        required_columns = ["node_name", "shape", "colour", "parameter"]
        if not all(col in df.columns for col in required_columns):
            return no_update, no_update, html.Div([
                "Error: CSV must have columns: " + ", ".join(required_columns),
                html.Br(),
                "Import CSV with Viridis Colouring"
            ])
        
        # Filter out rows with missing parameter values
        df_valid = df[df["parameter"].notna() & (df["parameter"] != "")]
        
        # Convert parameter to numeric, coercing errors to NaN
        df_valid["parameter"] = pd.to_numeric(df_valid["parameter"], errors='coerce')
        df_valid = df_valid[df_valid["parameter"].notna()]
        
        if len(df_valid) == 0:
            return no_update, no_update, html.Div([
                "Error: No valid numeric parameter values found",
                html.Br(),
                "Import CSV with Viridis Colouring"
            ])
        
        # Calculate min/max for normalization
        param_min = df_valid["parameter"].min()
        param_max = df_valid["parameter"].max()
        
        # Handle case where all parameters are the same
        if param_min == param_max:
            normalized_values = [0.5] * len(df_valid)  # Use middle of viridis
        else:
            normalized_values = (df_valid["parameter"] - param_min) / (param_max - param_min)
        
        # Get viridis colormap
        viridis = matplotlib.colormaps['viridis']
        
        # Create mapping of node_name to viridis colour
        node_color_map = {}
        missing_nodes = []
        
        # Convert normalized_values to list for easier indexing
        if isinstance(normalized_values, pd.Series):
            normalized_list = normalized_values.tolist()
        else:
            normalized_list = list(normalized_values) if hasattr(normalized_values, '__iter__') else [normalized_values]
        
        # Reset index to ensure sequential indexing
        df_valid = df_valid.reset_index(drop=True)
        
        for idx, row in df_valid.iterrows():
            node_name = str(row["node_name"])
            normalized = normalized_list[idx]
            rgb = viridis(normalized)[:3]  # Get RGB (first 3 values)
            hex_color = mcolors.rgb2hex(rgb)
            
            # Find matching node
            node_found = False
            for el in all_elements:
                if "source" not in el.get("data", {}):
                    node_data = el.get("data", {})
                    if node_data.get("label") == node_name or node_data.get("id") == node_name:
                        node_color_map[node_data.get("id")] = hex_color
                        node_found = True
                        break
            
            if not node_found:
                missing_nodes.append(node_name)
        
        # Update all_elements
        updated_all = []
        for el in all_elements:
            el_copy = el.copy()
            if "source" not in el.get("data", {}):  # It's a node
                node_id = el["data"].get("id")
                if node_id in node_color_map:
                    el_copy["data"] = el["data"].copy()
                    el_copy["data"]["node_colour"] = node_color_map[node_id]
            updated_all.append(el_copy)
        
        # Update current_elements
        updated_current = []
        for el in current_elements:
            el_copy = el.copy()
            if "source" not in el.get("data", {}):  # It's a node
                node_id = el["data"].get("id")
                if node_id in node_color_map:
                    el_copy["data"] = el["data"].copy()
                    el_copy["data"]["node_colour"] = node_color_map[node_id]
            updated_current.append(el_copy)
        
        # Create upload component message
        if missing_nodes:
            warning_msg = f"Warning: {len(missing_nodes)} node(s) not found: {', '.join(missing_nodes[:5])}"
            if len(missing_nodes) > 5:
                warning_msg += f" and {len(missing_nodes) - 5} more"
            upload_children = html.Div([
                html.Div(warning_msg, style={"color": "#ff9800", "marginBottom": "0.5rem"}),
                "Import CSV with Viridis Colouring"
            ])
        else:
            upload_children = html.Div([
                html.Div(f"Successfully imported {len(df_valid)} nodes", style={"color": "#4CAF50", "marginBottom": "0.5rem"})
            ])
        
        return updated_current, updated_all, upload_children
        
    except Exception as e:
        error_msg = f"Error importing CSV: {str(e)}"
        return no_update, no_update, html.Div([
            html.Div(error_msg, style={"color": "#f44336", "marginBottom": "0.5rem"}),
            "Import CSV with Viridis Colouring"
        ])


@app.callback(
    Output("cyto-graph", "elements", allow_duplicate=True),
    Output("all-elements", "data", allow_duplicate=True),
    Output("leaves-hidden", "data", allow_duplicate=True),
    Output("selected-node-id", "data", allow_duplicate=True),
    Output("upload-wsp", "children", allow_duplicate=True),
    Input("upload-wsp", "contents"),
    State("upload-wsp", "filename"),
    prevent_initial_call=True,
)
def import_wsp_file(contents, filename):
    """
    Import WSP file and replace the current network with fresh styling.
    """
    if not contents or not filename:
        return no_update, no_update, no_update, no_update, no_update
    
    # Validate file extension
    if not filename.lower().endswith('.wsp'):
        error_msg = "Error: File must be a .wsp file"
        return no_update, no_update, no_update, no_update, html.Div([
            html.Div(error_msg, style={"color": "#f44336", "marginBottom": "0.5rem"}),
            "Import New WSP"
        ])
    
    # Parse uploaded file
    try:
        content_type, content_string = contents.split(',')
        decoded = base64.b64decode(content_string)
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.wsp') as tmp_file:
            tmp_file.write(decoded)
            tmp_path = tmp_file.name
        
        try:
            # Convert WSP to Cytoscape elements
            cy = wsp_to_cyto(tmp_path)
            elements_all = cy["nodes"] + cy["edges"]
            
            # Apply default styling to all nodes
            for node in elements_all:
                if "source" not in node.get("data", {}):
                    node["data"]["node_colour"] = "#A0C4FF"
                    node["data"]["node_shape"] = "ellipse"
            
            # Filter leaves (start with leaves hidden)
            elements_filtered, _ = filter_out_leaves(elements_all, keep_root=True)
            
            # Create success message
            upload_children = html.Div(
                html.Div(
                    f"Successfully loaded WSP file: {filename} ({len(elements_all)} elements)",
                    style={"color": "#4CAF50", "marginBottom": "0.5rem"}
                )
            )
            
            return (
                elements_filtered,  # cyto-graph elements
                elements_all,       # all-elements store
                True,               # leaves-hidden (start with leaves hidden)
                None,               # selected-node-id (clear selection)
                upload_children     # upload component message
            )
            
        finally:
            # Clean up temporary file
            try:
                os.unlink(tmp_path)
            except:
                pass
        
    except Exception as e:
        error_msg = f"Error loading WSP file: {str(e)}"
        return no_update, no_update, no_update, no_update, html.Div([
            html.Div(error_msg, style={"color": "#f44336", "marginBottom": "0.5rem"}),
            "Import New WSP"
        ])


@app.callback(
    Output("cyto-graph", "layout"),
    Output("current-layout-type", "data"),
    Output("btn-layout-breadthfirst", "style"),
    Output("btn-layout-cose", "style"),
    Output("breadthfirst-controls", "style"),
    Output("cose-controls", "style"),
    Input("btn-layout-breadthfirst", "n_clicks"),
    Input("btn-layout-cose", "n_clicks"),
    Input("layout-params", "data"),
    State("current-layout-type", "data"),
    prevent_initial_call=False,
)
def update_layout(bf_clicks, cose_clicks, layout_params, current_layout_type):
    """
    Update layout type and parameters, and show/hide appropriate controls.
    Style buttons to show which is active.
    """
    triggered_id = get_triggered_id()
    
    # Determine layout type based on which button was clicked
    if triggered_id == "btn-layout-breadthfirst":
        new_layout_type = "breadthfirst"
    elif triggered_id == "btn-layout-cose":
        new_layout_type = "cose"
    else:
        # Use current layout type (initial load or parameter update)
        new_layout_type = current_layout_type or "cose"
    
    # Ensure layout_params is not None
    if layout_params is None:
        layout_params = {"spacingFactor": 1.15, "padding": 75, "nodeRepulsion": 20000, "idealEdgeLength": 1}
    
    # Create layout with current parameters
    layout = make_layout(new_layout_type, **layout_params)
    
    # Style buttons - active button is greyed out/disabled style, inactive is normal
    base_button_style = {
        "flex": "1",
        "padding": "0.5rem 1rem",
        "fontSize": "0.9rem",
        "cursor": "pointer",
        "border": "1px solid #ccc",
        "borderRadius": "4px",
    }
    
    # First button always has marginRight, second button never does
    bf_base = {**base_button_style, "marginRight": "0.5rem"}
    cose_base = {**base_button_style.copy()}
    
    if new_layout_type == "breadthfirst":
        bf_button_style = {
            **bf_base,
            "backgroundColor": "#e0e0e0",
            "color": "#666",
            "opacity": 0.7,
            "cursor": "not-allowed",
            "boxShadow": "inset 0 2px 4px rgba(0,0,0,0.1)",
        }
        cose_button_style = {
            **cose_base,
            "backgroundColor": "#fff",
            "color": "#333",
        }
    else:  # cose
        bf_button_style = {
            **bf_base,
            "backgroundColor": "#fff",
            "color": "#333",
        }
        cose_button_style = {
            **cose_base,
            "backgroundColor": "#e0e0e0",
            "color": "#666",
            "opacity": 0.7,
            "cursor": "not-allowed",
            "boxShadow": "inset 0 2px 4px rgba(0,0,0,0.1)",
        }
    
    # Show/hide controls based on layout type
    if new_layout_type == "breadthfirst":
        bf_style = {"display": "block"}
        cose_style = {"display": "none"}
    else:  # cose
        bf_style = {"display": "none"}
        cose_style = {"display": "block"}
    
    return layout, new_layout_type, bf_button_style, cose_button_style, bf_style, cose_style


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
        current_params = {"spacingFactor": 1.15, "padding": 75, "nodeRepulsion": 20000, "idealEdgeLength": 200}
    
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


# --- Colour Picker Modal Callbacks ---

@app.callback(
    Output("color-picker-modal-open", "data"),
    Output("color-picker-selected", "data"),
    Output("color-picker-modal-overlay", "style"),
    Output("color-picker-preview", "style"),
    Output("color-picker-hex-input", "value"),
    Input({"type": "btn-open-color-picker", "node_id": ALL}, "n_clicks"),
    Input("btn-close-color-picker", "n_clicks"),
    Input("btn-cancel-color-picker", "n_clicks"),
    Input({"type": "color-swatch", "index": ALL}, "n_clicks"),
    Input("color-picker-hex-input", "value"),
    State("color-picker-modal-open", "data"),
    State("color-picker-selected", "data"),
    State("selected-node-id", "data"),
    State("all-elements", "data"),
    prevent_initial_call=True,
)
def handle_color_picker_modal(
    open_btn_clicks, close_btn_clicks, cancel_btn_clicks, swatch_clicks, hex_input,
    modal_open, selected_color, selected_node_id, all_elements
):
    """
    Handle opening/closing the colour picker modal and colour selection.
    """
    ctx = callback_context
    if not ctx.triggered:
        return no_update, no_update, no_update, no_update, no_update
    
    triggered_id = get_triggered_id()
    
    # Get current node colour for initial preview
    current_node_color = "#A0C4FF"
    if selected_node_id and all_elements:
        for el in all_elements:
            if "source" not in el.get("data", {}) and el["data"].get("id") == selected_node_id:
                current_node_color = el["data"].get("node_colour", "#A0C4FF")
                break
    
    # Handle opening modal
    if "btn-open-color-picker" in triggered_id:
        # Only open if there's an actual click (n_clicks > 0)
        if open_btn_clicks and any(x and x > 0 for x in open_btn_clicks):
            modal_style = {
                "display": "flex",
                "position": "fixed",
                "top": 0,
                "left": 0,
                "width": "100%",
                "height": "100%",
                "backgroundColor": "rgba(0, 0, 0, 0.5)",
                "zIndex": 1000,
                "justifyContent": "center",
                "alignItems": "center",
            }
            preview_style = {
                "width": "60px",
                "height": "50px",
                "backgroundColor": current_node_color,
                "border": "2px solid #333",
                "borderRadius": "4px",
                "marginRight": "0.5rem",
                "flexShrink": 0,
            }
            return True, current_node_color, modal_style, preview_style, current_node_color
        else:
            return no_update, no_update, no_update, no_update, no_update
    
    # Handle closing modal (close or cancel buttons)
    if triggered_id in ["btn-close-color-picker", "btn-cancel-color-picker"]:
        modal_style = {
            "display": "none",
            "position": "fixed",
            "top": 0,
            "left": 0,
            "width": "100%",
            "height": "100%",
            "backgroundColor": "rgba(0, 0, 0, 0.5)",
            "zIndex": 1000,
            "justifyContent": "center",
            "alignItems": "center",
        }
        return False, None, modal_style, no_update, no_update
    
    # Handle colour swatch selection
    if "color-swatch" in triggered_id:
        colors = get_color_palette()
        try:
            import json
            json_part = triggered_id.split(".n_clicks")[0]
            swatch_info = json.loads(json_part)
            index = swatch_info.get("index")
            if index is not None and 0 <= index < len(colors):
                selected_color = colors[index]
                preview_style = {
                    "width": "60px",
                    "height": "50px",
                    "backgroundColor": selected_color,
                    "border": "2px solid #333",
                    "borderRadius": "4px",
                    "marginRight": "0.5rem",
                    "flexShrink": 0,
                }
                return no_update, selected_color, no_update, preview_style, selected_color
        except:
            pass
    
    # Handle hex input change
    if triggered_id == "color-picker-hex-input":
        if hex_input:
            hex_input = hex_input.strip()
            if hex_input.startswith("#") and len(hex_input) == 7:  # Valid hex colour
                preview_style = {
                    "width": "60px",
                    "height": "50px",
                    "backgroundColor": hex_input,
                    "border": "2px solid #333",
                    "borderRadius": "4px",
                    "marginRight": "0.5rem",
                    "flexShrink": 0,
                }
                return no_update, hex_input, no_update, preview_style, hex_input
        # Even if invalid, allow typing (don't block input)
        return no_update, no_update, no_update, no_update, hex_input
    
    return no_update, no_update, no_update, no_update, no_update


@app.callback(
    Output("cyto-graph", "elements", allow_duplicate=True),
    Output("all-elements", "data", allow_duplicate=True),
    Output("color-picker-modal-open", "data", allow_duplicate=True),
    Output("color-picker-modal-overlay", "style", allow_duplicate=True),
    Output({"type": "btn-open-color-picker", "node_id": ALL}, "style", allow_duplicate=True),
    Input("btn-apply-color-picker", "n_clicks"),
    State("color-picker-selected", "data"),
    State("selected-node-id", "data"),
    State("all-elements", "data"),
    State("cyto-graph", "elements"),
    State({"type": "btn-open-color-picker", "node_id": ALL}, "style"),
    prevent_initial_call=True,
)
def apply_color_from_picker(
    apply_clicks, selected_color, selected_node_id, all_elements, current_elements, current_button_styles
):
    """
    Apply the selected colour from the colour picker to the node.
    """
    if not apply_clicks or not selected_color or not selected_node_id:
        return no_update, no_update, no_update, no_update, no_update
    
    # Update all_elements
    updated_all = []
    for el in all_elements:
        el_copy = el.copy()
        if "source" not in el.get("data", {}):  # It's a node
            if el["data"].get("id") == selected_node_id:
                el_copy["data"] = el["data"].copy()
                el_copy["data"]["node_colour"] = selected_color
        updated_all.append(el_copy)
    
    # Update current_elements
    updated_current = []
    for el in current_elements:
        el_copy = el.copy()
        if "source" not in el.get("data", {}):  # It's a node
            if el["data"].get("id") == selected_node_id:
                el_copy["data"] = el["data"].copy()
                el_copy["data"]["node_colour"] = selected_color
        updated_current.append(el_copy)
    
    # Close modal
    modal_style = {
        "display": "none",
        "position": "fixed",
        "top": 0,
        "left": 0,
        "width": "100%",
        "height": "100%",
        "backgroundColor": "rgba(0, 0, 0, 0.5)",
        "zIndex": 1000,
        "justifyContent": "center",
        "alignItems": "center",
    }
    
    # Update colour preview button style
    # Since only one node is selected at a time, we need to update the button style
    # The button ID is {"type": "btn-open-color-picker", "node_id": selected_node_id}
    # With ALL pattern, we need to return a list matching all buttons
    # We'll update all buttons, but only the one for the selected node will be visible
    
    color_preview_style = {
        "width": "50px",
        "height": "40px",
        "backgroundColor": selected_color,
        "border": "1px solid #333",
        "borderRadius": "4px",
        "cursor": "pointer",
        "padding": 0,
        "transition": "all 0.2s",
    }
    
    # Return updated styles - since we're using ALL, we need to return a list
    # We'll preserve existing styles for other buttons and update the matching one
    if current_button_styles:
        updated_styles = []
        for style in current_button_styles:
            if style and isinstance(style, dict):
                # Update the style, preserving other properties
                updated_style = style.copy()
                updated_style["backgroundColor"] = selected_color
                updated_styles.append(updated_style)
            else:
                updated_styles.append(color_preview_style)
    else:
        # If no current styles, return the new style
        updated_styles = [color_preview_style]
    
    return updated_current, updated_all, False, modal_style, updated_styles


@app.callback(
    Output("cyto-graph", "elements", allow_duplicate=True),
    Output("all-elements", "data", allow_duplicate=True),
    Input({"type": "btn-apply-downstream", "action": "color", "node_id": ALL}, "n_clicks"),
    Input({"type": "btn-apply-downstream", "action": "shape", "node_id": ALL}, "n_clicks"),
    State("selected-node-id", "data"),
    State("all-elements", "data"),
    State("cyto-graph", "elements"),
    State({"type": "node-edit-input", "field": "node_shape", "node_id": ALL}, "value"),
    prevent_initial_call=True,
)
def apply_to_all_downstream(
    color_clicks, shape_clicks, selected_node_id, all_elements, current_elements, shape_values
):
    """
    Apply colour or shape to all downstream nodes from the selected node.
    Uses the current colour/shape of the selected node.
    """
    if not selected_node_id or not all_elements or not current_elements:
        return no_update, no_update
    
    triggered = callback_context.triggered[0] if callback_context.triggered else None
    if not triggered:
        return no_update, no_update
    
    # Parse the triggered prop_id to get which action was clicked
    prop_id = triggered["prop_id"]
    if "btn-apply-downstream" not in prop_id:
        return no_update, no_update
    
    # Extract action and node_id from the prop_id
    import json
    try:
        json_part = prop_id.split(".n_clicks")[0]
        button_info = json.loads(json_part)
        action = button_info.get("action")
        node_id = button_info.get("node_id")
    except:
        return no_update, no_update
    
    # Verify this is for the selected node
    if node_id != selected_node_id:
        return no_update, no_update
    
    # Check if there was an actual click
    if action == "color":
        if not color_clicks or not any(x and x > 0 for x in color_clicks):
            return no_update, no_update
        # Get the current colour from the selected node
        selected_color = None
        for el in all_elements:
            if "source" not in el.get("data", {}) and el["data"].get("id") == selected_node_id:
                selected_color = el["data"].get("node_colour", "#A0C4FF")
                break
        if not selected_color:
            return no_update, no_update
    elif action == "shape":
        if not shape_clicks or not any(x and x > 0 for x in shape_clicks):
            return no_update, no_update
        # Get the current shape value from the dropdown
        if not shape_values or not any(v for v in shape_values):
            return no_update, no_update
        # Find the shape value for the selected node
        selected_shape = None
        for val in shape_values:
            if val:
                selected_shape = val
                break
        if not selected_shape:
            return no_update, no_update
    else:
        return no_update, no_update
    
    # Get all downstream nodes
    downstream_node_ids = get_all_downstream_nodes(selected_node_id, all_elements)
    
    if not downstream_node_ids:
        return no_update, no_update
    
    # Update all_elements
    updated_all = []
    for el in all_elements:
        el_copy = el.copy()
        if "source" not in el.get("data", {}):  # It's a node
            node_id = el["data"].get("id")
            if node_id in downstream_node_ids:
                el_copy["data"] = el["data"].copy()
                if action == "color":
                    el_copy["data"]["node_colour"] = selected_color
                elif action == "shape":
                    el_copy["data"]["node_shape"] = selected_shape
        updated_all.append(el_copy)
    
    # Update current_elements
    updated_current = []
    for el in current_elements:
        el_copy = el.copy()
        if "source" not in el.get("data", {}):  # It's a node
            node_id = el["data"].get("id")
            if node_id in downstream_node_ids:
                el_copy["data"] = el["data"].copy()
                if action == "color":
                    el_copy["data"]["node_colour"] = selected_color
                elif action == "shape":
                    el_copy["data"]["node_shape"] = selected_shape
        updated_current.append(el_copy)
    
    return updated_current, updated_all


@app.callback(
    Output("cyto-graph", "elements", allow_duplicate=True),
    Output("hidden-nodes-state", "data", allow_duplicate=True),
    Output("node-info-panel", "children", allow_duplicate=True),
    Input({"type": "btn-hide-nodes", "direction": ALL, "node_id": ALL}, "n_clicks"),
    State("selected-node-id", "data"),
    State("all-elements", "data"),
    State("cyto-graph", "elements"),
    State("hidden-nodes-state", "data"),
    State("leaves-hidden", "data"),
    prevent_initial_call=True,
)
def hide_or_show_upstream_or_downstream_nodes(button_clicks, selected_node_id, all_elements, current_elements, hidden_state, leaves_hidden):
    """
    Hide or show upstream or downstream nodes from the selected node in the visualiser.
    """
    if not selected_node_id or not all_elements or not current_elements:
        return no_update, no_update, no_update
    
    triggered = callback_context.triggered[0] if callback_context.triggered else None
    if not triggered:
        return no_update, no_update, no_update
    
    # Parse the triggered prop_id to get which button was clicked
    prop_id = triggered["prop_id"]
    if "btn-hide-nodes" not in prop_id:
        return no_update, no_update, no_update
    
    # Extract direction and node_id from the prop_id
    import json
    try:
        json_part = prop_id.split(".n_clicks")[0]
        button_info = json.loads(json_part)
        direction = button_info.get("direction")
        node_id = button_info.get("node_id")
    except:
        return no_update, no_update, no_update
    
    # Verify this is for the selected node
    if node_id != selected_node_id:
        return no_update, no_update, no_update
    
    # Check if there was an actual click
    if not button_clicks or not any(x and x > 0 for x in button_clicks):
        return no_update, no_update, no_update
    
    # Initialize hidden_state if needed
    if not hidden_state:
        hidden_state = {"upstream": False, "downstream": False, "node_id": None}
    
    # Check if nodes are currently hidden for this direction
    is_currently_hidden = (
        hidden_state.get("node_id") == selected_node_id and
        hidden_state.get(direction, False)
    )
    
    if is_currently_hidden:
        # Show nodes - restore from all_elements
        # Get nodes that were hidden
        if direction == "upstream":
            nodes_to_restore = get_all_upstream_nodes(selected_node_id, all_elements)
        elif direction == "downstream":
            nodes_to_restore = get_all_downstream_nodes(selected_node_id, all_elements)
        else:
            return no_update, no_update, no_update
        
        # Restore all elements (show everything)
        # But check if the other direction is still hidden
        other_direction = "downstream" if direction == "upstream" else "upstream"
        other_hidden = (
            hidden_state.get("node_id") == selected_node_id and
            hidden_state.get(other_direction, False)
        )
        
        if other_hidden:
            # Other direction is still hidden, so filter those out
            if other_direction == "upstream":
                nodes_to_keep_hidden = get_all_upstream_nodes(selected_node_id, all_elements)
            else:
                nodes_to_keep_hidden = get_all_downstream_nodes(selected_node_id, all_elements)
            
            filtered_elements = []
            for el in all_elements:
                if "source" not in el.get("data", {}):  # It's a node
                    node_id_el = el["data"].get("id")
                    if node_id_el == selected_node_id or node_id_el not in nodes_to_keep_hidden:
                        filtered_elements.append(el)
                else:  # It's an edge
                    source = el["data"].get("source")
                    target = el["data"].get("target")
                    if source not in nodes_to_keep_hidden and target not in nodes_to_keep_hidden:
                        filtered_elements.append(el)
            # Respect leaves-hidden state
            if leaves_hidden:
                filtered_elements, _ = filter_out_leaves(filtered_elements, keep_root=True)
        else:
            # No other direction hidden, show everything (but respect leaves-hidden state)
            filtered_elements = all_elements
            if leaves_hidden:
                filtered_elements, _ = filter_out_leaves(all_elements, keep_root=True)
        
        # Update hidden state
        new_hidden_state = hidden_state.copy()
        new_hidden_state[direction] = False
        if not new_hidden_state.get("upstream") and not new_hidden_state.get("downstream"):
            new_hidden_state["node_id"] = None
        
    else:
        # Hide nodes
        if direction == "upstream":
            nodes_to_hide = get_all_upstream_nodes(selected_node_id, all_elements)
        elif direction == "downstream":
            nodes_to_hide = get_all_downstream_nodes(selected_node_id, all_elements)
        else:
            return no_update, no_update, no_update
        
        if not nodes_to_hide:
            return no_update, no_update, no_update
        
        # Check if the other direction is already hidden
        other_direction = "downstream" if direction == "upstream" else "upstream"
        other_hidden = (
            hidden_state.get("node_id") == selected_node_id and
            hidden_state.get(other_direction, False)
        )
        
        if other_hidden:
            # Combine with already hidden nodes
            if other_direction == "upstream":
                other_hidden_nodes = get_all_upstream_nodes(selected_node_id, all_elements)
            else:
                other_hidden_nodes = get_all_downstream_nodes(selected_node_id, all_elements)
            nodes_to_hide = nodes_to_hide.union(other_hidden_nodes)
        
        # Filter current elements to exclude nodes to hide (but keep the selected node)
        filtered_elements = []
        for el in current_elements:
            if "source" not in el.get("data", {}):  # It's a node
                node_id_el = el["data"].get("id")
                if node_id_el == selected_node_id or node_id_el not in nodes_to_hide:
                    filtered_elements.append(el)
            else:  # It's an edge
                source = el["data"].get("source")
                target = el["data"].get("target")
                if source not in nodes_to_hide and target not in nodes_to_hide:
                    filtered_elements.append(el)
        
        # Update hidden state
        new_hidden_state = hidden_state.copy()
        new_hidden_state[direction] = True
        new_hidden_state["node_id"] = selected_node_id
    
    # Update node info panel to reflect new button states
    # Find the selected node data
    selected_node_data = None
    for el in all_elements:
        if "source" not in el.get("data", {}) and el["data"].get("id") == selected_node_id:
            selected_node_data = el["data"]
            break
    
    updated_node_info = show_node_info(selected_node_data, all_elements, new_hidden_state)
    
    return filtered_elements, new_hidden_state, updated_node_info


@app.callback(
    Output("visualiser-container", "className"),
    Output("btn-fullscreen", "title"),
    Input("btn-fullscreen", "n_clicks"),
    State("fullscreen-mode", "data"),
    prevent_initial_call=True,
)
def toggle_fullscreen(n_clicks, is_fullscreen):
    """
    Toggle fullscreen mode for the visualiser.
    """
    if not n_clicks:
        return no_update, no_update
    
    new_fullscreen = not is_fullscreen
    
    if new_fullscreen:
        return "fullscreen", "Exit fullscreen (ESC)"
    else:
        return "", "Toggle fullscreen"




@app.callback(
    Output("fullscreen-mode", "data"),
    Input("visualiser-container", "className"),
    prevent_initial_call=True,
)
def update_fullscreen_state(className):
    """
    Update fullscreen state store based on className.
    """
    return className == "fullscreen"


# Clientside callback for ESC key to exit fullscreen
app.clientside_callback(
    """
    function(className) {
        // Store handler reference globally so we can remove it later
        if (className === 'fullscreen') {
            // Remove any existing handler first (prevents accumulation)
            if (window._fullscreenEscapeHandler) {
                document.removeEventListener('keydown', window._fullscreenEscapeHandler);
            }
            
            var handleEscape = function(e) {
                if (e.key === 'Escape') {
                    var btn = document.getElementById('btn-fullscreen');
                    if (btn) {
                        btn.click();
                    }
                    document.removeEventListener('keydown', handleEscape);
                    window._fullscreenEscapeHandler = null;
                }
            };
            window._fullscreenEscapeHandler = handleEscape;
            document.addEventListener('keydown', handleEscape);
        } else {
            // Remove listener when exiting fullscreen via button
            if (window._fullscreenEscapeHandler) {
                document.removeEventListener('keydown', window._fullscreenEscapeHandler);
                window._fullscreenEscapeHandler = null;
            }
        }
        return window.dash_clientside.no_update;
    }
    """,
    Output("fullscreen-mode", "data", allow_duplicate=True),
    Input("visualiser-container", "className"),
    prevent_initial_call=True,
)


# --- Main ---
if __name__ == "__main__":
    app.run(debug=True)
