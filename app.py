from __future__ import annotations

import io
import os

import ezdxf
from ezdxf import bbox as ezdxf_bbox
import numpy as np
import streamlit as st
import trimesh

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
        "notes": [
            "Older standard; STEP preferred when possible.",
            "Solids are possible but surface-only exports are common.",
            "Geometry healing may be required before machining.",
        ],
    },
    ".stl": {
        "label": "Mesh (STL)",
        "geometry_class": "Mesh",
        "typical_authoring_tools": [
            "Any CAD with STL export",
            "Scan/reverse-engineering tools",
        ],
        "common_use_cases": [
            "Scan data",
            "Quick visualization exports",
            "Reverse-engineered geometry",
        ],
        "survives": ["Triangulated surface", "Envelope shape"],
        "lost": ["Exact geometry", "Edges/faces", "Units sometimes ambiguous"],
        "dfm_quote_confidence": "Low",
        "quote_risk_baseline": "High",
        "automation_friendliness": "Medium",
        "notes": [
            "Check units (mm vs in).",
            "Not suitable for CNC machining quote alone.",
            "Lacks exact B-rep geometry; reverse engineering may be needed.",
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
        "quote_risk_baseline": "Medium",
        "automation_friendliness": "High",
        "notes": [
            "Risk depends on access to SolidWorks; file cannot be opened without it.",
            "Export to STEP is recommended for CNC quoting workflows.",
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
        "quote_risk_baseline": "Medium",
        "automation_friendliness": "High",
        "notes": [
            "Risk depends on access to SolidWorks; file cannot be opened without it.",
            "Export to STEP is recommended for CNC quoting workflows.",
        ],
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
        "quote_risk_baseline": "Medium",
        "automation_friendliness": "Medium",
        "notes": [
            "Risk depends on access to CATIA; file cannot be opened without it.",
            "Export to STEP is recommended for CNC quoting workflows.",
        ],
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
            "CAM software",
        ],
        "common_use_cases": [
            "CNC profile layouts",
            "Fixture and jig drawings",
            "2D CAM",
            "Drawing exchange",
        ],
        "survives": ["Lines, arcs", "Blocks", "Layers"],
        "lost": ["Proprietary objects", "Full fidelity"],
        "dfm_quote_confidence": "Medium",
        "quote_risk_baseline": "Medium",
        "automation_friendliness": "High",
        "notes": ["Good for 2D CAM and CNC profile work."],
    },
}


def compute_contextual_risk(risk_score: int) -> str:
    """Derive the contextual risk label from the numeric risk score.

    Delegates to *score_to_band* (defined below) so that risk labels are
    always consistent with the dual-axis scoring model.
    """
    label, _ = score_to_band(risk_score, "risk")
    return label


MESH_EXTENSIONS = {".stl", ".obj"}
COMPONENT_SPLIT_MAX_TRIANGLES = 1_000_000


def parse_mesh_metrics(file_bytes: bytes, file_type: str) -> dict | str:
    """Load a mesh from raw bytes and return basic geometric metrics.

    Returns a dict of metrics on success, or an error-message string on failure.
    """
    try:
        mesh = trimesh.load(
            io.BytesIO(file_bytes),
            file_type=file_type.lstrip("."),
        )
        if isinstance(mesh, trimesh.Scene):
            mesh = mesh.dump(concatenate=True)
        if not isinstance(mesh, trimesh.Trimesh):
            return f"Unexpected mesh type after loading: {type(mesh).__name__}"

        if mesh.bounds is None or len(mesh.vertices) == 0:
            return "Mesh contains no geometry (0 vertices)."

        bb_min = mesh.bounds[0]
        bb_max = mesh.bounds[1]
        dims = bb_max - bb_min

        tri_count = int(len(mesh.faces))

        if tri_count <= COMPONENT_SPLIT_MAX_TRIANGLES:
            body_count: int | None = len(mesh.split(only_watertight=False))
        else:
            body_count = None

        return {
            "triangle_count": tri_count,
            "bbox_dims": np.round(dims, 4).tolist(),
            "bbox_min": np.round(bb_min, 4).tolist(),
            "bbox_max": np.round(bb_max, 4).tolist(),
            "is_watertight": bool(mesh.is_watertight),
            "component_count": body_count,
        }
    except Exception as exc:
        return f"Mesh parsing failed: {exc}"


