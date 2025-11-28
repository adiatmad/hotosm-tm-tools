import streamlit as st
import zipfile
import json
from io import BytesIO
from shapely.geometry import Point, LineString, Polygon, mapping
from shapely.ops import unary_union
from lxml import etree
import numpy as np

st.title("KMZ/KML → Super-Optimized GeoJSON <1MB")

uploaded_file = st.file_uploader("Upload KMZ/KML file", type=["kmz", "kml"])
max_size_mb = st.number_input("Max file size per chunk (MB)", min_value=0.1, value=1.0, step=0.1)
quantize_precision = st.number_input("Quantization step (decimal degrees)", min_value=1e-6, value=1e-5, step=1e-6)

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
    import zipfile
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
# Quantization + Union
# ----------------------------
def quantize_coords(geom, step):
    def round_coord(c):
        if isinstance(c[0], (float,int)):
            return [round(c[0]/step)*step, round(c[1]/step)*step]
        else:
            return [round_coord(sub) for sub in c]
    geom_dict = mapping(geom)
    geom_dict['coordinates'] = round_coord(geom_dict['coordinates'])
    return geom_dict

# ----------------------------
# Chunk by size
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
        file_bytes = uploaded_file.read()
        st.info("Extracting features...")
        features = extract_features_from_file(file_bytes, uploaded_file.name)

        st.info("Merging poligon/line clusters...")
        # Union geometries of same type to reduce duplicates
        geom_by_type = {}
        for f in features:
            t = f['geometry'].geom_type
            geom_by_type.setdefault(t, []).append(f['geometry'])

        merged_features = []
        for t, geoms in geom_by_type.items():
            union_geom = unary_union(geoms)
            if union_geom.geom_type == 'GeometryCollection':
                for g in union_geom.geoms:
                    merged_features.append(g)
            else:
                merged_features.append(union_geom)

        st.info("Quantizing coordinates...")
        processed_features = []
        for g in merged_features:
            q_geom = quantize_coords(g, quantize_precision)
            processed_features.append({"type":"Feature","properties":{},"geometry":q_geom})

        max_bytes = int(max_size_mb*1024*1024)
        st.info("Splitting into chunks...")
        chunks = split_geojson(processed_features, max_bytes)

        st.success(f"Done: {len(chunks)} chunk(s)")

        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer,"w") as zf:
            for i,c in enumerate(chunks,1):
                zf.writestr(f"geojson_chunk_{i}.geojson",json.dumps(c,indent=2))

        st.download_button(
            label="Download all chunks as ZIP",
            data=zip_buffer.getvalue(),
            file_name="geojson_chunks.zip",
            mime="application/zip"
        )

    except Exception as e:
        st.error(f"Error: {e}")
