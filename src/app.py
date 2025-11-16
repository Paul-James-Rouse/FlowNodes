# app.py
from pathlib import Path

from dash import Dash, html, dcc, Input, Output, State, callback_context, no_update

import dash_cytoscape as cyto
from src.data_loader import load_gates_csv
from src.csv_to_cyto import csv_to_cyto
from src.styles_cyto import cyto_stylesheet


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


def show_metadata(data):
    if not data:
        return "Click a node to see details."
    rows = []
    for key, label in [
        ("label", "Population"),
        ("panel", "Panel"),
        ("primary_markers", "Markers"),
        ("biological_role", "Biological role"),
        ("x_marker_desc", "X marker desc"),
        ("y_marker_desc", "Y marker desc"),
        ("id", "Full path (unique id)"),
    ]:
        val = data.get(key)
        if val:
            rows.append(html.Div([html.Strong(f"{label}: "), html.Span(str(val))]))
    return html.Div(rows)


def get_triggered_id():
    return (
        callback_context.triggered[0]["prop_id"].split(".")[0]
        if callback_context.triggered else None
    )


def make_layout(name: str):
    if name == "breadthfirst":
        return {
            "name": "breadthfirst",
            "directed": True,
            "spacingFactor": 1.15,
            "padding": 30,
            "animate": False,
        }
    # default: cose
    return {
        "name": "cose",
        "directed": True,
        "padding": 50,
        "animate": False,
        "randomize": False,  # ← critical for non-random initial positions
        "nodeOverlap": 1,
        #"idealEdgeLength": 200,  # ← increase this (default ≈ 100)
        "nodeRepulsion": 20_000,  # pushes nodes apart (default ≈ 4000)
    }


# --- App ---
app = Dash(__name__)

# --- Data ---
CSV_PATH = Path("/Users/imu2/Documents/PycharmProjects/Gating_Tree_Depiction/outputs/Tv2_gates.csv")
df = load_gates_csv(CSV_PATH)
elements_all = csv_to_cyto(df)

elements_filtered, initial_leaves = filter_out_leaves(elements_all, keep_root=True)
print(f"⚡ Loaded with {len(elements_filtered)} nodes (removed {len(initial_leaves)} leaves)")

elements = elements_filtered  # start with leaves hidden

# --- Client-side stores & controls ---
stores = [
    dcc.Store(id="all-elements", data=elements_all),
    dcc.Store(id="leaves-hidden", data=True),  # start with leaves already hidden
]

controls = html.Div(
    [
        html.Button("Show leaf nodes", id="btn-toggle-leaves", n_clicks=0, style={"marginBottom": "0.5rem"}),
        html.Div(id="leaf-status", style={"fontSize": "0.9rem", "opacity": 0.75}),
        html.Hr(),
        html.Button("Export (Current View)", id="btn-export-png", n_clicks=0),
        html.Hr(),
        html.Button("Switch to breadthfirst", id="btn-toggle-layout", n_clicks=0),
    ],
    style={"display": "flex", "flexDirection": "column", "gap": "0.25rem"},
)

# --- Layout ---
app.layout = html.Div(
    [
        *stores,
        html.Div(
            [
                controls,
                cyto.Cytoscape(
                    id="cyto-graph",
                    elements=elements,
                    layout=make_layout("breadthfirst"),  # ← use tuned layout here
                    stylesheet=cyto_stylesheet(),
                    style={"height": "90vh", "width": "100%"},
                    minZoom=0.2,
                    maxZoom=2.5,
                    boxSelectionEnabled=True,
                ),
            ],
            style={"width": "65%", "display": "inline-block", "verticalAlign": "top", "padding": "0 1rem"},
        ),
        html.Div(
            [
                html.H4("Gate metadata"),
                html.Div(id="metadata-panel", children="Click a node to see details."),
            ],
            style={"width": "35%", "display": "inline-block", "verticalAlign": "top"},
        ),
    ]
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
    Output("metadata-panel", "children"),
    Input("cyto-graph", "tapNodeData"),
)
def update_metadata_panel(tap_node_data):
    return show_metadata(tap_node_data)


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


revent_initial_call=False,

@app.callback(
    Output("cyto-graph", "layout"),
    Output("btn-toggle-layout", "children"),
    Input("btn-toggle-layout", "n_clicks"),
    State("cyto-graph", "layout"),
    prevent_initial_call=False,
)

def toggle_layout(n_clicks, current_layout):
    # Initial load: start with breadthfirst layout
    if not n_clicks:
        return make_layout("breadthfirst"), "Switch to cose"

    current_name = (current_layout or {}).get("name", "breadthfirst")
    next_name = "breadthfirst" if current_name != "breadthfirst" else "cose"
    next_label = "Switch to cose" if next_name == "breadthfirst" else "Switch to breadthfirst"
    return make_layout(next_name), next_label


# --- Main ---
if __name__ == "__main__":
    app.run(debug=True)
