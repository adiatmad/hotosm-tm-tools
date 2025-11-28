import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json

# Konfigurasi
POSTPASS_URL = "https://postpass.geofabrik.de/api/0.2/interpreter"
st.set_page_config(page_title="HOT Tasking Manager Monitor", layout="wide")

st.title("🚨 HOT Tasking Manager - Real-time Quality Monitor")
st.markdown("Monitoring kualitas data OSM untuk respons bencana")

# Sidebar untuk parameter
st.sidebar.header("Parameter Monitoring")
bbox = st.sidebar.text_input("Bounding Box (min_lon,min_lat,max_lon,max_lat)", "8.34,48.97,8.46,49.03")
hours_back = st.sidebar.slider("Jam ke belakang untuk monitoring", 1, 72, 24)

# Parse BBOX
try:
    bbox_parts = [float(x.strip()) for x in bbox.split(",")]
    bbox_wkt = f"ST_MakeEnvelope({bbox_parts[0]}, {bbox_parts[1]}, {bbox_parts[2]}, {bbox_parts[3]}, 4326)"
except:
    st.error("Format BBOX tidak valid! Gunakan: min_lon,min_lat,max_lon,max_lat")
    st.stop()

def run_postpass_query(query, return_geojson=True):
    """Eksekusi query ke Postpass API"""
    params = {
        'data': query
    }
    if not return_geojson:
        params['options[geojson]'] = 'false'
    
    try:
        response = requests.post(POSTPASS_URL, data=params, timeout=60)
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"Error API: {response.status_code}")
            return None
    except Exception as e:
        st.error(f"Koneksi gagal: {str(e)}")
        return None

# Tab untuk berbagai fitur monitoring
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Dashboard", 
    "👥 Mapper Activity", 
    "🏗️ Data Quality", 
    "🗺️ Coverage",
    "🚨 Alerts"
])

with tab1:
    st.header("Real-time Mapping Dashboard")
    
    # Query aktivitas terkini
    activity_query = f"""
    SELECT 
        DATE_TRUNC('hour', to_timestamp((tags->>'timestamp')::bigint)) as mapping_hour,
        COUNT(*) as features_mapped,
        COUNT(DISTINCT tags->>'user') as unique_mappers
    FROM postpass_pointlinepolygon 
    WHERE tags->>'timestamp' IS NOT NULL
        AND tags->>'user' IS NOT NULL
        AND geom && {bbox_wkt}
        AND to_timestamp((tags->>'timestamp')::bigint) > NOW() - INTERVAL '{hours_back} hours'
    GROUP BY mapping_hour
    ORDER BY mapping_hour DESC
    LIMIT 100
    """
    
    result = run_postpass_query(activity_query, False)
    
    if result and 'features' in result:
        data = []
        for feature in result['features']:
            data.append(feature['properties'])
        
        df_activity = pd.DataFrame(data)
        
        if not df_activity.empty:
            # Metrics
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Features", df_activity['features_mapped'].sum())
            with col2:
                st.metric("Unique Mappers", df_activity['unique_mappers'].sum())
            with col3:
                st.metric("Active Hours", len(df_activity))
            
            # Simple table sebagai pengganti chart
            st.subheader("Activity Timeline")
            st.dataframe(df_activity)
    else:
        st.info("Tidak ada data aktivitas dalam timeframe ini")

with tab2:
    st.header("Mapper Activity Analysis")
    
    suspicious_query = f"""
    SELECT 
        tags->>'user' as mapper,
        COUNT(*) as total_features,
        COUNT(DISTINCT ST_GeoHash(geom, 8)) as unique_areas,
        MIN(to_timestamp((tags->>'timestamp')::bigint)) as first_edit,
        MAX(to_timestamp((tags->>'timestamp')::bigint)) as last_edit
    FROM postpass_pointlinepolygon
    WHERE geom && {bbox_wkt}
        AND tags->>'timestamp' IS NOT NULL
        AND to_timestamp((tags->>'timestamp')::bigint) > NOW() - INTERVAL '{hours_back} hours'
    GROUP BY tags->>'user'
    HAVING COUNT(*) > 10
    ORDER BY total_features DESC
    LIMIT 20
    """
    
    result = run_postpass_query(suspicious_query, False)
    
    if result and 'features' in result:
        mapper_data = []
        for feature in result['features']:
            mapper_data.append(feature['properties'])
        
        df_mappers = pd.DataFrame(mapper_data)
        
        if not df_mappers.empty:
            # Calculate hours active and features per hour
            df_mappers['first_edit'] = pd.to_datetime(df_mappers['first_edit'])
            df_mappers['last_edit'] = pd.to_datetime(df_mappers['last_edit'])
            df_mappers['hours_active'] = (df_mappers['last_edit'] - df_mappers['first_edit']).dt.total_seconds() / 3600
            df_mappers['features_per_hour'] = df_mappers['total_features'] / df_mappers['hours_active'].replace(0, 1)
            
            # Flag suspicious mappers
            df_mappers['suspicious'] = df_mappers.apply(
                lambda x: '🚨' if (x['features_per_hour'] > 100 and x['unique_areas'] < 5) else '✅', axis=1
            )
            
            st.subheader("Top Mappers")
            st.dataframe(df_mappers[['mapper', 'total_features', 'unique_areas', 'features_per_hour', 'suspicious']])
            
            # Simple analysis
            suspicious_count = (df_mappers['suspicious'] == '🚨').sum()
            if suspicious_count > 0:
                st.warning(f"Ditemukan {suspicious_count} mapper dengan aktivitas mencurigakan")

