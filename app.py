import streamlit as st
import zipfile
import json
from io import BytesIO
from shapely.geometry import shape, mapping
from fastkml import kml
import zipfile as zf

st.title("KMZ → Optimized GeoJSON <1MB (Safe Version)")

uploaded_file = st.file_uploader("Upload KMZ/KML file", type=["kmz", "kml"])
max_size_mb = st.number_input("Max file size per chunk (MB)", min_value=0.1, value=1.0, step=0.1)

def extract_features_from_kmz_kml(file_bytes, filename):
    """
    Extract features from KMZ/KML and return as list of dicts {'geometry': shapely, 'properties': dict}
    """
    extracted_features = []
    if filename.lower().endswith(".kmz"):
        with zf.ZipFile(BytesIO(file_bytes)) as kmz_zip:
            kml_files = [f for f in kmz_zip.namelist() if f.endswith(".kml")]
            for kml_file in kml_files:
                kml_data = kmz_zip.read(kml_file)
                extracted_features.extend(extract_features_from_kml_bytes(kml_data))
    else:
        extracted_features.extend(extract_features_from_kml_bytes(file_bytes))
    return extracted_features

def extract_features_from_kml_bytes(kml_bytes):
    k = kml.KML()
    k.from_string(kml_bytes)
    features_list = []

    def recursive_extract(f, parent_props=None):
        props = dict(parent_props) if parent_props else {}
        if hasattr(f, 'name') and f.name:
            props['name'] = f.name
        if hasattr(f, 'description') and f.description:
            props['description'] = f.description
        if hasattr(f, 'geometry') and f.geometry:
            features_list.append({'geometry': f.geometry, 'properties': props})
        if hasattr(f, 'features'):
            for subf in f.features():
                recursive_extract(subf, props)

    for doc in k.features():
        recursive_extract(doc)
    return features_list

def simplify_and_round(geom, simplify_tol=0.0001, precision=5):
    if simplify_tol > 0:
        geom = geom.simplify(simplify_tol, preserve_topology=True)
    geom_dict = mapping(geom)
    def round_coords(coords):
        if isinstance(coords[0], (float,int)):
            return [round(coords[0], precision), round(coords[1], precision)]
        else:
            return [round_coords(c) for c in coords]
    geom_dict['coordinates'] = round_coords(geom_dict['coordinates'])
    return geom_dict

def split_geojson(features_list, max_size_bytes):
    chunks = []
    current_chunk = {"type":"FeatureCollection","features":[]}
    for feat in features_list:
        current_chunk['features'].append(feat)
        size = len(json.dumps(current_chunk).encode('utf-8'))
        if size > max_size_bytes:
            current_chunk['features'].pop()
            if current_chunk['features']:
                chunks.append(current_chunk)
            current_chunk = {"type":"FeatureCollection","features":[feat]}
    if current_chunk['features']:
        chunks.append(current_chunk)
    return chunks

if uploaded_file:
    try:
        raw_bytes = uploaded_file.read()
        st.info("Extracting features...")
        features_raw = extract_features_from_kmz_kml(raw_bytes, uploaded_file.name)

        st.info("Simplifying and rounding geometries...")
        features_processed = []
        for f in features_raw:
            geom = f['geometry']
            props = f['properties']
            simplified_geom = simplify_and_round(geom, simplify_tol=0.0001, precision=5)
            features_processed.append({"type":"Feature", "properties":props, "geometry":simplified_geom})

        max_size_bytes = int(max_size_mb * 1024 * 1024)
        st.info("Splitting into chunks...")
        chunks = split_geojson(features_processed, max_size_bytes)
        st.success(f"Converted into {len(chunks)} chunk(s).")

        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zf_obj:
            for i, chunk in enumerate(chunks, start=1):
                zf_obj.writestr(f"geojson_chunk_{i}.geojson", json.dumps(chunk, indent=2))

        st.download_button(
            label="Download all chunks as ZIP",
            data=zip_buffer.getvalue(),
            file_name="geojson_chunks.zip",
            mime="application/zip"
        )
    except Exception as e:
        st.error(f"Error: {e}")
