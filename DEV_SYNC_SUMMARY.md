# CAD File Profiler — CNC Machining Version — Development Summary

Paste the sections below into ChatGPT to sync a collaborator. No code blocks, no links, no proposed features — only current state, what changed, known issues, and verification steps.

---

## 1) Current State (5–10 bullets)

- Three pages: Analyze, Learn — Formats, Learn — Materials. Sidebar radio selects page; each page calls a scroll-to-top helper so switching pages resets scroll position.
- Analyze page: Material selectbox (eight options, default Aluminum — 6061-T6), file uploader, then when a file is uploaded and format is known: summary card (filename · extension · material), Material machining reality section, Scoring (dual-axis bars + score drivers), Triage summary (bold + disabled text area for copy/paste), then Extracted metrics (mesh or DXF only for supported types). Unknown format shows a short message and no scoring/triage/metrics.
- FORMAT_KB has ten canonical extensions: .step, .iges, .stl, .obj, .sldprt, .sldasm, .prt, .catpart, .dwg, .dxf. Alias map EXTENSION_TO_FORMAT: .stp → .step, .igs → .iges. get_format_info(extension) lowercases, resolves alias, then looks up FORMAT_KB; Learn — Formats dropdown shows canonical extensions plus alias entries labeled like ".stp  (→ .step)".
- Measurement: .stl and .obj parsed with trimesh (BytesIO, file_type); Scene is dump(concatenate=True) to one mesh. Returns triangle_count, bbox_dims/min/max (4 decimals), is_watertight, component_count (from mesh.split(only_watertight=False) only when triangle_count ≤ 1,000,000; otherwise None for performance). .dxf decoded UTF-8 with Latin-1 fallback, parsed with ezdxf; modelspace iterated for total_entities, counts_by_type (LINE, ARC, CIRCLE, LWPOLYLINE, POLYLINE, SPLINE, TEXT, MTEXT), layer_count, and extents (min/max/size via ezdxf bbox). DXF display suppresses Z in extents when size Z is zero. Parse errors surface as st.warning in Analyze; no metrics for other formats (STEP, IGES, native CAD).
- Scoring: Single workflow (CNC machining). SCORE_BASELINES keyed by geometry_class only: B-Rep (15, 85), Surface (40, 55), Mesh (75, 25), Parametric (20, 80), 2D Drawing (45, 50). compute_scores(info, mesh_metrics, dxf_metrics) starts from baseline (risk, confidence), applies metric-based adjustments, then clamps both to 0–100. score_to_band(score, "risk"|"confidence") returns (label, hex_color) from RISK_BANDS / CONFIDENCE_BANDS (five bands each). Contextual risk label is derived only from the numeric risk score via compute_contextual_risk(risk_score) → score_to_band(risk_score, "risk"); no separate label logic.
- Metric adjustments (unchanged): mesh non-watertight → risk +10, confidence −10; mesh component_count > 1 (when not skipped) → risk +8; mesh triangle_count > 500k → risk +5, > 2M → risk +10; DXF splines present → risk +10, confidence −5; DXF extents max dimension (X or Y) > 10,000 → risk +5; DXF extents max dimension &gt; 0 and &lt; 1 → risk +5. All scores clamped to [0, 100].
- Triage summary: build_triage_summary returns exactly two sentences. Sentence 1: "Material: {mat_label} —" then geometry class and quote risk (baseline vs context-adjusted), then optional cleanup flags (non-watertight, disconnected components, splines) separated by semicolons. Sentence 2: geometry-class-specific next ask (Mesh: units + STEP/native request; 2D Drawing: dimensions/tolerances/thickness; B-Rep/Surface/Parametric: tolerances and surface finish). When material is "Other / Unknown", sentence 2 appends an "also confirm material, heat treat condition, and any coatings/special processes" clause folded into the same sentence.
- MATERIAL_KB: Eight entries keyed by exact Material selectbox labels. Each has difficulty, machining_reality (1–2 sentences), cost_drivers (bullets), quote_implications (bullets). Used for display only: in Analyze (Material machining reality section under summary card) and in Learn — Materials (quick reference selectbox + same content). Material does not affect numeric scoring or banding.

