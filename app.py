import streamlit as st
import os

st.set_page_config(page_title="CAD File Profiler", layout="centered")

# Canonical extension per format (true aliases only, e.g. .stp -> .step)
EXTENSION_TO_FORMAT = {
    ".stp": ".step",
    ".igs": ".iges",
}

FORMAT_KB = {
    ".step": {
        "label": "Neutral Solid (STEP)",
        "geometry_class": "B-Rep",
        "typical_authoring_tools": ["Any major CAD system"],
        "common_use_cases": [
            "Supplier deliverables",
            "Design handoff",
            "Quoting and tooling",
        ],
        "survives": ["Exact B-rep", "Assemblies", "Names/attributes"],
        "lost": ["Parametric history", "Sketch constraints"],
        "dfm_quote_confidence": "High",
        "quote_risk_baseline": "Low",
        "automation_friendliness": "High",
        "notes": ["ISO 10303.", "Preferred for quoting and tooling."],
    },
    ".iges": {
        "label": "Neutral Surface/Solid (IGES)",
        "geometry_class": "Surface",
        "typical_authoring_tools": [
            "Legacy CAD systems",
            "Aerospace supply chain tools",
        ],
        "common_use_cases": ["2D/3D mix", "Legacy exchange", "Surface-heavy data"],
        "survives": ["Surfaces and solids", "Basic topology"],
        "lost": ["Tight tolerances", "Parametric history", "Some assembly context"],
        "dfm_quote_confidence": "Medium",
        "quote_risk_baseline": "Medium",
        "automation_friendliness": "Medium",
        "notes": ["Older standard; STEP preferred when possible."],
    },
    ".stl": {
        "label": "Mesh (STL)",
        "geometry_class": "Mesh",
        "typical_authoring_tools": [
            "Any CAD with STL export",
            "Scan/reverse-engineering tools",
        ],
        "common_use_cases": ["3D printing", "Scan data", "Quick exports"],
        "survives": ["Triangulated surface", "Envelope shape"],
        "lost": ["Exact geometry", "Edges/faces", "Units sometimes ambiguous"],
        "dfm_quote_confidence": "Medium",
        "quote_risk_baseline": "Medium",
        "automation_friendliness": "Medium",
        "notes": [
            "Check units (mm vs in).",
            "Not suitable for precision machining quote alone.",
        ],
    },
    ".obj": {
        "label": "Mesh (OBJ)",
        "geometry_class": "Mesh",
        "typical_authoring_tools": [
            "Blender",
            "Maya",
            "Scan pipelines",
            "Game engines",
        ],
        "common_use_cases": ["Visualization", "Games", "Appearance models"],
        "survives": ["Triangulated mesh", "UVs / materials"],
        "lost": ["Precise CAD geometry", "Units"],
        "dfm_quote_confidence": "Low",
        "quote_risk_baseline": "High",
        "automation_friendliness": "Medium",
        "notes": ["Often used for appearance, not engineering."],
    },
    ".sldprt": {
        "label": "SolidWorks Part",
        "geometry_class": "Parametric",
        "typical_authoring_tools": ["SolidWorks"],
        "common_use_cases": ["Supplier parts", "Design in-house", "Detailing"],
        "survives": ["Full feature tree", "Parameters", "Materials"],
        "lost": ["Nothing when opened in SolidWorks"],
        "dfm_quote_confidence": "High",
        "quote_risk_baseline": "Low",
        "automation_friendliness": "High",
        "notes": [
            "Requires SolidWorks to open.",
            "Export STEP for neutral workflow.",
        ],
    },
    ".sldasm": {
        "label": "SolidWorks Assembly",
        "geometry_class": "Parametric",
        "typical_authoring_tools": ["SolidWorks"],
        "common_use_cases": ["Assembly design", "BOM", "Large assemblies"],
        "survives": ["Structure", "mates", "parts"],
        "lost": ["Nothing when opened in SolidWorks"],
        "dfm_quote_confidence": "High",
        "quote_risk_baseline": "Low",
        "automation_friendliness": "High",
        "notes": ["Assembly context preserved.", "Export STEP for neutral."],
    },
    ".prt": {
        "label": "NX / Creo Native",
        "geometry_class": "Parametric",
        "typical_authoring_tools": ["Siemens NX", "PTC Creo"],
        "common_use_cases": [
            "Manufacturing CAD",
            "High-end design",
            "Enterprise parts",
        ],
        "survives": ["Full model in native system"],
        "lost": ["Cross-platform; need same CAD to open"],
        "dfm_quote_confidence": "Medium",
        "quote_risk_baseline": "Medium",
        "automation_friendliness": "High",
        "notes": [
            "Extension shared by NX and Creo; requires the correct native CAD to open reliably.",
            "Export to STEP when the recipient's CAD system is unknown.",
        ],
    },
    ".catpart": {
        "label": "CATIA Part",
        "geometry_class": "Parametric",
        "typical_authoring_tools": ["CATIA V5", "CATIA V6 (3DEXPERIENCE)"],
        "common_use_cases": ["Aerospace", "Automotive", "Large assembly design"],
        "survives": ["Full part in CATIA"],
        "lost": ["Cross-platform"],
        "dfm_quote_confidence": "High",
        "quote_risk_baseline": "Low",
        "automation_friendliness": "Medium",
        "notes": ["Native CATIA format.", "STEP for exchange."],
    },
    ".dwg": {
        "label": "AutoCAD Native (2D/3D)",
        "geometry_class": "2D Drawing",
        "typical_authoring_tools": ["AutoCAD", "DraftSight", "BricsCAD"],
        "common_use_cases": ["Drafting", "Legacy drawings", "2D documentation"],
        "survives": ["Drafting entities", "Blocks", "Layouts"],
        "lost": ["Parametric 3D in some workflows"],
        "dfm_quote_confidence": "Medium",
        "quote_risk_baseline": "Medium",
        "automation_friendliness": "High",
        "notes": ["Often used for 2D drawings; 3D possible."],
    },
    ".dxf": {
        "label": "Drawing Exchange Format (2D)",
        "geometry_class": "2D Drawing",
        "typical_authoring_tools": [
            "AutoCAD",
            "CNC nesting software",
            "Laser/plasma CAM",
        ],
        "common_use_cases": [
            "CNC nesting",
            "Laser cutting",
            "2D CAM",
            "Drawing exchange",
        ],
        "survives": ["Lines, arcs", "Blocks", "Layers"],
        "lost": ["Proprietary objects", "Full fidelity"],
        "dfm_quote_confidence": "Medium",
        "quote_risk_baseline": "Medium",
        "automation_friendliness": "High",
        "notes": ["Good for 2D CAM and sheet cutting."],
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
        st.markdown("**Geometry class**")
        st.write(info["geometry_class"])

        st.markdown("**Typical authoring tools**")
        for item in info["typical_authoring_tools"]:
            st.markdown(f"- {item}")

        st.markdown("**Common use cases**")
        for item in info["common_use_cases"]:
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

        st.markdown("**Quote risk baseline**")
        st.write(info["quote_risk_baseline"])

        st.markdown("**Automation friendliness**")
        st.write(info["automation_friendliness"])

        st.markdown("**Notes**")
        for item in info["notes"]:
            st.markdown(f"- {item}")


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
