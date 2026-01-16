# FlowNodes

An interactive web application for visualising and editing FlowJo gating tree networks. FlowNodes provides an intuitive interface to explore, customise, and export cytometry gating hierarchies with advanced visualisation and styling options.

## Features

### Network Visualisation
- **Interactive Graph**: Explore FlowJo gating trees as interactive network diagrams
- **Multiple Layouts**: Choose between Breadthfirst (hierarchical) or Cose (force-directed) layouts
- **Customisable Layout Parameters**: Fine-tune spacing, padding, node repulsion, and edge lengths with intuitive sliders
- **Zoom & Pan**: Navigate large networks with zoom (0.2x to 2.5x) and pan controls
- **Show/Hide Leaf Nodes**: Toggle visibility of terminal nodes to focus on the hierarchy structure

### Node Editing
- **Node Selection**: Click any node to view and edit its properties
- **Edit Node Name**: Rename nodes directly in the interface
- **Colour Customisation**: 
  - Choose from a curated colour palette
  - Enter custom hex colour codes
  - Visual colour preview before applying
- **Shape Selection**: Choose from 8 node shapes (ellipse, rectangle, triangle, diamond, pentagon, hexagon, star, round-rectangle)
- **Bulk Operations**: Apply colour or shape to all downstream nodes with a single click

### Data Import & Export
- **CSV Export**: Export network data with columns: `node_name`, `shape`, `colour`, `parameter`
- **CSV Import**: Import CSV files to automatically apply viridis colour schemes based on numeric parameter values
- **Automatic Processing**: CSV files are processed immediately upon upload (drag-and-drop or file picker)
- **High-Quality PNG Export**: Export the entire network at 10x resolution (up to 8000x8000px) for publication-quality figures

### Colour Mapping
- **Viridis Colormap**: Automatically map numeric parameter values to the scientific viridis colour scheme
- **Normalisation**: Parameter values are automatically normalised for optimal colour distribution
- **Missing Node Handling**: Clear warnings when imported nodes don't match existing network nodes

## Installation

### Prerequisites
- Python 3.8 or higher
- pip package manager

### Setup