---

## 2) What Changed Since Last Sync (bullets grouped by area)

**UI/UX**
- Sidebar navigation is now three options: Analyze, Learn — Formats, Learn — Materials. Learn — Formats is the former single "Learn" page (format dropdown + summary card only). Learn — Materials is a new page with four sections: how materials change cost/margin, material quick reference (MATERIAL_KB), rule-of-thumb takeaways, and what to ask customers. Why: dedicated Materials subpage for CNC economics without cluttering Analyze or Format learn. Constraint: Learn — Materials has no file upload; scroll position is reset on page change via injected JS targeting the main content section.
- Analyze page: Material selectbox added above the file uploader; summary card caption includes material (filename · extension · material); new "Material machining reality" section appears between summary card and Scoring, driven by selected material from MATERIAL_KB. Why: make material visible and provide CNC-specific machining reality per material. Constraint: material selection is independent of file; no format–material coupling.
- Scroll-to-top runs at the start of each of the three page branches so switching pages does not preserve the previous page’s scroll position. Why: Learn — Materials scroll was being inherited from other pages. Constraint: implementation relies on Streamlit’s main content container selector (section.main) in the DOM.

**Scoring**
- No change to numeric scoring logic in this sync. SCORE_BASELINES remains geometry_class-only (CNC machining). compute_scores has no workflow or material parameter. Contextual risk label still comes solely from score_to_band(risk_score, "risk"). Clamping and all metric-based adjustments are unchanged.

**Measurement**
- No change. Mesh parsing still uses trimesh with 1M-triangle cutoff for component_count. DXF still uses ezdxf (UTF-8 / Latin-1, modelspace, bbox extents). No STEP/IGES or native CAD geometry extraction.

**Knowledge (Formats)**
- FORMAT_KB and EXTENSION_TO_FORMAT unchanged. Learn page was renamed to Learn — Formats and left otherwise the same (dropdown built from FORMAT_KB keys plus alias labels, summary card without filename/contextual_risk). All copy remains CNC-machining focused (no additive/sheet-metal workflow language).

**Knowledge (Materials)**
- MATERIAL_KB populated with CNC-specific, concrete entries for all eight materials. Emphasis added on tool wear, cycle time, scrap risk, stainless work hardening, titanium low thermal conductivity and springback, Inconel heat and tool wear, 6061 forgiving vs 7075 stronger but less forgiving, 4140 vs 1018 machinability. Each entry has difficulty, machining_reality (plain-language 1–2 sentences), cost_drivers (3–5 bullets), quote_implications (2–4 bullets). Used only for display in Analyze (Material machining reality) and Learn — Materials (quick reference); no impact on numeric scoring.

**Triage Summary**
- build_triage_summary now takes a material argument. Sentence 1 always starts with "Material: {mat_label} —" (mat_label strips parentheticals from the selectbox label). Sentence 2, when material is "Other / Unknown", appends the clause "also confirm material, heat treat condition, and any coatings/special processes" into the same sentence (Mesh, 2D Drawing, or B-Rep/Surface/Parametric next-ask). Output remains exactly two sentences. Why: surface material in triage and prompt confirmation when material is unknown. Constraint: two-sentence guarantee is preserved; no third sentence.

---

## 3) Known Issues / TODO (max 12 bullets)

