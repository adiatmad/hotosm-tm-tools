import streamlit as st
import zipfile
import json
from io import BytesIO
from shapely.geometry import Point, LineString, Polygon, mapping, box
from shapely.ops import split, unary_union
from lxml import etree
import math

st.title("KMZ/KML → Optimized GeoJSON <1MB (Hybrid Tiling + Auto-Tuning)")

uploaded_file = st.file_uploader("Upload KMZ/KML file", type=["kmz", "kml"])
max_size_mb = st.number_input("Max file size per chunk (MB)", min_value=0.1, value=1.0, step=0.1)
tile_size_deg = st.number_input("Tile size in degrees (for large areas)", min_value=0.01, value=0.5, step=0.1)

# ----------------------------
# KML Parsing
# ----------------------------
def parse_kml_placemarks(kml_content):
    ns = {'kml': 'http://www.opengis.net/kml/2.2'}
    root = etree.fromstring(kml_content)
    placemarks = root.xpath(".//kml:Placemark", namespaces=ns)
    features = []
    for pm in placemarks:
        props = {}
        name_el = pm.find("kml:name", ns)
        if name_el is not None:
            props['name'] = name_el.text
        desc_el = pm.find("kml:description", ns)
        if desc_el is not None:
            props['description'] = desc_el.text

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
            features.append({'geometry': geom, 'properties': props})
    return features

def extract_features_from_file(file_bytes, filename):
    all_features = []
    if filename.lower().endswith(".kmz"):
        with zipfile.ZipFile(BytesIO(file_bytes)) as kmz_zip:
            kml_files_in_kmz = [f for f in kmz_zip.namelist() if f.endswith(".kml")]
            for kml_file_name in kml_files_in_kmz:
                kml_content = kmz_zip.read(kml_file_name)
                all_features.extend(parse_kml_placemarks(kml_content))
    else:
        all_features.extend(parse_kml_placemarks(file_bytes))
    return all_features

# ----------------------------
# Simplify + Round
# ----------------------------
def simplify_and_round(shapely_geom, simplify_tol=0.0, precision=5):
    if simplify_tol > 0:
        shapely_geom = shapely_geom.simplify(simplify_tol, preserve_topology=True)
    geom_dict = mapping(shapely_geom)
    def round_coords(coords):
        if isinstance(coords[0], (float, int)):
            return [round(coords[0], precision), round(coords[1], precision)]
        else:
            return [round_coords(c) for c in coords]
    geom_dict['coordinates'] = round_coords(geom_dict['coordinates'])
    return geom_dict

# ----------------------------
# Tiling
# ----------------------------
def tile_geometry(geom, tile_size_deg):
    minx, miny, maxx, maxy = geom.bounds
    tiles = []
    x_count = math.ceil((maxx - minx) / tile_size_deg)
    y_count = math.ceil((maxy - miny) / tile_size_deg)
    for i in range(x_count):
        for j in range(y_count):
            tile_box = box(minx + i*tile_size_deg, miny + j*tile_size_deg,
                           min(minx + (i+1)*tile_size_deg, maxx),
                           min(miny + (j+1)*tile_size_deg, maxy))
            intersection = geom.intersection(tile_box)
            if not intersection.is_empty:
                tiles.append(intersection)
    return tiles

# ----------------------------
# Split GeoJSON by size
# ----------------------------
def split_geojson(features_list, max_size_bytes):
    chunks = []
    current_chunk = {"type": "FeatureCollection", "features": []}
    for feat in features_list:
        current_chunk["features"].append(feat)
        size = len(json.dumps(current_chunk).encode('utf-8'))
        if size > max_size_bytes:
            current_chunk["features"].pop()
            if current_chunk["features"]:
                chunks.append(current_chunk)
            current_chunk = {"type": "FeatureCollection", "features": [feat]}
    if current_chunk["features"]:
        chunks.append(current_chunk)
    return chunks

# ----------------------------
# Main
# ----------------------------
if uploaded_file:
    try:
        file_bytes = uploaded_file.read()
        st.info("Extracting features...")
        features = extract_features_from_file(file_bytes, uploaded_file.name)

        st.info("Tiling geometries...")
        tiled_features = []
        for f in features:
            geom = f['geometry']
            props = f['properties']
            tiles = tile_geometry(geom, tile_size_deg)
            for t in tiles:
                tiled_features.append({'geometry': t, 'properties': props})

        st.info("Auto-tuning simplify + rounding for target size...")
        max_bytes = int(max_size_mb * 1024 * 1024)
        simplify_tol = 0.0
        precision = 6
        while True:
            processed_features = []
            for f in tiled_features:
                geom = f['geometry']
                props = f['properties']
                simplified_geom = simplify_and_round(geom, simplify_tol=simplify_tol, precision=precision)
                processed_features.append({"type": "Feature", "properties": props, "geometry": simplified_geom})
            chunks = split_geojson(processed_features, max_bytes)
            if len(chunks) <= math.ceil(len(processed_features) * 100000 / max_bytes):
                break
            simplify_tol += 0.00005
            if simplify_tol > 0.001:
                precision -= 1
                simplify_tol = 0.0001
            if precision < 3:
                break

        st.success(f"Conversion done: {len(chunks)} chunk(s).")

        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zip_file:
            for i, chunk in enumerate(chunks, start=1):
                zip_file.writestr(f"geojson_chunk_{i}.geojson", json.dumps(chunk, indent=2))

        st.download_button(
            label="Download all chunks as ZIP",
            data=zip_buffer.getvalue(),
            file_name="geojson_chunks.zip",
            mime="application/zip"
        )

    except Exception as e:
        st.error(f"Error: {e}")