def render_mesh_metrics(metrics: dict) -> None:
    """Display extracted mesh metrics in a dedicated section."""
    st.markdown("---")
    st.subheader("Extracted metrics")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Triangle count**")
        st.write(f"{metrics['triangle_count']:,}")

        st.markdown("**Bounding box dimensions (X, Y, Z)**")
        dx, dy, dz = metrics["bbox_dims"]
        st.write(f"{dx}  ×  {dy}  ×  {dz}")

    with col2:
        st.markdown("**Watertight**")
        st.write("Yes" if metrics["is_watertight"] else "No")

        st.markdown("**Disconnected components**")
        if metrics["component_count"] is not None:
            st.write(str(metrics["component_count"]))
        else:
            st.write("(skipped for performance)")

        st.markdown("**Bounding box min**")
        st.write(
            f"({metrics['bbox_min'][0]}, {metrics['bbox_min'][1]}, {metrics['bbox_min'][2]})"
        )

        st.markdown("**Bounding box max**")
        st.write(
            f"({metrics['bbox_max'][0]}, {metrics['bbox_max'][1]}, {metrics['bbox_max'][2]})"
        )

    st.caption(
        "Mesh formats may not reliably encode units (mm vs in). "
        "Confirm units before quoting."
    )


DXF_TRACKED_TYPES = [
    "LINE",
    "ARC",
    "CIRCLE",
    "LWPOLYLINE",
    "POLYLINE",
    "SPLINE",
    "TEXT",
    "MTEXT",
]


def parse_dxf_metrics(file_bytes: bytes) -> dict | str:
    """Parse a DXF from in-memory bytes and return entity metrics.

    Returns a dict of metrics on success, or an error-message string on failure.
    """
    try:
        try:
            text = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            text = file_bytes.decode("latin-1")
        doc = ezdxf.read(io.StringIO(text))
        msp = doc.modelspace()

        counts_by_type: dict[str, int] = {}
        layers: set[str] = set()
        total = 0

        for entity in msp:
            total += 1
            dtype = entity.dxftype()
            if dtype in DXF_TRACKED_TYPES:
                counts_by_type[dtype] = counts_by_type.get(dtype, 0) + 1
            layers.add(entity.dxf.layer)

        extents: dict | None = None
        cache = ezdxf_bbox.Cache()
        bounding_box = ezdxf_bbox.extents(msp, cache=cache)
        if bounding_box.has_data:
            ext_min = bounding_box.extmin
            ext_max = bounding_box.extmax
            ext_size = ext_max - ext_min
            extents = {
                "min": [round(ext_min.x, 4), round(ext_min.y, 4), round(ext_min.z, 4)],
                "max": [round(ext_max.x, 4), round(ext_max.y, 4), round(ext_max.z, 4)],
                "size": [
                    round(ext_size.x, 4),
                    round(ext_size.y, 4),
                    round(ext_size.z, 4),
                ],
            }

        return {
            "total_entities": total,
            "counts_by_type": {
                t: counts_by_type[t] for t in DXF_TRACKED_TYPES if t in counts_by_type
            },
            "layer_count": len(layers),
            "extents": extents,
        }
    except Exception as exc:
        return f"DXF parsing failed: {exc}"