- [P2] Scroll-to-top uses a fixed DOM selector (section.main) to scroll the Streamlit main container; if Streamlit changes their layout or class names, the scroll reset may stop working or target the wrong element.
- [P2] No automated tests; refactors and new features risk regressions in scoring, triage wording, or render order.
- [P2] For meshes with more than 1,000,000 triangles, component_count is not computed (set to None) for performance; the user sees "(skipped for performance)" and the multi-component risk adjustment (+8) is never applied even when the mesh has multiple bodies.
- [P2] STEP, IGES, and native CAD (.sldprt, .sldasm, .prt, .catpart, .dwg) have no geometry extraction; risk and confidence come only from format baselines and no file-specific metrics.
- [P2] DXF extents-based adjustments use only the maximum of X and Y size (not Z) for the &gt;10,000 and &lt;1 heuristic; intentional for typical 2D DXFs but 3D DXF with large Z could be missed.
- [P2] Learn — Formats and Analyze use different widget contexts; the Material selectbox on Learn — Materials uses a unique key to avoid Streamlit key collisions with Analyze’s Material selectbox when switching pages.
- [P1] If a user uploads a file with an extension not in FORMAT_KB (and not an alias), the app shows "Unknown format" and does not run scoring, triage, or metrics; material selection is still visible but has no effect for that run.
- [P2] _material_triage_label strips only the first parenthetical (e.g. "(default)"); labels with multiple parentheticals would leave the rest; current MATERIALS list has at most one parenthetical per option so this is not triggered in practice.
- [P2] Mesh parse failures (e.g. corrupt or non-mesh file with .stl extension) show a st.warning and no mesh metrics; scoring still runs using format baseline only.
- [P2] DXF parse failures similarly show st.warning and no DXF metrics; scoring uses format baseline only.
- [P0] None identified that block core use (analyze → summary → material reality → score → triage → metrics).

---

## 4) Quick Verification Checklist (8–12 checkboxes)

- [ ] Contextual risk label matches the risk score band: for any uploaded file with a known format, the "Quote risk (context-adjusted)" value on the summary card equals the risk band label shown in the Scoring section (e.g. Low, Moderate, Elevated, High, Severe).
- [ ] Risk and confidence scores are always between 0 and 100 inclusive after all adjustments (mesh watertight, components, triangle count, DXF splines, DXF extents).
- [ ] Mesh with triangle_count &gt; 500,000 and ≤ 2,000,000 receives risk +5 and an explanation mentioning high triangle count; mesh with triangle_count &gt; 2,000,000 receives risk +10 and very high triangle count.
- [ ] Mesh with triangle_count &gt; 1,000,000 shows "(skipped for performance)" for Disconnected components and component_count is not used in compute_scores (no +8 for multiple components in that case).
- [ ] DXF with at least one SPLINE entity: risk +10, confidence −5, and st.warning "Splines detected — may require conversion to arcs/polylines for CAM" appears in the DXF metrics section.
- [ ] DXF with extents size max (X or Y) &gt; 10,000: risk +5 and explanation about very large extents / verify units; with 0 &lt; max &lt; 1: risk +5 and explanation about very small extents / verify units.
- [ ] Triage summary is exactly two sentences (one period after sentence 1, one after sentence 2; no extra sentences).
- [ ] When Material is "Other / Unknown", the second sentence of the triage summary includes the clause about confirming material, heat treat condition, and coatings/special processes; when Material is any other option, that clause is absent.
- [ ] Analyze render order with a known-format file: Summary card (with filename · extension · material) → Material machining reality → Scoring (bars + score drivers) → Triage summary (bold + copy/paste text area) → Extracted metrics (mesh or DXF as applicable).
- [ ] Learn — Formats: selecting an extension (including alias like .stp) shows the format summary card without filename or contextual risk; Learn — Materials shows the four sections and the material quick reference selectbox populated from MATERIALS/MATERIAL_KB.
- [ ] Changing the Material selectbox on Analyze updates the summary card caption and the Material machining reality section without re-uploading the file; triage summary text updates to include the new material label and, when switching to or from "Other / Unknown", the second-sentence clause toggles accordingly.
- [ ] Switching between Analyze, Learn — Formats, and Learn — Materials resets scroll position to the top of the new page (no carryover of scroll from the previous page).
