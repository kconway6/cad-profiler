from __future__ import annotations

import io
import os

import ezdxf
from ezdxf import bbox as ezdxf_bbox
import numpy as np
import streamlit as st
import streamlit.components.v1 as st_components
import trimesh

st.set_page_config(page_title="CAD File Profiler", layout="centered")


def _scroll_to_top() -> None:
    """Inject JS to reset scroll position when switching pages."""
    st_components.html(
        "<script>window.parent.document.querySelector('section.main')"
        ".scrollTo(0, 0);</script>",
        height=0,
    )


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

# Plain-English "What this file is" for Learn — Formats field guide (2–4 sentences).
FORMAT_WHAT_THIS_IS: dict[str, str] = {
    ".step": (
        "STEP is an ISO standard exchange format for 3D product data. "
        "It carries exact boundary-representation (B-rep) geometry: surfaces, "
        "edges, and topology that CAM and inspection software can use directly. "
        "For CNC quoting it is the preferred neutral format because it preserves "
        "design intent without requiring the original CAD system."
    ),
    ".iges": (
        "IGES is an older neutral format that can represent both surfaces and "
        "solids. Many legacy and aerospace systems still export it. "
        "Quality varies: surface-only exports are common, and geometry may need "
        "healing before machining. STEP is preferred when the sender can provide it."
    ),
    ".stl": (
        "STL is a mesh format: the model is stored as a cloud of triangles with "
        "no exact curves or edges. It is widely used for 3D printing and quick "
        "exports. For CNC machining it is problematic because units are often "
        "ambiguous (mm vs in) and the triangulated surface is not suitable for "
        "precision toolpaths without conversion or reverse engineering."
    ),
    ".obj": (
        "OBJ is a mesh format common in animation and visualization (Blender, "
        "Maya, game engines). It can carry UVs and materials but rarely carries "
        "engineering units or precise CAD geometry. For CNC intake it shares "
        "the same drawbacks as STL: no B-rep, unclear units, and limited use "
        "for direct machining."
    ),
    ".sldprt": (
        "A SolidWorks part file contains the full parametric model: features, "
        "sketches, and history. It can only be opened in SolidWorks. "
        "For CNC quoting the risk is access: if the recipient does not have "
        "SolidWorks, they cannot inspect or re-export the geometry. Exporting to "
        "STEP is the standard workaround for neutral handoff."
    ),
    ".sldasm": (
        "A SolidWorks assembly file references multiple parts and stores mates "
        "and assembly structure. Like .sldprt it is native to SolidWorks only. "
        "For intake the same rule applies: without SolidWorks the file cannot "
        "be opened. Request a STEP export (or individual STEP parts) for "
        "quoting and CAM."
    ),
    ".prt": (
        "The .prt extension is shared by Siemens NX and PTC Creo. The file "
        "contains a full native part model but is tied to the originating "
        "system. Opening it requires the correct CAD license (NX or Creo). "
        "For cross‑platform quoting, STEP is the safe choice."
    ),
    ".catpart": (
        "A CATIA part file holds the complete part model in CATIA V5 or V6 "
        "format. It can only be opened in CATIA. Common in aerospace and "
        "automotive; for CNC quoting, suppliers without CATIA need a STEP "
        "export to evaluate and program the part."
    ),
    ".dwg": (
        "DWG is AutoCAD’s native format for 2D and 3D drawing data. It carries "
        "drafting entities, blocks, and layouts and is widely used for "
        "drawings and documentation. For CNC, 2D DWGs are often used for "
        "profile or fixture work; 3D is possible but less common in "
        "machining workflows."
    ),
    ".dxf": (
        "DXF is a 2D (and limited 3D) exchange format built around lines, "
        "arcs, circles, and polylines. It is the usual output for CNC nesting "
        "and 2D CAM. Quality depends on how it was exported: splines and "
        "complex entities may require conversion to arcs or polylines before "
        "toolpath generation."
    ),
}