def render_dxf_metrics(metrics: dict) -> None:
    """Display extracted DXF entity metrics in a dedicated section."""
    st.markdown("---")
    st.subheader("Extracted metrics")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Total entities**")
        st.write(f"{metrics['total_entities']:,}")

        st.markdown("**Layers referenced**")
        st.write(str(metrics["layer_count"]))

        extents = metrics.get("extents")
        if extents:
            sx, sy, sz = extents["size"]
            has_z = sz != 0.0

            if has_z:
                st.markdown("**Approx extents (X × Y × Z)**")
                st.write(f"{sx}  ×  {sy}  ×  {sz}")
            else:
                st.markdown("**Approx extents (X × Y)**")
                st.write(f"{sx}  ×  {sy}")

            st.markdown("**Extents min**")
            if has_z:
                st.write(
                    f"({extents['min'][0]}, {extents['min'][1]}, {extents['min'][2]})"
                )
            else:
                st.write(f"({extents['min'][0]}, {extents['min'][1]})")

            st.markdown("**Extents max**")
            if has_z:
                st.write(
                    f"({extents['max'][0]}, {extents['max'][1]}, {extents['max'][2]})"
                )
            else:
                st.write(f"({extents['max'][0]}, {extents['max'][1]})")

    with col2:
        st.markdown("**Entity counts by type**")
        counts = metrics["counts_by_type"]
        if counts:
            for dtype, count in counts.items():
                st.markdown(f"- {dtype}: {count:,}")
        else:
            st.write("No tracked entity types found.")

    if counts.get("SPLINE", 0) > 0:
        st.warning(
            "Splines detected — may require conversion to arcs/polylines for CAM."
        )


def get_format_info(extension: str) -> dict | None:
    """Resolve extension (including aliases) to FORMAT_KB entry."""
    ext = extension.lower()
    canonical = EXTENSION_TO_FORMAT.get(ext, ext)
    return FORMAT_KB.get(canonical)


def render_summary_card(
    info: dict,
    *,
    filename: str | None = None,
    extension: str | None = None,
    contextual_risk: str | None = None,
) -> None:
    """Render a summary card with header, two columns, and bullet lists.

    When *filename* / *extension* are provided (Analyze page) the caption
    shows them.  When *contextual_risk* is provided the adjusted-risk row
    is included.
    """
    st.subheader(info["label"])
    if filename and extension:
        st.caption(f"{filename}  ·  {extension}")
    elif extension:
        st.caption(extension)

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

        if contextual_risk is not None:
            st.markdown("**Quote risk (context-adjusted)**")
            st.write(contextual_risk)

        st.markdown("**Automation friendliness**")
        st.write(info["automation_friendliness"])

        st.markdown("**Notes**")
        for item in info["notes"]:
            st.markdown(f"- {item}")


def build_triage_summary(
    info: dict,
    contextual_risk: str,
    mesh_metrics: dict | None = None,
    dxf_metrics: dict | None = None,
) -> str:
    """Return a max-2-sentence triage paragraph for Analyze mode."""
    gc = info["geometry_class"]
    baseline = info["quote_risk_baseline"]

    # -- Sentence 1: risk assessment + any cleanup flags ---------------
    if contextual_risk == baseline:
        risk_part = f"{gc} geometry with {baseline.lower()} quote risk"
    else:
        risk_part = (
            f"{gc} geometry with {baseline.lower()} baseline risk, "
            f"adjusted to {contextual_risk.lower()} for CNC machining intake"
        )

    issues: list[str] = []

    if mesh_metrics is not None:
        if not mesh_metrics.get("is_watertight", True):
            issues.append("mesh is not watertight")
        cc = mesh_metrics.get("component_count")
        if cc is not None and cc > 1:
            issues.append(f"{cc} disconnected components detected")

    if dxf_metrics is not None:
        if dxf_metrics.get("counts_by_type", {}).get("SPLINE", 0) > 0:
            issues.append("splines present that may need conversion for CAM")

    sentence1 = f"{risk_part}."
    if issues:
        sentence1 = f"{risk_part} — {'; '.join(issues)}."

    # -- Sentence 2: next ask ------------------------------------------
    if gc == "Mesh":
        next_ask = (
            "Confirm units (mm vs in) and request a STEP or native CAD file "
            "if available."
        )
    elif gc == "2D Drawing":
        next_ask = (
            "Confirm dimensions, tolerances, and material thickness are "
            "specified in the drawing."
        )
    else:
        next_ask = "Confirm tolerances and surface finish requirements."

    return f"{sentence1} {next_ask}"


