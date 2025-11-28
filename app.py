import streamlit as st
import zipfile
import json
from io import BytesIO
from zipfile import ZipFile
from kml2geojson import convert
from shapely.geometry import shape, mapping
from shapely.ops import unary_union

st.title("KMZ → Optimized GeoJSON <1MB (No Geopandas)")

uploaded_file = st.file_uploader("Upload KMZ/KML file", type=["kmz", "kml"])
max_size_mb = st.number_input("Max file size per chunk (MB)", min_value=0.1, value=1.0, step=0.1)

def simplify_and_round(geom_dict, simplify_tol=0.0001, precision=5):
    geom = shape(geom_dict)
    if simplify_tol > 0:
        geom = geom.simplify(simplify_tol, preserve_topology=True)
    geom_dict = mapping(geom)
    # Round coordinates
    def round_coords(coords):
        if isinstance(coords[0], (float,int)):
            return [round(coords[0], precision), round(coords[1], precision)]
        else:
            return [round_coords(c) for c in coords]
    geom_dict['coordinates'] = round_coords(geom_dict['coordinates'])
    return geom_dict

def split_geojson(geojson_data, max_size_bytes):
    features = geojson_data['features']
    chunks = []
    current_chunk = {"type":"FeatureCollection","features":[]}
    for feature in features:
        current_chunk['features'].append(feature)
        size = len(json.dumps(current_chunk).encode('utf-8'))
        if size > max_size_bytes:
            current_chunk['features'].pop()
            if current_chunk['features']:
                chunks.append(current_chunk)
            current_chunk = {"type":"FeatureCollection","features":[feature]}
    if current_chunk['features']:
        chunks.append(current_chunk)
    return chunks

if uploaded_file:
    try:
        # Convert KMZ/KML to GeoJSON (in memory)
        with ZipFile(uploaded_file) if uploaded_file.name.endswith(".kmz") else None as kmz_zip:
            convert.convert(uploaded_file.name if not kmz_zip else kmz_zip, "./tmp_geojson", format='geojson')
        
        # Read all GeoJSON files from tmp_geojson
        import glob, os
        geojson_files = glob.glob("./tmp_geojson/*.geojson")
        features = []
        for f in geojson_files:
            with open(f,'r', encoding='utf-8') as gf:
                data = json.load(gf)
                for feat in data['features']:
                    # Simplify & round
                    feat['geometry'] = simplify_and_round(feat['geometry'], simplify_tol=0.0001, precision=5)
                    features.append(feat)

        geojson_data = {"type":"FeatureCollection","features":features}

        max_size_bytes = int(max_size_mb * 1024 * 1024)
        chunks = split_geojson(geojson_data, max_size_bytes)
        st.success(f"File converted into {len(chunks)} chunk(s).")

        # ZIP download
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            for i, chunk in enumerate(chunks, start=1):
                zf.writestr(f"geojson_chunk_{i}.geojson", json.dumps(chunk, indent=2))
        st.download_button(
            label="Download all chunks as ZIP",
            data=zip_buffer.getvalue(),
            file_name="geojson_chunks.zip",
            mime="application/zip"
        )

    except Exception as e:
        st.error(f"Error: {e}")