# Optional parentheticals for survives/lost bullets on Learn — Formats (canonical ext → survives|lost → item → note).
FORMAT_BULLET_NOTES: dict[str, dict[str, dict[str, str]]] = {
    ".step": {
        "survives": {
            "Exact B-rep": "precise surfaces and topology",
            "Assemblies": "structure and placement",
            "Names/attributes": "PMI and metadata where present",
        },
        "lost": {"Parametric history": "feature tree and sketch constraints"},
    },
    ".iges": {
        "survives": {
            "Surfaces and solids": "depending on export",
            "Basic topology": "may need healing",
        },
        "lost": {
            "Tight tolerances": "often approximated",
            "Parametric history": "not in IGES",
            "Some assembly context": "structure can be flattened",
        },
    },
    ".stl": {
        "survives": {
            "Triangulated surface": "triangle mesh only",
            "Envelope shape": "outer shell",
        },
        "lost": {
            "Exact geometry": "no curves or edges",
            "Edges/faces": "replaced by facets",
            "Units sometimes ambiguous": "mm vs in not encoded",
        },
    },
    ".obj": {
        "survives": {
            "Triangulated mesh": "vertices and faces",
            "UVs / materials": "for visualization",
        },
        "lost": {"Precise CAD geometry": "no B-rep", "Units": "not standardized"},
    },
    ".sldprt": {
        "survives": {
            "Full feature tree": "in SolidWorks only",
            "Parameters": "dimensions and relations",
            "Materials": "in the model",
        },
        "lost": {"Nothing when opened in SolidWorks": "full fidelity in‑house only"},
    },
    ".sldasm": {
        "survives": {
            "Structure": "assembly tree",
            "mates": "constraints",
            "parts": "references to .sldprt",
        },
        "lost": {
            "Nothing when opened in SolidWorks": "cross‑platform requires STEP export"
        },
    },
    ".prt": {
        "survives": {"Full model in native system": "in NX or Creo only"},
        "lost": {"Cross-platform; need same CAD to open": "STEP for handoff"},
    },
    ".catpart": {
        "survives": {"Full part in CATIA": "in CATIA only"},
        "lost": {"Cross-platform": "STEP for non‑CATIA shops"},
    },
    ".dwg": {
        "survives": {
            "Drafting entities": "lines, arcs, text, dimensions",
            "Blocks": "reusable symbols",
            "Layouts": "paper space",
        },
        "lost": {
            "Parametric 3D in some workflows": "3D can be present but not always portable"
        },
    },
    ".dxf": {
        "survives": {
            "Lines, arcs": "and circles, polylines",
            "Blocks": "block definitions",
            "Layers": "layer names and visibility",
        },
        "lost": {
            "Proprietary objects": "custom entities may not translate",
            "Full fidelity": "export options affect what is written",
        },
    },
}


MATERIALS = [
    "Aluminum — 6061-T6 (default)",
    "Aluminum — 7075-T6",
    "Steel — 1018 (low carbon)",
    "Steel — 4140 (alloy)",
    "Stainless Steel — 304/316",
    "Titanium — Ti-6Al-4V",
    "Inconel — 718",
    "Other / Unknown",
]


