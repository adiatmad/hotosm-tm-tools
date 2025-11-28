# app.py
import streamlit as st
import requests
import pandas as pd
import json

st.set_page_config(page_title="OSM Live QC Dashboard", layout="wide")

st.title("🗺️ OSM Live Quality Dashboard")
st.markdown(
    """
    Enter a HOT Tasking Manager Project ID or Campaign Hashtag. 
    This dashboard will fetch live mapping stats and quality checks (QC) from PostPass.
    """
)

# Input for Project/Campaign
project_input = st.text_input("HOT TM Project ID or Campaign", placeholder="16441 or #IndonesiaFlood2025")

# Function to fetch TM stats
def fetch_tm_stats(project_id):
    try:
        url = f"https://tasking-manager-tm4-production-api.hotosm.org/api/v2/projects/{project_id}/statistics/"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        st.error(f"Failed to fetch TM data: {e}")
        return None

# Function to run PostPass SQL
def run_postpass(sql):
    url = "https://postpass.geofabrik.de/api/0.2/interpreter"
    try:
        resp = requests.post(url, data={"data": sql}, timeout=20)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        st.error(f"Failed to fetch PostPass data: {e}")
        return None

# Function to build PostPass queries
def build_postpass_queries(campaign):
    return {
        "Invalid Buildings": f"""
            SELECT id, ST_IsValidReason(geom) AS reason 
            FROM postpass_polygon 
            WHERE tags ? 'building' 
              AND NOT ST_IsValid(geom) 
              AND changeset IN (
                SELECT id FROM postpass_changeset WHERE tags->>'comment' ILIKE '%{campaign}%'
              )
        """,
        "Overlapping Buildings": f"""
            SELECT a.id AS b1, b.id AS b2 
            FROM postpass_polygon a 
            JOIN postpass_polygon b 
              ON ST_Intersects(a.geom, b.geom) 
            WHERE a.tags ? 'building' AND b.tags ? 'building' AND a.id < b.id 
              AND a.changeset IN (
                SELECT id FROM postpass_changeset WHERE tags->>'comment' ILIKE '%{campaign}%'
              )
        """,
        "Small Buildings (<5m²)": f"""
            SELECT id, ST_Area(geom::geography) AS area_m2 
            FROM postpass_polygon 
            WHERE tags ? 'building' AND ST_Area(geom::geography)<5 
              AND changeset IN (
                SELECT id FROM postpass_changeset WHERE tags->>'comment' ILIKE '%{campaign}%'
              )
        """
    }

if project_input:
    st.subheader("🔹 HOT Tasking Manager Stats")
    tm_data = fetch_tm_stats(project_input)
    if tm_data:
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Mappers", tm_data.get("total_mappers", 0))
        col2.metric("Tasks Mapped", tm_data.get("tasks_mapped", 0))
        col3.metric("Total Validators", tm_data.get("tasks_validated", 0))

        st.markdown("**Top Mappers (first 50)**")
        mappers = tm_data.get("mappers", [])[:50]
        if mappers:
            df_mappers = pd.DataFrame([
                {"Username": u["username"], "Mapped Tasks": u["tasks_mapped"]} 
                for u in mappers
            ])
            st.dataframe(df_mappers)
        else:
            st.info("No mappers found.")

    st.subheader("🛠️ Live QC (PostPass)")
    queries = build_postpass_queries(project_input)
    for key, sql in queries.items():
        with st.expander(key):
            st.text("Fetching data...")
            result = run_postpass(sql)
            if result:
                if isinstance(result, list) and result:
                    st.dataframe(pd.json_normalize(result))
                else:
                    st.info("No issues found for this QC category.")
