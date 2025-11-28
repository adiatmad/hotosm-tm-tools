import streamlit as st
import json
from shapely.geometry import shape, mapping, Polygon, MultiPolygon
from shapely.ops import unary_union
from io import BytesIO
import zipfile
import datetime
import random

st.title("GeoJSON Optimizer for HOT Tasking Manager (<1MB)")

uploaded_file = st.file_uploader("Upload large GeoJSON", type=["geojson"])
target_size_mb = st.number_input("Target max file size per chunk (MB)", min_value=0.1, value=1.0, step=0.1)
resample_points = st.number_input("Approx. points per polygon", min_value=10, value=100, step=10)

# Fun messages while processing
fun_messages = [
    "Tracing roads for rescue operations...",
    "Mapping shelters for those in need...",
    "Tagging rivers to avoid floods...",
    "Drawing boundaries for life-saving tasks...",
    "Helping communities one polygon at a time...",
    "Mapping emergency response zones..."
]

# ----------------------------
# Resample / Reduce Points
# ----------------------------
def resample_polygon(polygon, num_points):
    coords = list(polygon.exterior.coords)
    if len(coords) <= num_points:
        return polygon
    step = max(1, len(coords) // num_points)
    new_coords = coords[::step]
    if new_coords[0] != new_coords[-1]:
        new_coords.append(new_coords[0])
    return Polygon(new_coords)

# ----------------------------
# Split GeoJSON by size
# ----------------------------
def split_geojson(features_list, max_size_bytes):
    chunks = []
    current_chunk = {"type":"FeatureCollection","features":[]}
    for f in features_list:
        current_chunk['features'].append(f)
        size = len(json.dumps(current_chunk).encode('utf-8'))
        if size > max_size_bytes:
            current_chunk['features'].pop()
            if current_chunk['features']:
                chunks.append(current_chunk)
            current_chunk = {"type":"FeatureCollection","features":[f]}
    if current_chunk['features']:
        chunks.append(current_chunk)
    return chunks

# ----------------------------
# Main
# ----------------------------
if uploaded_file:
    try:
        geojson_data = json.load(uploaded_file)
        features = geojson_data.get("features", [])

        st.info(random.choice(fun_messages))
        st.info("Converting to Shapely geometries...")
        geoms = []
        for f in features:
            geom = shape(f["geometry"])
            geoms.append(geom)

        st.info(random.choice(fun_messages))
        st.info("Union all polygons to reduce feature count...")
        unioned = unary_union(geoms)
        if isinstance(unioned, Polygon):
            unioned = MultiPolygon([unioned])

        st.info(random.choice(fun_messages))
        st.info("Resampling polygons to reduce points...")
        processed_features = []
        for poly in unioned.geoms:
            resampled = resample_polygon(poly, int(resample_points))
            processed_features.append({
                "type":"Feature",
                "properties":{},
                "geometry":mapping(resampled)
            })

        st.info(random.choice(fun_messages))
        max_bytes = int(target_size_mb*1024*1024)
        chunks = split_geojson(processed_features, max_bytes)

        timestamp = datetime.datetime.now().strftime("%Y%m%dT%H%M")
        input_name = uploaded_file.name.rsplit(".",1)[0]
        zip_filename = f"{input_name}_{timestamp}.zip"

        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer,"w") as zf:
            for i,c in enumerate(chunks,1):
                zf.writestr(f"{input_name}_{i}_{timestamp}.geojson", json.dumps(c, separators=(',',':')))

        st.success(f"Done! {len(chunks)} chunk(s) ready for HOT TM")
        st.download_button(
            label="Download ZIP of optimized GeoJSON",
            data=zip_buffer.getvalue(),
            file_name=zip_filename,
            mime="application/zip"
        )

    except Exception as e:
        st.error(f"Error: {e}")