MATERIAL_KB: dict[str, dict] = {
    "Aluminum — 6061-T6 (default)": {
        "difficulty": "Low",
        "machining_reality": (
            "6061-T6 is the most forgiving CNC material in common use. It"
            " shears cleanly, produces well-formed chips, and allows"
            " aggressive feeds and speeds (SFM 800–1200+) with standard"
            " uncoated or ZrN-coated carbide endmills. Tool life is"
            ' excellent — a single 1/2" endmill can often run 200+ parts'
            " before replacement. The material is thermally conductive, so"
            " heat leaves through the chip rather than building at the"
            " cutting edge, which means mist coolant or even dry cutting"
            " is viable for many operations."
        ),
        "cost_drivers": [
            "Very low tool wear — standard 2- or 3-flute carbide endmills last hundreds of parts",
            "Fast cycle times: feeds of 80–150 IPM and full-slotting depths of 1×D are routine",
            "Mist or flood coolant both work; no special coolant delivery needed",
            "Low scrap risk — the material is ductile and forgiving of minor programming errors",
            "Stock is cheap and widely available in plate, bar, and round",
        ],
        "quote_implications": [
            "Straightforward quoting — cycle time estimates are reliable and tool cost is minimal",
            "Confirm temper: T6 (general purpose) vs T651 (stress-relieved, better flatness for plates)",
            "Anodize-ready surfaces need Ra 32–63 µin finish passes; factor in if cosmetic",
            'Thin-wall features (<0.040") are achievable but may need reduced stepover and spring passes',
        ],
    },
    "Aluminum — 7075-T6": {
        "difficulty": "Low",
        "machining_reality": (
            "7075-T6 is significantly harder and stronger than 6061 (UTS"
            " ~83 ksi vs ~45 ksi) and machines at similar speeds, but it"
            " is less forgiving under aggressive cuts. It produces shorter,"
            " snappier chips and is more prone to residual-stress warping"
            " in thin-wall or asymmetric parts. Hogging pockets in 7075"
            " plate can release internal stresses that bow or twist the"
            " part after unclamping — stress-relief cycles or alternating"
            " roughing sides may be needed."
        ),
        "cost_drivers": [
            "Tool wear ~20–30% higher than 6061; coated carbide (AlTiN) extends life at high speeds",
            "Feeds and speeds comparable to 6061 (SFM 600–1000) but with slightly lower DOC limits",
            "Residual stress is the hidden cost: thin-wall parts may need intermediate stress relief or flip roughing",
            "Stock cost ~1.5–2× 6061; scrapping a large 7075 billet is a real financial hit",
            "Chip evacuation is easier than 6061 (shorter chips) but chip-to-surface contact can gall soft tooling",
        ],
        "quote_implications": [
            "Confirm temper and whether plate is pre-stretched (T7351) to reduce residual stress",
            "Grain direction matters for aerospace — ask if orientation relative to rolling direction is specified",
            "Material certs (mill certs) are typically required; AMS 4078 / AMS 4045 callouts are common",
            "Ask about stress-relief strategy for thin-wall geometry — this can add ops and cycle time",
        ],
    },
    "Steel — 1018 (low carbon)": {
        "difficulty": "Medium",
        "machining_reality": (
            "1018 is soft (~Brinell 126, ~72 HRB) and ductile, which makes"
            " it gummy rather than brittle. It produces long, stringy chips"
            " that wrap around tooling and clog flutes if chip-breaking"
            " geometry isn't used. Built-up edge (BUE) is common at low"
            " cutting speeds — the material welds itself to the tool tip"
            " and tears rather than shearing. Running faster (SFM 400–600)"
            " with coated inserts and positive rake geometry reduces BUE"
            " and improves finish. Compared to 4140, chip control is worse"
            " and surface finish is harder to achieve, but tool wear is"
            " lower and the material is very forgiving structurally."
        ),
        "cost_drivers": [
            "Tool wear is moderate; BUE is the bigger threat — destroys finish before it destroys the tool",
            "Cycle times ~2–3× aluminum: typical SFM 400–600 with carbide, lower with HSS",
            "Flood coolant strongly recommended for chip evacuation and BUE prevention",
            "Stringy chips can bird-nest on the tool or workpiece, causing surface damage and stoppages",
            "Stock is cheap and widely available; scrap cost is low per unit weight",
        ],
        "quote_implications": [
            "Ask if carburizing or case hardening is planned after machining — tolerances shift after heat treat",
            "Surface finish expectations: 1018 doesn't take a good polish; Ra 63 µin is realistic, 32 µin is a fight",
            "Confirm whether customer needs cold-rolled (1018 CF) vs hot-rolled — hardness and surface differ",
            "Post-machining heat treat (normalize, carburize, Q&T) must be specified up front",
        ],
    },
    "Steel — 4140 (alloy)": {
        "difficulty": "Medium",
        "machining_reality": (
            "4140 is a step up from 1018 in every machining dimension."
            " Pre-hard (28–32 HRC) it cuts cleanly with coated carbide,"
            " breaks chips well, and produces a better surface finish than"
            " low-carbon steel — the chromium–molybdenum alloy content"
            " actually improves machinability over plain carbon grades."
            " However, it generates more heat, wears tools faster, and the"
            " cost jump to hardened 4140 (>40 HRC) is dramatic: tool life"
            " drops by 50–70%, speeds must be halved, and ceramic or CBN"
            " inserts may be needed."
        ),
        "cost_drivers": [
            "Tool wear 1.5–2× that of 1018; coated carbide (TiAlN, AlCrN) is required, not optional",
            "Cycle times ~3–4× aluminum in pre-hard condition; ~5–6× in hardened (>40 HRC) condition",
            "Flood coolant is essential; through-spindle preferred for deep pockets and holes",
            "Pre-hard vs annealed vs hardened condition fundamentally changes the quoting equation",
            "Stock cost ~2× low-carbon steel; scrap is painful on large billets",
        ],
        "quote_implications": [
            "Confirm exact hardness condition: annealed (~197 HB), pre-hard (28–32 HRC), or hardened (40+ HRC)",
            "If hardened after machining, tolerances will shift — budget for finish grind on critical dims",
            "Ask about Q&T (quench and temper) requirements — ASTM A829 and AMS 6382 are common callouts",
            "Material certs are expected for structural, hydraulic, and oil/gas applications",
        ],
    },
    "Stainless Steel — 304/316": {
        "difficulty": "High",
        "machining_reality": (
            "Austenitic stainless (304, 316) work-hardens aggressively:"
            " every pass that rubs instead of shearing creates a thin,"
            " glass-hard surface layer that dulls the next pass's cutting"
            " edge. This means dull tools, light feeds, dwelling, and"
            " re-cutting spring passes all make the problem worse. The fix"
            " is sharp tools, rigid setups, aggressive chip loads (stay"
            " above minimum chip thickness), and never letting the tool"
            " rub. Tool life is roughly 1/3 to 1/4 of carbon steel at"
            " equivalent feeds, and cycle times are 2–3× longer."
        ),
        "cost_drivers": [
            "High tool wear from work hardening: expect tool life 1/3 to 1/4 of carbon steel",
            "Cycle times 2–3× carbon steel — SFM 250–400 typical; slower still with interrupted cuts",
            "Flood coolant is mandatory: the material's low thermal conductivity traps heat at the cut",
            "Rigid workholding is critical — chatter causes rubbing, which triggers the work-hardening spiral",
            "Scrap risk is elevated: a work-hardened surface layer can render a part unsalvageable",
        ],
        "quote_implications": [
            "Confirm exact alloy: 304 (general) vs 316 (marine/chemical — slightly harder to machine)",
            "Surface finish matters more here — work-hardened surfaces tear; Ra callouts must be explicit",
            "Passivation (citric or nitric acid) is often required post-machining; electropolish adds more cost",
            "Lead times run longer: slower cycle times and more frequent tool changes reduce daily throughput",
        ],
    },
    "Titanium — Ti-6Al-4V": {
        "difficulty": "Very High",
        "machining_reality": (
            "Ti-6Al-4V combines high strength (UTS ~130 ksi), very low"
            " thermal conductivity (~1/6 of steel), and significant"
            " springback. Because heat doesn't leave through the chip, it"
            " concentrates at the tool tip — cutting-edge temperatures can"
            " exceed 600 °C even at modest speeds, causing rapid crater"
            " wear and edge breakdown. Springback means the material"
            " deflects under the tool and then recovers, causing"
            " under-cutting on thin walls and poor dimensional control."
            " Expect cycle times 3–5× aluminum and tool life 1/5 to 1/10"
            " of what you'd see in 6061."
        ),
        "cost_drivers": [
            "Extreme tool wear driven by heat: tool life 1/5 to 1/10 of aluminum; premium coated carbide (AlTiN, nanocomposite) or PCD required",
            "Very slow cycle times — SFM 100–200 typical; 3–5× aluminum for equivalent geometry",
            "High-pressure through-spindle coolant (1000+ PSI) strongly recommended to manage cutting-edge heat",
            "Springback causes dimensional drift on thin walls; multiple light finish passes or spring passes needed",
            "Stock cost is very high ($15–40/lb for bar); a single scrapped billet can cost hundreds of dollars",
        ],
        "quote_implications": [
            "Confirm grade (Grade 5 is Ti-6Al-4V) and condition: annealed, STA (solution treated and aged), or ELI (extra low interstitials for medical)",
            "Material certs and full batch traceability are almost always required (AMS 4928, AMS 4911)",
            "Ask about post-machining: chemical milling, shot peening, anodize, or PVD coatings are common in aerospace",
            "Budget for significantly longer lead times and higher per-part cost — plan for 4–8× the cost of equivalent 6061 parts",
        ],
    },
    "Inconel — 718": {
        "difficulty": "Very High",
        "machining_reality": (
            "Inconel 718 is among the most punishing CNC materials."
            " It work-hardens like stainless but worse, has even lower"
            " thermal conductivity than titanium, and is highly abrasive"
            " due to hard carbide particles in the microstructure. Cutting"
            " temperatures routinely exceed 700 °C. Ceramic inserts can"
            " rough at higher speeds (SFM 600–1000) but are brittle and"
            " demand rigid, chatter-free setups. Carbide finishing at SFM"
            " 70–120 is common. Tool life in Inconel is often measured in"
            " minutes, not parts — a single roughing insert may last"
            " 5–15 minutes of cut time."
        ),
        "cost_drivers": [
            "Extreme tool wear: roughing inserts may last only 5–15 minutes of cutting time; ceramics needed for productivity",
            "Very slow cycle times with carbide (SFM 70–120); ceramics are faster but require perfect rigidity and zero chatter",
            "High-pressure coolant (1000+ PSI through spindle) is mandatory — inadequate coolant destroys tools in seconds",
            "Cutting forces are very high; specialized high-clamp-force workholding and rigid, high-torque spindles are required",
            "Stock cost is extreme ($30–80/lb); scrap is catastrophically expensive on large forgings or billets",
        ],
        "quote_implications": [
            "Confirm alloy condition: solution annealed (~30 HRC), age-hardened (~40–44 HRC), or direct-aged — machining difficulty varies enormously",
            "Material certs with full heat-lot traceability are mandatory (AMS 5662, AMS 5663)",
            "Verify the shop has Inconel experience, ceramic tooling, and high-pressure coolant capability before committing",
            "Expect cost and lead time 6–10× equivalent steel parts; fewer shops are qualified and capacity is limited",
        ],
    },
    "Other / Unknown": {
        "difficulty": "Unknown",
        "machining_reality": (
            "Material is not specified. Without knowing the alloy, hardness,"
            " and thermal properties, it is impossible to estimate tool wear"
            " rates, cycle times, or coolant requirements. A quote without"
            " a confirmed material is a guess — the difference between"
            " machining 6061 aluminum and Inconel 718 is easily a 10×"
            " cost multiplier on the same geometry."
        ),
        "cost_drivers": [
            "Tool wear is unpredictable: a 10× range between easy aluminum and superalloys",
            "Cycle time cannot be estimated — feeds, speeds, and depth of cut depend entirely on material",
            "Coolant strategy (mist, flood, high-pressure TSC) depends on material thermal properties",
            "Workholding forces and rigidity requirements scale with material hardness and cutting forces",
            "Scrap risk is unquantifiable: material cost per pound ranges from $2 (aluminum) to $80 (Inconel)",
        ],
        "quote_implications": [
            "Request exact material specification (alloy, grade, temper/condition) before quoting",
            "Confirm hardness or heat treat state — this matters more than alloy name alone for machinability",
            "Ask about any coatings, plating, or special post-machining processes",
            "Without material, any quoted price is a placeholder — flag this to the customer explicitly",
        ],
    },
}


