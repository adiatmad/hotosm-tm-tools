import streamlit as st
import zipfile
import json
from io import BytesIO
from shapely.geometry import shape, mapping, Polygon, MultiPolygon, Point, LineString
from shapely.ops import unary_union
from lxml import etree
import datetime
import random
import zipfile

st.title("HOT TM KMZ → Optimized GeoJSON (<1MB)")

uploaded_file = st.file_uploader("Upload KMZ file", type=["kmz"])
target_size_mb = st.number_input("Target max file size per chunk (MB)", min_value=0.1, value=1.0, step=0.1)
max_initial_points = st.number_input("Approx points per polygon start", min_value=10, value=200, step=10)

# Fun messages while processing
fun_messages = [
    "Tracing roads for rescue operations...",
    "Mapping shelters for those in need...",
    "Tagging rivers to avoid floods...",
    "Drawing boundaries for life-saving tasks...",
    "Helping communities one polygon at a time...",
    "Mapping emergency response zones..."
]

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
            geom = LineString(coords)
        elif poly_el is not None:
            coords = [tuple(map(float, c.strip().split(",")[:2])) for c in poly_el.text.strip().split()]
            geom = Polygon(coords)

        if geom:
            features.append(geom)
    return features

def extract_features_from_kmz(file_bytes):
    import zipfile
    features = []
    with zipfile.ZipFile(BytesIO(file_bytes)) as kmz_zip:
        kml_files = [f for f in kmz_zip.namelist() if f.endswith(".kml")]
        for kml_file in kml_files:
            kml_content = kmz_zip.read(kml_file)
            features.extend(parse_kml_placemarks(kml_content))
    return features

def resample_polygon(polygon, num_points):
    coords = list(polygon.exterior.coords)
    if len(coords) <= num_points:
        return polygon
    step = max(1, len(coords) // num_points)
    new_coords = coords[::step]
    if new_coords[0] != new_coords[-1]:
        new_coords.append(new_coords[0])
    return Polygon(new_coords)

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

if uploaded_file:
    try:
        st.info(random.choice(fun_messages))
        file_bytes = uploaded_file.read()
        st.info("Extracting features from KMZ...")
        features = extract_features_from_kmz(file_bytes)

        st.info(random.choice(fun_messages))
        st.info("Union all polygons to simplify boundaries...")
        geoms = [f for f in features if isinstance(f, (Polygon, MultiPolygon))]
        unioned = unary_union(geoms)
        if isinstance(unioned, Polygon):
            unioned = MultiPolygon([unioned])

        st.info(random.choice(fun_messages))
        # Adaptive resampling
        processed_features = []
        max_bytes = int(target_size_mb * 1024 * 1024)
        points = int(max_initial_points)
        iteration = 0
        while True:
            processed_features = []
            for poly in unioned.geoms:
                resampled = resample_polygon(poly, points)
                processed_features.append({
                    "type":"Feature",
                    "properties":{},
                    "geometry":mapping(resampled)
                })
            test_geojson = {"type":"FeatureCollection","features":processed_features}
            size_bytes = len(json.dumps(test_geojson).encode('utf-8'))
            if size_bytes <= max_bytes or points <= 10:
                break
            points = max(10, points - 10)  # reduce points iteratively
            iteration += 1
            st.info(random.choice(fun_messages))

        st.success(f"Optimized in {iteration+1} iterations, final approx points per polygon: {points}")

        chunks = split_geojson(processed_features, max_bytes)
        timestamp = datetime.datetime.now().strftime("%Y%m%dT%H%M")
        input_name = uploaded_file.name.rsplit(".",1)[0]
        zip_filename = f"{input_name}_{timestamp}.zip"

        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer,"w") as zf:
            for i, c in enumerate(chunks,1):
                zf.writestr(f"{input_name}_{i}_{timestamp}.geojson", json.dumps(c, separators=(',',':')))

        st.download_button(
            label="Download Optimized GeoJSON ZIP",
            data=zip_buffer.getvalue(),
            file_name=zip_filename,
            mime="application/zip"
        )

    except Exception as e:
        st.error(f"Error: {e}")