with tab3:
    st.header("Data Quality Issues")
    
    quality_query = f"""
    SELECT 
        issue_type,
        COUNT(*) as issue_count
    FROM (
        SELECT 'INVALID_GEOMETRY' as issue_type, osm_id
        FROM postpass_polygon 
        WHERE geom && {bbox_wkt}
            AND NOT ST_IsValid(geom)
        
        UNION ALL
        
        SELECT 'MISSING_NAME_TAGS' as issue_type, osm_id
        FROM postpass_pointlinepolygon 
        WHERE geom && {bbox_wkt}
            AND (
                (tags->>'building' = 'yes' AND tags->>'name' IS NULL)
                OR (tags->>'highway' IS NOT NULL AND tags->>'name' IS NULL)
            )
        
        UNION ALL
        
        SELECT 'CRITICAL_NO_NAME' as issue_type, osm_id
        FROM postpass_polygon 
        WHERE geom && {bbox_wkt}
            AND tags->>'building' IN ('hospital', 'clinic', 'school')
            AND tags->>'name' IS NULL
    ) issues
    GROUP BY issue_type
    ORDER BY issue_count DESC
    """
    
    result = run_postpass_query(quality_query, False)
    
    if result and 'features' in result:
        quality_data = []
        for feature in result['features']:
            quality_data.append(feature['properties'])
        
        df_quality = pd.DataFrame(quality_data)
        
        if not df_quality.empty:
            st.subheader("Quality Issues Summary")
            
            # Display metrics
            for idx, row in df_quality.iterrows():
                col1, col2 = st.columns([1, 3])
                with col1:
                    st.metric(row['issue_type'], row['issue_count'])
                with col2:
                    st.progress(min(row['issue_count'] / 100, 1.0))
        else:
            st.success("✅ Tidak ditemukan issue kualitas data")

with tab4:
    st.header("Coverage Analysis")
    
    coverage_query = f"""
    SELECT 
        (SELECT COUNT(*) FROM postpass_polygon WHERE geom && {bbox_wkt} 
         AND tags->>'building' IN ('hospital', 'clinic', 'school')) as critical_buildings,
        (SELECT COUNT(*) FROM postpass_polygon WHERE geom && {bbox_wkt}) as total_buildings,
        (SELECT COUNT(*) FROM postpass_line WHERE geom && {bbox_wkt} 
         AND tags->>'highway' IS NOT NULL) as total_roads
    """
    
    result = run_postpass_query(coverage_query, False)
    
    if result and 'features' in result:
        coverage_data = result['features'][0]['properties']
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Critical Buildings", coverage_data['critical_buildings'])
        with col2:
            st.metric("Total Buildings", coverage_data['total_buildings'])
        with col3:
            st.metric("Total Roads", coverage_data['total_roads'])
        
        # Simple coverage calculation
        if coverage_data['total_buildings'] > 0:
            critical_ratio = (coverage_data['critical_buildings'] / coverage_data['total_buildings']) * 100
            st.write(f"Rasio Bangunan Kritis: {critical_ratio:.1f}%")

with tab5:
    st.header("Alert System")
    
    alerts_query = f"""
    SELECT 
        mapper,
        features_per_hour,
        issue_count,
        CASE 
            WHEN features_per_hour > 150 THEN 'CRITICAL'
            WHEN features_per_hour > 100 THEN 'HIGH' 
            WHEN issue_count > 10 THEN 'MEDIUM'
            ELSE 'LOW'
        END as alert_level
    FROM (
        SELECT 
            tags->>'user' as mapper,
            COUNT(*) / NULLIF(EXTRACT(EPOCH FROM (MAX(to_timestamp((tags->>'timestamp')::bigint)) - 
             MIN(to_timestamp((tags->>'timestamp')::bigint)))) / 3600, 0) as features_per_hour,
            SUM(CASE WHEN NOT ST_IsValid(geom) THEN 1 ELSE 0 END) as issue_count
        FROM postpass_pointlinepolygon
        WHERE geom && {bbox_wkt}
            AND tags->>'timestamp' IS NOT NULL
            AND to_timestamp((tags->>'timestamp')::bigint) > NOW() - INTERVAL '{hours_back} hours'
        GROUP BY tags->>'user'
        HAVING COUNT(*) > 5
    ) stats
    WHERE features_per_hour > 50 OR issue_count > 5
    ORDER BY features_per_hour DESC
    LIMIT 10
    """
    
    result = run_postpass_query(alerts_query, False)
    
    if result and 'features' in result:
        alert_data = []
        for feature in result['features']:
            alert_data.append(feature['properties'])
        
        df_alerts = pd.DataFrame(alert_data)
        
        if not df_alerts.empty:
            st.subheader("Active Alerts")
            
            for idx, row in df_alerts.iterrows():
                if row['alert_level'] == 'CRITICAL':
                    st.error(f"🚨 CRITICAL: {row['mapper']} - {row['features_per_hour']:.0f} features/hour")
                elif row['alert_level'] == 'HIGH':
                    st.warning(f"⚠️ HIGH: {row['mapper']} - {row['features_per_hour']:.0f} features/hour")
                elif row['alert_level'] == 'MEDIUM':
                    st.info(f"ℹ️ MEDIUM: {row['mapper']} - {row['issue_count']} issues")
        else:
            st.success("✅ No critical alerts detected")

# Refresh button
if st.sidebar.button("🔄 Refresh Data"):
    st.rerun()

st.sidebar.info(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
st.sidebar.markdown("---")
st.sidebar.markdown("**Data Source:** Postpass API + OSM")