def render_material_section(material: str) -> None:
    """Display the material machining reality callout."""
    mat_info = MATERIAL_KB.get(material)
    if mat_info is None:
        return

    st.markdown("---")
    st.subheader("Material machining reality")

    st.markdown(f"**Difficulty:** {mat_info['difficulty']}")
    st.write(mat_info["machining_reality"])

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Cost drivers**")
        for item in mat_info["cost_drivers"]:
            st.markdown(f"- {item}")

    with col2:
        st.markdown("**Quote implications**")
        for item in mat_info["quote_implications"]:
            st.markdown(f"- {item}")


def _material_triage_label(material: str) -> str:
    """Return a clean material label for triage text (strip parenthetical notes)."""
    if " (" in material:
        return material.split(" (")[0].strip()
    return material


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


def _quoting_reality_paragraph(info: dict) -> str:
    """Turn dfm_quote_confidence, quote_risk_baseline, automation_friendliness into a short narrative."""
    conf = info["dfm_quote_confidence"]
    risk = info["quote_risk_baseline"]
    auto = info["automation_friendliness"]
    parts: list[str] = []
    if conf == "High":
        parts.append(
            "Quote confidence is high: the format usually carries enough information to estimate and program without guesswork."
        )
    elif conf == "Medium":
        parts.append(
            "Quote confidence is medium: you can often quote from the file, but missing details (units, tolerances, condition) may require a round of clarification."
        )
    else:
        parts.append(
            "Quote confidence is low: the file alone is rarely enough to quote accurately; expect to ask for units, native or STEP geometry, or additional specs."
        )
    if risk == "High":
        parts.append(
            "Baseline quote risk is high—rework, miscommunication, or conversion failures are more likely."
        )
    elif risk == "Medium":
        parts.append(
            "Baseline quote risk is medium; access to the right tools or a neutral export reduces risk."
        )
    else:
        parts.append("Baseline quote risk is low for CNC intake.")
    if auto == "High":
        parts.append(
            "Automation friendliness is high: the format is well suited to scripted checks and toolpath generation."
        )
    elif auto == "Medium":
        parts.append(
            "Automation is possible but may require format-specific handling or cleanup."
        )
    else:
        parts.append(
            "Automation is limited; manual review or conversion is often needed."
        )
    return " ".join(parts)


