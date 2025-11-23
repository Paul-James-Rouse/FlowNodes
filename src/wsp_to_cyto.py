# wsp_to_cyto.py
import flowkit as fk
from pathlib import PurePath

def extract_gate_paths_from_wsp(wsp_path):

    # Use Flowkit to parse wsp
    wsp = fk.parse_wsp(wsp_path)

    # valid keys FlowJo may use for gates
    possible_gate_keys = ["group_gates", "gates"]

    # Initiate a dict that pairs each gating tree with each group name
    group_gate_dict = {}

    for group_name, group_data in wsp["groups"].items():

        # initialize each group with root
        gt = [PurePath("root")]

        # find the key that exists in this group
        gate_key = next(
            (k for k in possible_gate_keys if k in group_data),
            None
        )

        if gate_key is None:
            raise KeyError(
                f"No gate key found in group '{group_name}'. "
                f"Looked for: {possible_gate_keys}"
            )

        # iterate over tuple paths
        for gate_path_tuple in group_data[gate_key].keys():
            gate = ''

            # parse tuple elements into string path
            for val in gate_path_tuple:
                gate += str(val).strip() + ' / '

            gt.append(PurePath(gate))

        # store this group's paths
        group_gate_dict[group_name] = gt

    return group_gate_dict

def wsp_to_cyto(wsp_path):
    """
    Convert FlowJo wsp gating tree into Cytoscape nodes + edges.
    """
    groups = extract_gate_paths_from_wsp(wsp_path)

    cy_nodes = []
    cy_edges = []

    for group_name, paths in groups.items():

        # Deduplicate nodes
        seen_nodes = set()

        for path in paths:
            parts = [p.strip() for p in str(path).split("/") if p.strip()]

            # build unique node ID
            node_id = "_".join(parts)  # e.g. root_Lymphocytes_CD3+
            label = parts[-1]          # show only the last name

            if node_id not in seen_nodes:
                cy_nodes.append({
                    "data": {
                        "id": node_id,
                        "label": label
                    }
                })
                seen_nodes.add(node_id)

            # build edges if there's a parent
            if len(parts) > 1:
                parent_id = "_".join(parts[:-1])
                cy_edges.append({
                    "data": {
                        "id": f"{parent_id}__to__{node_id}",
                        "source": parent_id,
                        "target": node_id
                    }
                })

    return {"nodes": cy_nodes, "edges": cy_edges}