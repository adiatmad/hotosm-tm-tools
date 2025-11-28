import streamlit as st
import geopandas as gpd
import json
from shapely.geometry import mapping
from io import BytesIO
import zipfile
import math

st.title("Robust KMZ → GeoJSON Auto-Tuning < 1MB")

uploaded_file = st.file_uploader("Upload KMZ/KML file", type=["kmz", "kml"])
max_size_mb = st.number_input("Max file size per chunk (MB)", min_value=0.1, value=1.0, step=0.1)

def read_kmz(file):
    return gpd.read_file(file)

def simplify_geometry_adaptive(geom, target_size_bytes=500*1024, max_attempts=15):
    """Simplify geometry adaptively to reduce size."""
    tol = 0.0
    precision = 8
    for attempt in range(max_attempts):
        simplified = geom.simplify(tol, preserve_topology=True)
        geojson_geom = mapping(simplified)
        geojson_geom = round_coords(geojson_geom, precision)
        size = len(json.dumps(geojson_geom).encode("utf-8"))
        if size <= target_size_bytes:
            return geojson_geom
        tol = tol*1.5 + 0.0001
        precision = max(3, precision-1)
    return geojson_geom  # fallback

def round_coords(geom_dict, precision=5):
    def round_point(c):
        return [round(c[0], precision), round(c[1], precision)]
    t = geom_dict["type"]
    if t == "Point":
        geom_dict["coordinates"] = round_point(geom_dict["coordinates"])
    elif t in ["LineString", "MultiPoint"]:
        geom_dict["coordinates"] = [round_point(pt) for pt in geom_dict["coordinates"]]
    elif t == "Polygon":
        geom_dict["coordinates"] = [[round_point(pt) for pt in ring] for ring in geom_dict["coordinates"]]
    elif t == "MultiLineString":
        geom_dict["coordinates"] = [[round_point(pt) for pt in line] for line in geom_dict["coordinates"]]
    elif t == "MultiPolygon":
        geom_dict["coordinates"] = [[[round_point(pt) for pt in ring] for ring in poly] for poly in geom_dict["coordinates"]]
    return geom_dict

def gdf_to_geojson_chunks(gdf, max_size_bytes):
    features = []
    st.info("Processing features and simplifying geometries...")
    progress_bar = st.progress(0)
    total = len(gdf)
    for idx, row in enumerate(gdf.itertuples()):
        geom = row.geometry
        geoms = geom.geoms if geom.geom_type.startswith("Multi") else [geom]
        for part in geoms:
            simplified_geom = simplify_geometry_adaptive(part, target_size_bytes=max_size_bytes//5)
            feature = {
                "type": "Feature",
                "properties": {k: getattr(row, k) for k in gdf.columns if k != "geometry"},
                "geometry": simplified_geom
            }
            features.append(feature)
        progress_bar.progress((idx+1)/total)
    
    # Split into chunks
    chunks = []
    current_chunk = {"type": "FeatureCollection", "features": []}
    for feature in features:
        current_chunk["features"].append(feature)
        size = len(json.dumps(current_chunk).encode("utf-8"))
        if size > max_size_bytes:
            current_chunk["features"].pop()
            if current_chunk["features"]:
                chunks.append(current_chunk)
            current_chunk = {"type": "FeatureCollection", "features": [feature]}
    if current_chunk["features"]:
        chunks.append(current_chunk)
    return chunks

if uploaded_file:
    try:
        gdf = read_kmz(uploaded_file)
        max_size_bytes = int(max_size_mb * 1024 * 1024)
        chunks = gdf_to_geojson_chunks(gdf, max_size_bytes)
        st.success(f"File converted into {len(chunks)} chunk(s) with robust auto-tuning.")

        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            for i, chunk in enumerate(chunks, start=1):
                chunk_bytes = json.dumps(chunk, indent=2).encode("utf-8")
                zf.writestr(f"geojson_chunk_{i}.geojson", chunk_bytes)
        st.download_button(
            label="Download all chunks as ZIP",
            data=zip_buffer.getvalue(),
            file_name="geojson_chunks.zip",
            mime="application/zip"
        )

    except Exception as e:
        st.error(f"Error: {e}")