def _next_ask_reference(gc: str) -> tuple[str, str]:
    """Return (standard next-ask sentence, optional line for unknown material)."""
    unknown_line = "If material is unknown, also confirm material, heat treat condition, and any coatings/special processes."
    if gc == "Mesh":
        return (
            "Confirm units (mm vs in) and request a STEP or native CAD file if available.",
            unknown_line,
        )
    if gc == "2D Drawing":
        return (
            "Confirm dimensions, tolerances, and material thickness are specified in the drawing.",
            unknown_line,
        )
    return "Confirm tolerances and surface finish requirements.", unknown_line


def render_summary_card(
    info: dict,
    *,
    filename: str | None = None,
    extension: str | None = None,
    material: str | None = None,
    contextual_risk: str | None = None,
) -> None:
    """Render a summary card with header, two columns, and bullet lists.

    When *filename* / *extension* are provided (Analyze page) the caption
    shows them.  When *material* is provided it is appended to the caption.
    When *contextual_risk* is provided the adjusted-risk row is included.
    """
    st.subheader(info["label"])
    if filename and extension and material:
        st.caption(f"{filename}  ·  {extension}  ·  {material}")
    elif filename and extension:
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


def render_format_field_guide(info: dict, canonical_ext: str) -> None:
    """Render the Learn — Formats field guide: What this file is, Where it comes from, Keep vs lose, Quoting reality, Scoring, What to ask next."""
    gc = info["geometry_class"]
    bullet_notes = FORMAT_BULLET_NOTES.get(canonical_ext, {})

    # What this file is
    what = FORMAT_WHAT_THIS_IS.get(canonical_ext, "")
    if what:
        st.subheader("What this file is")
        st.write(what)

    # Where it comes from
    st.subheader("Where it comes from")
    st.caption("Typical authoring tools and common use cases.")
    col_where1, col_where2 = st.columns(2)
    with col_where1:
        st.markdown("**Typical authoring tools**")
        for item in info["typical_authoring_tools"]:
            st.markdown(f"- {item}")
    with col_where2:
        st.markdown("**Common use cases**")
        for item in info["common_use_cases"]:
            st.markdown(f"- {item}")

    # What you keep vs what you lose
    st.subheader("What you keep vs what you lose")
    col_keep, col_lose = st.columns(2)
    with col_keep:
        st.markdown("**Survives**")
        for item in info["survives"]:
            note = bullet_notes.get("survives", {}).get(item)
            st.markdown(f"- {item}" + (f" ({note})" if note else ""))
    with col_lose:
        st.markdown("**Lost or at risk**")
        for item in info["lost"]:
            note = bullet_notes.get("lost", {}).get(item)
            st.markdown(f"- {item}" + (f" ({note})" if note else ""))

    # Quoting reality
    st.subheader("Quoting reality")
    st.write(_quoting_reality_paragraph(info))

    # Typical manufacturing workflow
    _WORKFLOW_FLOWS: dict[str, tuple[str, str | None]] = {
        ".step": ("STEP → CAM → machining", None),
        ".iges": (
            "IGES → stitch/repair → solidify → CAM → machining",
            "Common failure: surface gaps that prevent solid creation; healing may take multiple rounds.",
        ),
        ".stl": (
            "STL → remodel or surface fit → CAM → machining",
            "Common failure: ambiguous units (mm vs in) and faceted surfaces too coarse for precision toolpaths.",
        ),
        ".obj": (
            "OBJ → remodel or surface fit → CAM → machining",
            "Common failure: no engineering units; visualization-quality mesh rarely meets CNC tolerance needs.",
        ),
        ".sldprt": (
            "SLDPRT → export to STEP → CAM → machining",
            "Common failure: recipient lacks SolidWorks; file cannot be opened or re-exported.",
        ),
        ".sldasm": (
            "SLDASM → export to STEP (per-part) → CAM → machining",
            "Common failure: missing referenced parts or broken assembly mates after export.",
        ),
        ".prt": (
            "PRT → export to STEP → CAM → machining",
            "Common failure: wrong CAD system (NX vs Creo); file may not open at all.",
        ),
        ".catpart": (
            "CATPART → export to STEP → CAM → machining",
            "Common failure: no CATIA license; part is inaccessible without it.",
        ),
        ".dwg": (
            "DWG → extract 2D profiles → verify dims/tolerances → 2.5D CAM → machining",
            "Common failure: 3D data mixed with 2D layouts; unclear which entities define the part.",
        ),
        ".dxf": (
            "DXF → verify units + thickness + tolerances → 2.5D CAM/profile → machining",
            "Common failure: splines that CAM cannot process; entity cleanup required.",
        ),
    }
    _flow = _WORKFLOW_FLOWS.get(canonical_ext)
    if _flow:
        st.subheader("Typical manufacturing workflow")
        st.markdown(f"**{_flow[0]}**")
        if _flow[1]:
            st.caption(_flow[1])

    # How scoring works here
    st.subheader("How scoring works here")
    risk_base, conf_base = SCORE_BASELINES.get(gc, (50, 50))
    st.markdown(
        f"**Baseline (this geometry class):** risk {risk_base}, confidence {conf_base}."
    )
    if canonical_ext in MESH_EXTENSIONS:
        st.caption(
            "Metric-based adjustments that can apply when a mesh file is analyzed:"
        )
        st.markdown(
            "- **Non-watertight mesh:** risk +10, confidence −10 — gaps or holes in the surface."
        )
        st.markdown(
            "- **Multiple disconnected components:** risk +8 — more than one body in the file."
        )
        st.markdown(
            "- **High triangle count (>500k):** risk +5 — heavy meshes are harder to process and may indicate poor export."
        )
        st.markdown(
            "- **Very high triangle count (>2M):** risk +10 — component count is skipped for performance; risk still increases."
        )
    elif canonical_ext == ".dxf":
        st.caption("Metric-based adjustments that can apply when a DXF is analyzed:")
        st.markdown(
            "- **Splines present:** risk +10, confidence −5 — may need conversion to arcs/polylines for CAM."
        )
        st.markdown(
            "- **Very large extents (max dimension >10,000):** risk +5 — verify units (e.g. mm vs tenths)."
        )
        st.markdown(
            "- **Very small extents (0 < max dimension < 1):** risk +5 — verify units (e.g. in vs mm)."
        )
    else:
        st.caption(
            "No file-level metrics are extracted for this format; scoring uses the baseline only."
        )

    # What to ask next
    st.subheader("What to ask next")
    next_ask, unknown_line = _next_ask_reference(gc)
    st.write(next_ask)
    st.caption(unknown_line)


