# styles_cyto.py
def cyto_stylesheet():
    return [
        # Base nodes
        {"selector": "node",
         "style": {
             "label": "data(label)",
             "text-wrap": "wrap",
             "text-max-width": 120,
             "font-size": 12,
             "background-color": "#A0C4FF",
             "border-width": 1,
             "border-color": "#333",
             "width": "mapData(node_size, 0, 10, 20, 60)",
             "height": "mapData(node_size, 0, 10, 20, 60)",
         }},
        # If node_colour is set in data, prefer it
        {"selector": "node[ node_colour ]",
         "style": { "background-color": "data(node_colour)" }},

        # Panel-specific class example
        {"selector": ".panel-Tv2",
         "style": {"background-opacity": 0.9, "border-color": "#1f4f7f"}},

        # Edges
        {"selector": "edge",
         "style": {"curve-style": "bezier", "target-arrow-shape": "vee", "line-color": "#bbb",
                   "target-arrow-color": "#bbb", "width": 1}},
        # Selected
        {"selector": ":selected",
         "style": {"border-width": 3, "border-color": "#FFB703", "line-color": "#FFB703",
                   "target-arrow-color": "#FFB703"}}
    ]