# ---------------------------------------------------------------------------
# Dual-axis scoring (0–100)
# ---------------------------------------------------------------------------

# geometry_class → (risk_baseline, confidence_baseline) for CNC machining
SCORE_BASELINES: dict[str, tuple[int, int]] = {
    "B-Rep": (15, 85),
    "Surface": (40, 55),
    "Mesh": (75, 25),
    "Parametric": (20, 80),
    "2D Drawing": (45, 50),
}

RISK_BANDS: list[tuple[int, str, str]] = [
    (20, "Low", "#2ecc71"),
    (40, "Moderate", "#f1c40f"),
    (60, "Elevated", "#e67e22"),
    (80, "High", "#e74c3c"),
    (100, "Severe", "#c0392b"),
]

CONFIDENCE_BANDS: list[tuple[int, str, str]] = [
    (20, "Very low", "#c0392b"),
    (40, "Low", "#e74c3c"),
    (60, "Medium", "#e67e22"),
    (80, "High", "#f1c40f"),
    (100, "Very high", "#2ecc71"),
]


def score_to_band(score: int, kind: str) -> tuple[str, str]:
    """Return (descriptor, hex_color) for a 0–100 score."""
    bands = RISK_BANDS if kind == "risk" else CONFIDENCE_BANDS
    for ceiling, label, color in bands:
        if score <= ceiling:
            return label, color
    return bands[-1][1], bands[-1][2]


def compute_scores(
    info: dict,
    mesh_metrics: dict | None = None,
    dxf_metrics: dict | None = None,
) -> tuple[int, int, list[str]]:
    """Return (risk_score, confidence_score, explanations)."""
    gc = info["geometry_class"]
    risk, confidence = SCORE_BASELINES.get(gc, (50, 50))
    explanations: list[str] = [
        f"Baseline for {gc}: risk {risk}, confidence {confidence}"
    ]

    if mesh_metrics is not None:
        if not mesh_metrics.get("is_watertight", True):
            risk += 10
            confidence -= 10
            explanations.append("Non-watertight mesh: risk +10, confidence −10")
        cc = mesh_metrics.get("component_count")
        if cc is not None and cc > 1:
            risk += 8
            explanations.append(f"{cc} disconnected components: risk +8")
        tri = mesh_metrics.get("triangle_count", 0)
        if tri > 2_000_000:
            risk += 10
            explanations.append(f"Very high triangle count ({tri:,}): risk +10")
        elif tri > 500_000:
            risk += 5
            explanations.append(f"High triangle count ({tri:,}): risk +5")

    if dxf_metrics is not None:
        spline_count = dxf_metrics.get("counts_by_type", {}).get("SPLINE", 0)
        if spline_count > 0:
            risk += 10
            confidence -= 5
            explanations.append(
                f"Splines present ({spline_count}): risk +10, confidence −5"
            )
        extents = dxf_metrics.get("extents")
        if extents is not None:
            max_dim = max(extents["size"][0], extents["size"][1])
            if max_dim > 10_000:
                risk += 5
                explanations.append(
                    f"Very large extents ({max_dim:,.1f}): risk +5 — verify units"
                )
            elif 0 < max_dim < 1:
                risk += 5
                explanations.append(
                    f"Very small extents ({max_dim:.4f}): risk +5 — verify units"
                )

    risk = max(0, min(100, risk))
    confidence = max(0, min(100, confidence))
    return risk, confidence, explanations


def _colored_bar_html(score: int, color: str) -> str:
    """Return an HTML progress bar with the given color."""
    return (
        f'<div style="background:#e0e0e0;border-radius:6px;height:18px;width:100%">'
        f'<div style="background:{color};width:{score}%;height:100%;border-radius:6px">'
        f"</div></div>"
    )


