import streamlit as st
import os

st.set_page_config(page_title="CAD File Profiler", layout="centered")

# Canonical extension per format (for aliases like .stp -> .step)
EXTENSION_TO_FORMAT = {
    ".stp": ".step",
    ".igs": ".iges",
    ".obj": ".obj",
}

FORMAT_KB = {
    ".step": {
        "label": "Neutral Solid (STEP)",
        "geometry_type": "Solid",
        "typical_sources": [
            "Any major CAD system",
            "Supplier deliverables",
            "Design handoff",
        ],
        "survives": ["Exact B-rep", "Assemblies", "Names/attributes"],
        "lost": ["Parametric history", "Sketch constraints"],
        "dfm_quote_confidence": "High",
        "automation_friendliness": "High",
        "notes": "ISO 10303. Preferred for quoting and tooling.",
    },
    ".iges": {
        "label": "Neutral Surface/Solid (IGES)",
        "geometry_type": "Surface / Solid",
        "typical_sources": ["Legacy systems", "Aerospace supply chain", "2D/3D mix"],
        "survives": ["Surfaces and solids", "Basic topology"],
        "lost": ["Tight tolerances", "Parametric history", "Some assembly context"],
        "dfm_quote_confidence": "Medium",
        "automation_friendliness": "Medium",
        "notes": "Older standard; STEP preferred when possible.",
    },
    ".stl": {
        "label": "Mesh (STL)",
        "geometry_type": "Mesh",
        "typical_sources": ["3D printing", "Scan data", "Quick exports"],
        "survives": ["Triangulated surface", "Envelope shape"],
        "lost": ["Exact geometry", "Edges/faces", "Units sometimes ambiguous"],
        "dfm_quote_confidence": "Low–Medium",
        "automation_friendliness": "Medium",
        "notes": "Check units (mm vs in). Not suitable for precision machining quote alone.",
    },
    ".obj": {
        "label": "Mesh (OBJ)",
        "geometry_type": "Mesh",
        "typical_sources": ["Visualization", "Games", "Scan pipelines"],
        "survives": ["Triangulated mesh", "UVs / materials"],
        "lost": ["Precise CAD geometry", "Units"],
        "dfm_quote_confidence": "Low",
        "automation_friendliness": "Medium",
        "notes": "Often used for appearance, not engineering.",
    },
    ".sldprt": {
        "label": "SolidWorks Part",
        "geometry_type": "Solid (native)",
        "typical_sources": ["SolidWorks", "Supplier parts"],
        "survives": ["Full feature tree", "Parameters", "Materials"],
        "lost": ["Nothing when opened in SolidWorks"],
        "dfm_quote_confidence": "High",
        "automation_friendliness": "High (with SolidWorks API)",
        "notes": "Requires SolidWorks to open. Export STEP for neutral workflow.",
    },
    ".sldasm": {
        "label": "SolidWorks Assembly",
        "geometry_type": "Assembly (native)",
        "typical_sources": ["SolidWorks assemblies"],
        "survives": ["Structure", "mates", "parts"],
        "lost": ["Nothing when opened in SolidWorks"],
        "dfm_quote_confidence": "High",
        "automation_friendliness": "High (with SolidWorks API)",
        "notes": "Assembly context preserved. Export STEP for neutral.",
    },
    ".prt": {
        "label": "NX / Creo Native",
        "geometry_type": "Solid (native)",
        "typical_sources": ["Siemens NX", "PTC Creo"],
        "survives": ["Full model in native system"],
        "lost": ["Cross-platform; need same CAD to open"],
        "dfm_quote_confidence": "High",
        "automation_friendliness": "High (with native API)",
        "notes": "Extension shared by NX and Creo; context-dependent.",
    },
    ".catpart": {
        "label": "CATIA Part",
        "geometry_type": "Solid (native)",
        "typical_sources": ["CATIA V5/V6", "Aerospace / automotive"],
        "survives": ["Full part in CATIA"],
        "lost": ["Cross-platform"],
        "dfm_quote_confidence": "High",
        "automation_friendliness": "Medium",
        "notes": "Native CATIA format. STEP for exchange.",
    },
    ".dwg": {
        "label": "AutoCAD Native (2D/3D)",
        "geometry_type": "2D / 3D",
        "typical_sources": ["AutoCAD", "Drafting", "Legacy drawings"],
        "survives": ["Drafting entities", "Blocks", "Layouts"],
        "lost": ["Parametric 3D in some workflows"],
        "dfm_quote_confidence": "Medium (drawing-based)",
        "automation_friendliness": "High",
        "notes": "Often used for 2D drawings; 3D possible.",
    },
    ".dxf": {
        "label": "Drawing Exchange Format (2D)",
        "geometry_type": "2D",
        "typical_sources": ["AutoCAD", "CNC nesting", "Laser cutting"],
        "survives": ["Lines, arcs", "Blocks", "Layers"],
        "lost": ["Proprietary objects", "Full fidelity"],
        "dfm_quote_confidence": "Medium",
        "automation_friendliness": "High",
        "notes": "Good for 2D CAM and sheet cutting.",
    },
}


def get_format_info(extension: str) -> dict | None:
    """Resolve extension (including aliases) to FORMAT_KB entry."""
    ext = extension.lower()
    canonical = EXTENSION_TO_FORMAT.get(ext, ext)
    return FORMAT_KB.get(canonical)


def render_summary_card(filename: str, extension: str, info: dict) -> None:
    """Render a summary card with header, two columns, and bullet lists."""
    st.subheader(info["label"])
    st.caption(f"{filename}  ·  {extension}")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Geometry type**")
        st.write(info["geometry_type"])

        st.markdown("**Typical sources**")
        for item in info["typical_sources"]:
            st.markdown(f"- {item}")

        st.markdown("**Survives export**")
        for item in info["survives"]:
            st.markdown(f"- {item}")

        st.markdown("**Lost / at risk**")
        for item in info["lost"]:
            st.markdown(f"- {item}")

    with col2:
        st.markdown("**DFM / quote confidence**")
        st.write(info["dfm_quote_confidence"])

        st.markdown("**Automation friendliness**")
        st.write(info["automation_friendliness"])

        st.markdown("**Notes**")
        for line in info["notes"].split(". "):
            line = line.strip()
            if line:
                st.markdown(f"- {line}")


st.title("CAD File Profiler")
st.write("Upload a CAD file to analyze its format and metadata.")

uploaded_file = st.file_uploader("Upload CAD file")

if uploaded_file:
    filename = uploaded_file.name
    extension = os.path.splitext(filename)[1].lower()
    info = get_format_info(extension)

    if info:
        render_summary_card(filename, extension, info)
    else:
        st.subheader("Unknown format")
        st.caption(f"{filename}  ·  {extension}")
        st.info("No format profile in knowledge base for this extension.")
