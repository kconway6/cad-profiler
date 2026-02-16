import streamlit as st
import os

st.set_page_config(page_title="CAD File Profiler", layout="centered")

st.title("CAD File Profiler")
st.write("Upload a CAD file to analyze its format and metadata.")

uploaded_file = st.file_uploader("Upload CAD file")

if uploaded_file:
    filename = uploaded_file.name
    extension = os.path.splitext(filename)[1].lower()

    st.subheader("File Info")
    st.write(f"**File Name:** {filename}")
    st.write(f"**Extension:** {extension}")

    format_map = {
        ".step": "Neutral Solid (STEP)",
        ".stp": "Neutral Solid (STEP)",
        ".iges": "Neutral Surface/Solid (IGES)",
        ".igs": "Neutral Surface/Solid (IGES)",
        ".stl": "Mesh (STL)",
        ".obj": "Mesh (OBJ)",
        ".sldprt": "SolidWorks Native",
        ".sldasm": "SolidWorks Assembly",
        ".prt": "NX/Creo Native",
        ".catpart": "CATIA Native",
        ".dwg": "AutoCAD Native (2D/3D)",
        ".dxf": "Drawing Exchange Format (2D)"
    }

    category = format_map.get(extension, "Unknown Format")

    st.subheader("Format Classification")
    st.write(category)
