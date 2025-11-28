import streamlit as st
import zipfile
import json
from io import BytesIO
from shapely.geometry import Point, Polygon, mapping, MultiPolygon
from shapely.ops import unary_union
from lxml import etree
import math

st.title("HOT TM Boundary Optimizer (<1MB)")

uploaded_file = st.file_uploader("Upload KMZ/KML file", type=["kmz", "kml"])
target_size_mb = st.number_input("Target max file size (MB)", min_value=0.1, value=1.0, step=0.1)
resample_points = st.number_input("Approx. number of points per polygon", min_value=10, value=50, step=10)

# ----------------------------
# KML Parsing
# ----------------------------
def parse_kml_placemarks(kml_content):
    ns = {'kml': 'http://www.opengis.net/kml/2.2'}
    root = etree.fromstring(kml_content)
    placemarks = root.xpath(".//kml:Placemark", namespaces=ns)
    features = []
    for pm in placemarks:
        geom = None
        point_el = pm.find(".//kml:Point/kml:coordinates", ns)
        line_el = pm.find(".//kml:LineString/kml:coordinates", ns)
        poly_el = pm.find(".//kml:Polygon/kml:outerBoundaryIs/kml:LinearRing/kml:coordinates", ns)

        if point_el is not None:
            coords = [float(c) for c in point_el.text.strip().split(",")[:2]]
            geom = Point(coords)
        elif line_el is not None:
            coords = [tuple(map(float, c.strip().split(",")[:2])) for c in line_el.text.strip().split()]
            geom = Polygon(coords)
        elif poly_el is not None:
            coords = [tuple(map(float, c.strip().split(",")[:2])) for c in poly_el.text.strip().split()]
            geom = Polygon(coords)

        if geom:
            features.append(geom)
    return features

def extract_features(file_bytes, filename):
    import zipfile
    all_features = []
    if filename.lower().endswith(".kmz"):
        with zipfile.ZipFile(BytesIO(file_bytes)) as kmz_zip:
            kml_files = [f for f in kmz_zip.namelist() if f.endswith(".kml")]
            for kml_file in kml_files:
                kml_content = kmz_zip.read(kml_file)
                all_features.extend(parse_kml_placemarks(kml_content))
    else:
        all_features.extend(parse_kml_placemarks(file_bytes))
    return all_features

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
# Main
# ----------------------------
if uploaded_file:
    try:
        file_bytes = uploaded_file.read()
        st.info("Extracting geometries...")
        features = extract_features(file_bytes, uploaded_file.name)

        st.info("Union all polygons...")
        unioned = unary_union(features)
        # ensure MultiPolygon for consistent processing
        if isinstance(unioned, Polygon):
            unioned = MultiPolygon([unioned])

        st.info("Resampling polygons...")
        resampled_features = []
        for poly in unioned.geoms:
            resampled = resample_polygon(poly, int(resample_points))
            resampled_features.append({
                "type": "Feature",
                "properties": {},
                "geometry": mapping(resampled)
            })

        max_bytes = int(target_size_mb * 1024 * 1024)
        # optional: split into chunks if still > max size
        chunks = []
        current_chunk = {"type":"FeatureCollection","features":[]}
        for f in resampled_features:
            current_chunk["features"].append(f)
            size = len(json.dumps(current_chunk).encode('utf-8'))
            if size > max_bytes:
                current_chunk["features"].pop()
                if current_chunk["features"]:
                    chunks.append(current_chunk)
                current_chunk = {"type":"FeatureCollection","features":[f]}
        if current_chunk["features"]:
            chunks.append(current_chunk)

        st.success(f"Done: {len(chunks)} chunk(s)")

        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer,"w") as zf:
            for i,c in enumerate(chunks,1):
                zf.writestr(f"geojson_boundary_{i}.geojson",json.dumps(c,indent=2))

        st.download_button(
            label="Download ZIP of optimized boundaries",
            data=zip_buffer.getvalue(),
            file_name="geojson_boundary.zip",
            mime="application/zip"
        )

    except Exception as e:
        st.error(f"Error: {e}")