1. Clone or download this repository

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Prepare your FlowJo workspace file:
   - Download tutorial data from [FlowJo Learn](https://www.flowjo.com/learn)
   - Place your `.wsp` file in the `inputs/` directory
   - The application loads `inputs/FlowJo_tutorial.wsp` by default

4. Run the application:
```bash
python src/app.py
```

5. Open your browser to `http://127.0.0.1:8050`

## Usage Guide

### Getting Started

1. **Load a Network**: The application automatically loads the FlowJo workspace file from `inputs/FlowJo_tutorial.wsp` on startup

2. **Explore the Network**: 
   - The network visualisation appears in the top-left panel
   - By default, leaf nodes are hidden to show the hierarchy structure
   - Use mouse wheel to zoom, click and drag to pan

3. **Select a Node**: Click any node to view its details in the top-right panel

### Editing Nodes

1. **Select a Node**: Click on any node in the network graph

2. **Edit Properties**:
   - **Name**: Type directly in the name field
   - **Colour**: Click the colour button to open the colour picker modal
     - Choose from the colour palette
     - Or enter a hex code (e.g., `#FF5733`)
     - Click "Apply" to save
   - **Shape**: Select from the dropdown menu

3. **Apply to Downstream Nodes**:
   - After setting a node's colour or shape, click:
     - **"Apply Colour"** to copy the colour to all descendant nodes
     - **"Apply Shape"** to copy the shape to all descendant nodes

### Layout Controls

**Switch Layouts**:
- Click "Breadthfirst" for hierarchical tree layout
- Click "Cose" for force-directed layout

**Adjust Parameters** (sliders appear based on selected layout):

**Breadthfirst Layout**:
- **Spacing Factor**: Controls horizontal spacing between levels (0.5 - 3.0)
- **Padding**: Margin around the graph (0 - 100)

**Cose Layout**:
- **Node Repulsion**: Force pushing nodes apart (1k - 50k)
- **Ideal Edge Length**: Preferred edge length (1 - 500)
- **Padding**: Margin around the graph (0 - 100)

### View Controls

- **Show all nodes**: Displays the complete network including leaf nodes
- **Hide leaf nodes**: Hides terminal nodes to focus on the hierarchy

### Export Options

**Export PNG**:
- Click "Export PNG" to download a high-resolution image
- Exports at 10x scale (up to 8000x8000 pixels)
- Includes the entire network with current styling
- Perfect for publications and presentations

**Export CSV**:
- Click "Export CSV" to download network data
- Contains: `node_name`, `shape`, `colour`, `parameter` columns
- The `parameter` column is empty for you to fill with numeric values
- Use this exported file as a template for importing colour mappings

**Import CSV**:
1. Prepare a CSV file with columns: `node_name`, `shape`, `colour`, `parameter`
2. Fill the `parameter` column with numeric values you want to visualise
3. Drag and drop the CSV file into the upload area, or click to select
4. The application automatically:
   - Validates the file format
   - Applies viridis colour mapping based on parameter values
   - Updates the network visualisation
   - Shows success message or warnings for missing nodes

### CSV Import Format

Your CSV file must have these exact columns:

| Column | Description | Example |
|--------|-------------|---------|
| `node_name` | Node label or ID | `root_Lymphocytes` |
| `shape` | Node shape | `ellipse` |
| `colour` | Current colour (can be empty) | `#A0C4FF` |
| `parameter` | Numeric value for colour mapping | `42.5` |

**Important Notes**:
- Column names must match exactly (case-sensitive)
- Only rows with valid numeric `parameter` values will be processed
- Node names must match existing node labels or IDs in the network
- Missing nodes will be reported in a warning message

## File Structure

```
FlowNodes/
├── src/
│   ├── app.py              # Main Dash application
│   ├── wsp_to_cyto.py     # FlowJo workspace parser
│   └── styles_cyto.py      # Cytoscape styling definitions
├── inputs/                 # Place your .wsp files here
│   └── FlowJo_tutorial.wsp
├── requirements.txt        # Python dependencies
└── README.md              # This file
```

## Tips & Best Practices

1. **Large Networks**: For networks with many nodes, start with leaf nodes hidden for better performance
2. **Colour Mapping**: Use the CSV export/import workflow to apply colour schemes based on experimental data
3. **Layout Tuning**: Adjust layout parameters gradually - small changes can have significant visual impact
4. **PNG Export**: High-resolution exports may take a few seconds for large networks - be patient
5. **Node Matching**: When importing CSV, ensure node names exactly match the network (check spelling and case)

## Troubleshooting

**Application won't start**:
- Check that all dependencies are installed: `pip install -r requirements.txt`
- Verify Python version is 3.8 or higher: `python --version`
- Ensure the FlowJo workspace file exists in `inputs/FlowJo_tutorial.wsp`

**CSV import fails**:
- Verify column names match exactly: `node_name`, `shape`, `colour`, `parameter`
- Check that parameter column contains numeric values (not text)
- Ensure node names in CSV match existing network nodes

**Poor PNG quality**:
- The export uses 10x scale by default for high quality
- Very large networks may hit browser memory limits (8000x8000px max)
- Try exporting a smaller subset if issues occur

**Network not displaying**:
- Check browser console for errors
- Verify the `.wsp` file is valid and not corrupted
- Try refreshing the page

## Technical Details

- **Framework**: Dash (Plotly)
- **Visualization**: Dash Cytoscape (Cytoscape.js)
- **Data Processing**: FlowKit, pandas
- **Colour Mapping**: Matplotlib viridis colormap
- **Export Resolution**: 10x scale, max 8000x8000 pixels

## License

See LICENSE file for details.

## Credits

Built for visualizing FlowJo gating trees with interactive network exploration capabilities.
