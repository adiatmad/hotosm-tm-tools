import streamlit as st
import zipfile
import json
from io import BytesIO
from shapely.geometry import shape, mapping
from fastkml import kml
import zipfile as zf

st.title("KMZ → Optimized GeoJSON <1MB (Safe Final Version)")

uploaded_file = st.file_uploader("Upload KMZ/KML file", type=["kmz", "kml"])
max_size_mb = st.number_input("Max file size per chunk (MB)", min_value=0.1, value=1.0, step=0.1)

def extract_features_from_kmz_kml(file_bytes, filename):
    """
    Extract features from KMZ/KML, return list of dicts {'geometry': shapely, 'properties': dict}
    """
    all_features = []

    if filename.lower().endswith(".kmz"):
        with zf.ZipFile(BytesIO(file_bytes)) as kmz_zip:
            kml_files_in_kmz = [f for f in kmz_zip.namelist() if f.endswith(".kml")]
            for kml_file_name in kml_files_in_kmz:
                kml_bytes = kmz_zip.read(kml_file_name)
                all_features.extend(extract_features_from_kml_bytes(kml_bytes))
    else:  # KML file
        all_features.extend(extract_features_from_kml_bytes(file_bytes))
    return all_features

def extract_features_from_kml_bytes(kml_bytes):
    kml_document = kml.KML()
    kml_document.from_string(kml_bytes)
    feature_dict_list = []

    def recursive_extract(feature_obj, parent_props=None):
        props = dict(parent_props) if parent_props else {}
        if hasattr(feature_obj, 'name') and feature_obj.name:
            props['name'] = feature_obj.name
        if hasattr(feature_obj, 'description') and feature_obj.description:
            props['description'] = feature_obj.description
        if hasattr(feature_obj, 'geometry') and feature_obj.geometry:
            feature_dict_list.append({
                "geometry": feature_obj.geometry,
                "properties": props
            })
        if hasattr(feature_obj, 'features'):
            for subf in feature_obj.features():
                recursive_extract(subf, props)

    for doc_obj in kml_document.features():
        recursive_extract(doc_obj)
    return feature_dict_list

def simplify_and_round(shapely_geom, simplify_tol=0.0001, precision=5):
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

def split_geojson(features_list, max_size_bytes):
    chunks = []
    current_chunk = {"type": "FeatureCollection", "features": []}
    for feature in features_list:
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
        file_bytes = uploaded_file.read()
        st.info("Extracting features from KMZ/KML...")
        extracted_features = extract_features_from_kmz_kml(file_bytes, uploaded_file.name)

        st.info("Simplifying and rounding geometries...")
        processed_features = []
        for f in extracted_features:
            geom = f['geometry']
            props = f['properties']
            simplified_geom = simplify_and_round(geom, simplify_tol=0.0001, precision=5)
            processed_features.append({
                "type": "Feature",
                "properties": props,
                "geometry": simplified_geom
            })

        max_bytes = int(max_size_mb * 1024 * 1024)
        st.info("Splitting features into chunks...")
        geojson_chunks = split_geojson(processed_features, max_bytes)
        st.success(f"Conversion done: {len(geojson_chunks)} chunk(s).")

        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zip_file:
            for i, chunk in enumerate(geojson_chunks, start=1):
                zip_file.writestr(f"geojson_chunk_{i}.geojson", json.dumps(chunk, indent=2))

        st.download_button(
            label="Download all chunks as ZIP",
            data=zip_buffer.getvalue(),
            file_name="geojson_chunks.zip",
            mime="application/zip"
        )

    except Exception as e:
        st.error(f"Error: {e}")