def render_scoring_section(
    risk_score: int,
    confidence_score: int,
    explanations: list[str],
) -> None:
    """Display the dual-axis scoring section with colored bars."""
    st.markdown("---")
    st.subheader("Scoring")

    risk_label, risk_color = score_to_band(risk_score, "risk")
    conf_label, conf_color = score_to_band(confidence_score, "confidence")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown(f"**Quote Risk Score:** {risk_score} — {risk_label}")
        st.markdown(_colored_bar_html(risk_score, risk_color), unsafe_allow_html=True)

    with col2:
        st.markdown(f"**Data Confidence Score:** {confidence_score} — {conf_label}")
        st.markdown(
            _colored_bar_html(confidence_score, conf_color), unsafe_allow_html=True
        )

    st.markdown("**Score drivers**")
    for line in explanations:
        st.markdown(f"- {line}")


# Build the Learn-page dropdown options: canonical extensions + aliases.
def _build_learn_options() -> list[str]:
    options: list[str] = list(FORMAT_KB.keys())
    for alias, canonical in sorted(EXTENSION_TO_FORMAT.items()):
        options.append(f"{alias}  (→ {canonical})")
    return options


LEARN_OPTIONS = _build_learn_options()

# ---------------------------------------------------------------------------
# Sidebar navigation
# ---------------------------------------------------------------------------
st.sidebar.title("CAD File Profiler")
page = st.sidebar.radio("Navigate", ["Analyze", "Learn"])

# ---------------------------------------------------------------------------
# Analyze page
# ---------------------------------------------------------------------------
if page == "Analyze":
    st.title("CNC Machining Intake")
    st.write(
        "Upload a CAD file to assess format quality and quote risk for CNC machining."
    )

    uploaded_file = st.file_uploader("Upload CAD file")

    if uploaded_file:
        filename = uploaded_file.name
        extension = os.path.splitext(filename)[1].lower()
        info = get_format_info(extension)

        if info:
            # -- Compute everything before rendering -------------------------
            mesh_metrics: dict | None = None
            dxf_metrics: dict | None = None
            mesh_error: str | None = None
            dxf_error: str | None = None

            if extension in MESH_EXTENSIONS:
                file_bytes = uploaded_file.getvalue()
                result = parse_mesh_metrics(file_bytes, extension)
                if isinstance(result, dict):
                    mesh_metrics = result
                else:
                    mesh_error = result
            elif extension == ".dxf":
                file_bytes = uploaded_file.getvalue()
                result = parse_dxf_metrics(file_bytes)
                if isinstance(result, dict):
                    dxf_metrics = result
                else:
                    dxf_error = result

            risk_score, confidence_score, explanations = compute_scores(
                info, mesh_metrics, dxf_metrics
            )
            contextual_risk = compute_contextual_risk(risk_score)

            # -- Render: summary card → scoring → triage → metrics ----------
            render_summary_card(
                info,
                filename=filename,
                extension=extension,
                contextual_risk=contextual_risk,
            )

            render_scoring_section(risk_score, confidence_score, explanations)

            triage_text = build_triage_summary(
                info, contextual_risk, mesh_metrics, dxf_metrics
            )
            st.markdown("---")
            st.markdown(f"**Triage summary:** {triage_text}")
            st.text_area(
                "Copy/paste triage summary",
                value=triage_text,
                height=80,
                disabled=True,
            )

            if mesh_metrics is not None:
                render_mesh_metrics(mesh_metrics)
            elif mesh_error is not None:
                st.warning(mesh_error)

            if dxf_metrics is not None:
                render_dxf_metrics(dxf_metrics)
            elif dxf_error is not None:
                st.warning(dxf_error)
        else:
            st.subheader("Unknown format")
            st.caption(f"{filename}  ·  {extension}")
            st.info("No format profile in knowledge base for this extension.")

# ---------------------------------------------------------------------------
# Learn page
# ---------------------------------------------------------------------------
elif page == "Learn":
    st.title("Format knowledge base")
    st.write("Browse supported CAD format profiles for CNC machining intake.")

    selected = st.selectbox("Select an extension", LEARN_OPTIONS)

    # Resolve alias labels like ".stp  (→ .step)" back to the raw extension.
    ext = selected.split("(")[0].strip() if "(" in selected else selected
    info = get_format_info(ext)

    if info:
        render_summary_card(info, extension=ext)
