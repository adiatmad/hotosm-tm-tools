import streamlit as st
import json
from shapely.geometry import shape, mapping, Polygon, MultiPolygon, box
from shapely.ops import unary_union, transform
from shapely import simplify
import pyproj
from functools import partial
from io import BytesIO
import zipfile
import datetime
import random

# ------------------------------------------------------
# Streamlit UI
# ------------------------------------------------------

st.title("⚡ HOT Tasking Manager GeoJSON Optimizer")
st.caption("Auto-split by area, auto-reduce <1MB, union, resample, singlepart — fully HOT TM ready")

uploaded_file = st.file_uploader("Upload large GeoJSON", type=["geojson"])

target_size_mb = st.number_input("Target max GeoJSON size (MB)", min_value=0.1, value=1.0, step=0.1)
max_area_km2 = st.number_input("Max polygon area (km²)", min_value=100.0, value=5000.0, step=100.0)
base_points = st.number_input("Approx points per polygon", min_value=20, value=200, step=20)

fun_messages = [
    "🛰️ Tracing roads for rapid response...",
    "🚑 Mapping emergency access routes...",
    "🌧️ Outlining flood impact zones...",
    "🏥 Supporting humanitarian teams...",
    "🗺️ Splitting large areas into manageable tasks...",
    "💾 Compressing data without losing crucial detail..."
]

# ------------------------------------------------------
# Utility: Reprojection for accurate area & cutting
# ------------------------------------------------------

project_to_m = partial(
    pyproj.transform,
    pyproj.Proj(init="epsg:4326"),
    pyproj.Proj(init="epsg:3857")
)

project_to_deg = partial(
    pyproj.transform,
    pyproj.Proj(init="epsg:3857"),
    pyproj.Proj(init="epsg:4326")
)

# ------------------------------------------------------
# Split polygon by grid until not exceeding max area
# ------------------------------------------------------

def split_by_area(poly, max_area_m2):
    poly_m = transform(project_to_m, poly)
    if poly_m.area <= max_area_m2:
        return [poly]

    # Ideal grid cell size
    cell_side = (max_area_m2) ** 0.5  # meters
    minx, miny, maxx, maxy = poly_m.bounds

    pieces = []
    x = minx
    while x < maxx:
        y = miny
        while y < maxy:
            cell = box(x, y, x + cell_side, y + cell_side)
            inter = poly_m.intersection(cell)
            if not inter.is_empty:
                # Convert back to degrees
                inter_deg = transform(project_to_deg, inter)
                if isinstance(inter_deg, Polygon):
                    pieces.append(inter_deg)
                else:
                    pieces.extend(inter_deg.geoms)
            y += cell_side
        x += cell_side

    return pieces

# ------------------------------------------------------
# Adaptive size reduction loop
# ------------------------------------------------------

def geojson_size_bytes(obj):
    return len(json.dumps(obj, separators=(",", ":")).encode("utf-8"))

def adaptive_reduce(features, target_bytes):
    """Auto-split further + simplify if > target size."""
    step_simplify = 0.0005  # start gentle
    split_factor = 1.5      # grid becomes 1.5x smaller if needed

    attempt = 0
    while True:
        attempt += 1

        out = {"type": "FeatureCollection", "features": features}
        size_now = geojson_size_bytes(out)

        if size_now <= target_bytes:
            return features

        st.warning(f"⚠️ GeoJSON still too large ({size_now/1e6:.2f} MB). Auto-reducing... [Attempt {attempt}]")

        new_features = []
        for f in features:
            geom = shape(f["geometry"])
            # Step 1 — simplify geometry
            geom_simplified = geom.simplify(step_simplify, preserve_topology=True)

            # Step 2 — further area split
            max_area_m2 = (max_area_km2 * 1_000_000) / split_factor
            chunks = split_by_area(geom_simplified, max_area_m2)

            for c in chunks:
                new_features.append({
                    "type": "Feature",
                    "properties": {},
                    "geometry": mapping(c)
                })

        features = new_features
        step_simplify *= 1.3
        split_factor *= 1.4


# ------------------------------------------------------
# MAIN PROCESS
# ------------------------------------------------------
if uploaded_file:
    try:
        st.info(random.choice(fun_messages))
        data = json.load(uploaded_file)
        features = data.get("features", [])

        st.info(random.choice(fun_messages))
        geoms = [shape(f["geometry"]) for f in features]
        polygons = [g for g in geoms if isinstance(g, (Polygon, MultiPolygon))]

        st.info("🔄 Unioning all polygons...")
        unioned = unary_union(polygons)
        if isinstance(unioned, Polygon):
            unioned = MultiPolygon([unioned])

        # ------------------------------------------------------
        # Step: Split by area 1st pass
        # ------------------------------------------------------
        st.info("📏 Splitting polygons > max area...")
        all_split = []
        max_area_m2 = max_area_km2 * 1_000_000
        for p in unioned.geoms:
            all_split.extend(split_by_area(p, max_area_m2))

        # ------------------------------------------------------
        # Convert to Feature list
        # ------------------------------------------------------
        features_out = [{
            "type": "Feature",
            "properties": {},
            "geometry": mapping(poly)
        } for poly in all_split]

        # ------------------------------------------------------
        # Adaptive size reduction loop
        # ------------------------------------------------------
        st.info("💾 Ensuring file smaller than target size...")
        target_bytes = int(target_size_mb * 1_000_000)
        features_final = adaptive_reduce(features_out, target_bytes)

        final_geojson = {
            "type": "FeatureCollection",
            "features": features_final
        }

        timestamp = datetime.datetime.now().strftime("%Y%m%dT%H%M")
        input_name = uploaded_file.name.rsplit(".", 1)[0]
        zip_name = f"{input_name}_{timestamp}_HOTTM_ready.zip"

        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            zf.writestr(f"{input_name}_{timestamp}.geojson",
                        json.dumps(final_geojson, separators=(",", ":")))

        st.success("🎉 Processing complete! Fully HOT Tasking Manager ready.")
        st.download_button(
            "Download Optimized GeoJSON (ZIP)",
            data=buffer.getvalue(),
            file_name=zip_name,
            mime="application/zip"
        )

    except Exception as e:
        st.error(f"❌ Error: {e}")
