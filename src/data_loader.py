# data_loader.py
import pandas as pd
from pathlib import Path

REQUIRED_COLS = ["node", "parent"]


def load_gates_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"CSV is missing required columns: {missing}")

    # Normalise parent paths
    df["parent"] = df["parent"].fillna("root").astype(str).str.replace(r"\s*/\s*", "/", regex=True).str.strip()

    # Create full path (unique node id) and the immediate parent id
    # root’s parent is None
    def full_path(row):
        if row["parent"] == "root":
            return f"root/{row['node']}"
        return f"{row['parent']}/{row['node']}"

    df["id"] = df.apply(full_path, axis=1)
    df["parent_id"] = df["parent"].where(df["parent"].ne("root"), None)
    df.loc[df["parent_id"].notna(), "parent_id"] = df.loc[df["parent_id"].notna(), "parent_id"].astype(str)

    # Display label (what you see on the node)
    df["label"] = df["node"].astype(str)

    # Optional styling if present
    for opt in ["node_size", "node_colour", "panel", "primary_markers",
                "Biological role", "X marker description", "Y marker description"]:
        if opt not in df.columns:
            df[opt] = None

    # Drop duplicates on id (keep first occurrence)
    df = df.drop_duplicates(subset=["id"]).reset_index(drop=True)
    return df
