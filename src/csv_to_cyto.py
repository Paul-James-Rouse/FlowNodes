# csv_to_cyto.py
import re

def csv_to_cyto(df):
    """
    Convert a gating metadata DataFrame (from Tv2_gates.csv) into
    Cytoscape-compatible elements: nodes + edges.

    Expects columns: ['id', 'parent_id', 'label', ...]
    """
    # ---- Build nodes ----
    nodes = []
    for _, r in df.iterrows():
        classes = []
        if isinstance(r.get("panel"), str):
            # e.g. add CSS class per panel for styling
            safe_panel = re.sub(r"[^A-Za-z0-9_\-]", "_", r["panel"])
            classes.append(f"panel-{safe_panel}")

        node = {
            "data": {
                "id": r["id"],
                "label": r["label"],
                "panel": r.get("panel"),
                "primary_markers": r.get("primary_markers"),
                "biological_role": r.get("Biological role"),
                "x_marker_desc": r.get("X marker description"),
                "y_marker_desc": r.get("Y marker description"),
                "node_size": r.get("node_size"),
                "node_colour": r.get("node_colour"),
            },
            "classes": " ".join(classes) if classes else ""
        }

        nodes.append(node)

    # ---- Build edges ----
    edges = []
    for _, r in df.iterrows():
        if r["parent_id"]:
            edge_id = f"{r['parent_id']}->{r['id']}"
            edges.append({
                "data": {"id": edge_id, "source": r["parent_id"], "target": r["id"]}
            })

    return nodes + edges