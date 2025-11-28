import streamlit as st
import json
from shapely.geometry import shape, mapping, Polygon, MultiPolygon
from shapely.ops import unary_union
from io import BytesIO
import zipfile
import datetime
import random

st.title("HOT TM GeoJSON Optimizer (<1MB)")

uploaded_file = st.file_uploader("Upload large GeoJSON", type=["geojson"])
target_size_mb = st.number_input("Target max file size (MB)", min_value=0.1, value=1.0, step=0.1)
resample_points = st.number_input("Approx points per polygon", min_value=10, value=100, step=10)

# Fun messages for humanitarian mapping
fun_messages = [
    "Tracing roads for rescue operations...",
    "Mapping shelters for those in need...",
    "Tagging rivers to avoid floods...",
    "Drawing boundaries for life-saving tasks...",
    "Helping communities one polygon at a time...",
    "Mapping emergency response zones..."
]

def resample_polygon(polygon, num_points):
    coords = list(polygon.exterior.coords)
    if len(coords) <= num_points:
        return polygon
    step = max(1, len(coords) // num_points)
    new_coords = coords[::step]
    if new_coords[0] != new_coords[-1]:
        new_coords.append(new_coords[0])
    return Polygon(new_coords)

if uploaded_file:
    try:
        geojson_data = json.load(uploaded_file)
        features = geojson_data.get("features", [])

        st.info(random.choice(fun_messages))
        st.info("Converting features to Shapely geometries...")
        geoms = [shape(f["geometry"]) for f in features]

        st.info(random.choice(fun_messages))
        st.info("Union all polygons to reduce feature count...")
        polygons = [g for g in geoms if isinstance(g, (Polygon, MultiPolygon))]
        unioned = unary_union(polygons)
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

        # Singlepart GeoJSON (all polygons in one file)
        final_geojson = {"type":"FeatureCollection", "features": processed_features}

        # Prepare ZIP with input filename + timestamp
        timestamp = datetime.datetime.now().strftime("%Y%m%dT%H%M")
        input_name = uploaded_file.name.rsplit(".",1)[0]
        zip_filename = f"{input_name}_{timestamp}.zip"

        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            zf.writestr(f"{input_name}_{timestamp}.geojson", json.dumps(final_geojson, separators=(',',':')))

        st.success("Processing complete!")
        st.download_button(
            label="Download Optimized GeoJSON ZIP",
            data=zip_buffer.getvalue(),
            file_name=zip_filename,
            mime="application/zip"
        )

    except Exception as e:
        st.error(f"Error: {e}")