def build_triage_summary(
    info: dict,
    contextual_risk: str,
    material: str,
    mesh_metrics: dict | None = None,
    dxf_metrics: dict | None = None,
) -> str:
    """Return a max-2-sentence triage paragraph for Analyze mode."""
    gc = info["geometry_class"]
    baseline = info["quote_risk_baseline"]
    mat_label = _material_triage_label(material)
    unknown_material = material == "Other / Unknown"

    # -- Sentence 1: material + risk assessment + cleanup flags --------
    if contextual_risk == baseline:
        risk_part = (
            f"Material: {mat_label} — "
            f"{gc} geometry with {baseline.lower()} quote risk"
        )
    else:
        risk_part = (
            f"Material: {mat_label} — "
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
    unknown_clause = (
        "material, heat treat condition, and any coatings/special processes"
    )

    if gc == "Mesh":
        if unknown_material:
            next_ask = (
                "Confirm units (mm vs in) and request a STEP or native CAD "
                f"file if available; also confirm {unknown_clause}."
            )
        else:
            next_ask = (
                "Confirm units (mm vs in) and request a STEP or native CAD "
                "file if available."
            )
    elif gc == "2D Drawing":
        if unknown_material:
            next_ask = (
                "Confirm dimensions, tolerances, and material thickness are "
                f"specified in the drawing; also confirm {unknown_clause}."
            )
        else:
            next_ask = (
                "Confirm dimensions, tolerances, and material thickness are "
                "specified in the drawing."
            )
    else:
        if unknown_material:
            next_ask = (
                f"Confirm tolerances, surface finish requirements, "
                f"{unknown_clause}."
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


def _cnc_suitability_line(gc: str, conf: str) -> str:
    """One-line CNC suitability summary derived from geometry class and DFM confidence."""
    if gc == "B-Rep" and conf == "High":
        return "Ideal for CNC — exact geometry, reliable quoting"
    if gc == "B-Rep":
        return "Good for CNC — exact geometry, verify completeness"
    if gc == "Surface" and conf in ("High", "Medium"):
        return "Usable for CNC — may need healing; STEP preferred"
    if gc == "Surface":
        return "Risky for CNC — surface gaps common; healing required"
    if gc == "Mesh":
        return "Poor for CNC — no exact geometry; reverse engineering likely needed"
    if gc == "Parametric" and conf == "High":
        return "Excellent in-house — requires native CAD; export to STEP for handoff"
    if gc == "Parametric":
        return "Good if accessible — requires native CAD license to open"
    if gc == "2D Drawing" and conf in ("High", "Medium"):
        return "Good for 2D CNC / profiles — confirm dims and tolerances"
    return "Usable for 2D work — verify completeness"


def _build_comparison_rows() -> list[dict]:
    """Build comparison table rows for all canonical formats, sorted by baseline risk."""
    rows: list[dict] = []
    for ext, info in FORMAT_KB.items():
        gc = info["geometry_class"]
        risk_base, conf_base = SCORE_BASELINES.get(gc, (50, 50))
        risk_label, _ = score_to_band(risk_base, "risk")
        conf_label, _ = score_to_band(conf_base, "confidence")
        rows.append(
            {
                "ext": ext,
                "gc": gc,
                "risk_base": risk_base,
                "risk_label": risk_label,
                "conf_base": conf_base,
                "conf_label": conf_label,
                "auto": info["automation_friendliness"],
                "suitability": _cnc_suitability_line(gc, info["dfm_quote_confidence"]),
            }
        )
    rows.sort(key=lambda r: r["risk_base"])
    return rows


# ---------------------------------------------------------------------------
# Sidebar navigation
# ---------------------------------------------------------------------------
st.sidebar.title("CAD File Profiler")
page = st.sidebar.radio("Navigate", ["Analyze", "Learn — Formats", "Learn — Materials"])

# ---------------------------------------------------------------------------
# Analyze page
# ---------------------------------------------------------------------------
if page == "Analyze":
    _scroll_to_top()
    st.title("CNC Machining Intake")
    st.write(
        "Upload a CAD file to assess format quality and quote risk for CNC machining."
    )

    material = st.selectbox("Material", MATERIALS)

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
                material=material,
                contextual_risk=contextual_risk,
            )

            render_material_section(material)

            render_scoring_section(risk_score, confidence_score, explanations)

            triage_text = build_triage_summary(
                info, contextual_risk, material, mesh_metrics, dxf_metrics
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
# Learn — Formats page
# ---------------------------------------------------------------------------
elif page == "Learn — Formats":
    _scroll_to_top()
    st.title("Format knowledge base")
    st.write("Browse supported CAD format profiles for CNC machining intake.")

    # ------------------------------------------------------------------
    # Format comparison table
    # ------------------------------------------------------------------
    st.subheader("Format comparison (CNC machining)")
    st.caption("All canonical formats, sorted from lowest to highest baseline risk.")

    _comp_rows = _build_comparison_rows()

    _header = (
        "| Extension | Geometry | Risk | Confidence | Automation | CNC suitability |\n"
        "|-----------|----------|------|------------|------------|----------------|\n"
    )
    _body = ""
    for _r in _comp_rows:
        _body += (
            f"| `{_r['ext']}` "
            f"| {_r['gc']} "
            f"| {_r['risk_base']} ({_r['risk_label']}) "
            f"| {_r['conf_base']} ({_r['conf_label']}) "
            f"| {_r['auto']} "
            f"| {_r['suitability']} |\n"
        )
    st.markdown(_header + _body)

    st.markdown("---")

    selected = st.selectbox("Select an extension", LEARN_OPTIONS)

    # Resolve alias labels like ".stp  (→ .step)" back to the raw extension and canonical key.
    ext = selected.split("(")[0].strip() if "(" in selected else selected
    ext_lower = ext.lower()
    canonical_ext = EXTENSION_TO_FORMAT.get(ext_lower, ext_lower)
    info = get_format_info(ext)

    if info:
        st.subheader(info["label"])
        st.caption(f"{ext}  ·  {info['geometry_class']}")
        render_format_field_guide(info, canonical_ext)

# ---------------------------------------------------------------------------
# Learn — Materials page
# ---------------------------------------------------------------------------
elif page == "Learn — Materials":
    _scroll_to_top()
    st.title("CNC Machining Materials")
    st.write(
        "How material choice drives cost, cycle time, and quoting risk in "
        "CNC machining."
    )

    # ------------------------------------------------------------------
    # A. How materials change cost and margin
    # ------------------------------------------------------------------
    st.header("How materials change cost and margin")

    st.markdown(
        "In CNC machining, **machine time is the dominant cost driver**. "
        "Material choice directly controls how fast you can cut, how long "
        "your tools last, and how much overhead goes into each part. "
        "Understanding these dynamics is essential for accurate quoting."
    )

    st.markdown("#### Machine time")
    st.markdown(
        "Harder and tougher materials require slower feeds and speeds, "
        "directly increasing cycle time. A part that runs in 10 minutes "
        "in 6061 aluminum may take 30–50 minutes in titanium or Inconel."
    )

    st.markdown("#### Tool wear and tool changes")
    st.markdown(
        "Every material wears tooling differently. Aluminum is gentle on "
        "cutters; stainless and nickel alloys destroy them. Tool changes "
        "add cycle time and insert/endmill cost to every part."
    )
    st.markdown(
        "- Aluminum: standard carbide endmills, long tool life\n"
        "- Carbon steel: coated carbide, moderate life\n"
        "- Stainless steel: premium coated carbide, frequent changes\n"
        "- Titanium / Inconel: specialty inserts (ceramic, CBN), "
        "aggressive replacement schedules"
    )

    st.markdown("#### Heat management and coolant")
    st.markdown(
        "Cutting generates heat. Materials with low thermal conductivity "
        "(titanium, Inconel) concentrate heat at the tool tip, "
        "accelerating wear. Effective coolant delivery — especially "
        "high-pressure through-spindle coolant — becomes mandatory for "
        "these materials, adding machine capability requirements and cost."
    )

    st.markdown("#### Work hardening")
    st.markdown(
        "Austenitic stainless steels (304, 316) and some nickel alloys "
        "work-harden rapidly. If the tool rubs instead of cutting — due "
        "to dull edges, light feeds, or poor rigidity — the surface "
        "hardens and becomes even more difficult to machine. This creates "
        "a vicious cycle of accelerating tool wear and degrading surface "
        "finish."
    )

    st.markdown("#### Scrap risk and rework sensitivity")
    st.markdown(
        "Expensive stock (titanium, Inconel, 7075) makes scrap costly. "
        "Difficult-to-machine materials also leave less margin for rework "
        "— a scrapped titanium billet can represent hundreds of dollars in "
        "material alone, before any machine time is accounted for."
    )

    st.markdown("#### Inspection overhead")
    st.markdown(
        "Tighter tolerances in harder materials mean more in-process "
        "checks, CMM time, and potential first-article inspection (FAI) "
        "requirements. Aerospace and medical materials (Ti-6Al-4V, "
        "Inconel 718) almost always carry traceability and certification "
        "requirements that add administrative cost."
    )

    # ------------------------------------------------------------------
    # B. Material quick reference
    # ------------------------------------------------------------------
    st.markdown("---")
    st.header("Material quick reference")

    learn_material = st.selectbox("Material", MATERIALS, key="learn_material")

    mat_info = MATERIAL_KB.get(learn_material)
    if mat_info:
        st.markdown(f"**Difficulty:** {mat_info['difficulty']}")
        st.write(mat_info["machining_reality"])

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Cost drivers**")
            for item in mat_info["cost_drivers"]:
                st.markdown(f"- {item}")
        with col2:
            st.markdown("**Quote implications**")
            for item in mat_info["quote_implications"]:
                st.markdown(f"- {item}")

    # ------------------------------------------------------------------
    # C. Rule-of-thumb takeaways
    # ------------------------------------------------------------------
    st.markdown("---")
    st.header("Rule-of-thumb takeaways")

    _takeaways = [
        "6061 aluminum is the safest default — it's forgiving, fast to cut, and cheap to quote.",
        "7075 is stronger than 6061 but less tolerant of thin walls and residual stress.",
        "Low-carbon steel (1018) is gummy — keep feeds aggressive to avoid work hardening and built-up edge.",
        "4140 pre-hard (28–32 HRC) is manageable; above 40 HRC, expect a significant cost jump.",
        "Stainless work-hardens — keep tools sharp, feeds engaged, and never let the cutter rub.",
        "Titanium and Inconel punish tooling and reward conservative speeds with aggressive depth of cut.",
        "Harder materials amplify every setup weakness: rigidity, workholding, and runout all matter more.",
        "Through-spindle coolant is a nice-to-have for steel, but mandatory for titanium and Inconel.",
        "Material cost matters twice: once for the stock, and again if you scrap it.",
        "Always ask for material condition (temper, hardness, heat treat state) — it changes the quote more than alloy alone.",
        "If the customer says 'stainless' without specifying a grade, assume 304 and ask — 17-4 PH and 316 are very different jobs.",
        "When tolerances are tight on hard materials, plan for a finish pass and budget CMM time.",
    ]

    for item in _takeaways:
        st.markdown(f"- {item}")

    # ------------------------------------------------------------------
    # D. What to ask customers
    # ------------------------------------------------------------------
    st.markdown("---")
    st.header("What to ask customers")

    st.markdown("#### Material spec & condition")
    st.markdown(
        "- Exact alloy and grade (e.g., 6061-T6, 304L, Ti-6Al-4V)\n"
        "- Temper or hardness condition (annealed, pre-hard, aged)\n"
        "- Applicable material standard (AMS, ASTM, DIN, JIS)\n"
        "- Material certification or mill cert requirements"
    )

    st.markdown("#### Stock form")
    st.markdown(
        "- Plate, bar, round, tube, forging, or billet\n"
        "- Near-net-shape or oversized stock\n"
        "- Customer-furnished material (CFM) or shop-procured"
    )

    st.markdown("#### Quantity & lead time")
    st.markdown(
        "- Prototype vs production quantity\n"
        "- Required delivery date or lead time window\n"
        "- Blanket order or one-time run\n"
        "- Any material lead time concerns (long-lead alloys)"
    )

    st.markdown("#### Critical tolerances / datums / GD&T")
    st.markdown(
        "- Tightest dimensional tolerance on the part\n"
        "- Key datums and datum reference frames\n"
        "- Any GD&T callouts (true position, profile, runout)\n"
        "- Whether tolerances are pre- or post-heat-treat"
    )

    st.markdown("#### Surface finish, coatings, heat treat, special processes")
    st.markdown(
        "- Surface finish requirements (Ra / Rz callouts)\n"
        "- Coatings (anodize, plating, PVD, paint)\n"
        "- Heat treat (quench & temper, age hardening, stress relief)\n"
        "- Special processes (passivation, shot peening, NDT)"
    )

    st.markdown("#### Inspection requirements")
    st.markdown(
        "- First Article Inspection (FAI) per AS9102 or equivalent\n"
        "- CMM dimensional report\n"
        "- Material certs and traceability\n"
        "- Any customer-specific quality clauses or QMS requirements"
    )
