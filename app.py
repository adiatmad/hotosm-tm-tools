import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
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
min_confidence = st.sidebar.slider("Min Confidence Score", 0.0, 1.0, 0.7)

# Parse BBOX
try:
    bbox_parts = [float(x.strip()) for x in bbox.split(",")]
    bbox_wkt = f"ST_MakeEnvelope({bbox_parts[0]}, {bbox_parts[1]}, {bbox_parts[2]}, {bbox_parts[3]}, 4326)"
except:
    st.error("Format BBOX tidak valid!")
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
            st.error(f"Error API: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        st.error(f"Koneksi gagal: {str(e)}")
        return None

# Tab untuk berbagai fitur monitoring
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Dashboard Real-time", 
    "👥 Mapper Activity", 
    "🏗️ Data Quality", 
    "🗺️ Coverage Analysis",
    "🚨 Alert System"
])

with tab1:
    st.header("Real-time Mapping Dashboard")
    
    # Query aktivitas terkini
    activity_query = f"""
    SELECT 
        DATE_TRUNC('hour', to_timestamp((tags->>'timestamp')::bigint)) as mapping_hour,
        COUNT(*) as features_mapped,
        COUNT(DISTINCT tags->>'user') as unique_mappers,
        COUNT(*) / NULLIF(COUNT(DISTINCT tags->>'user'), 0) as productivity_ratio
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
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Features", df_activity['features_mapped'].sum())
            with col2:
                st.metric("Unique Mappers", df_activity['unique_mappers'].sum())
            with col3:
                st.metric("Avg Productivity", f"{df_activity['productivity_ratio'].mean():.1f}")
            with col4:
                st.metric("Active Hours", len(df_activity))
            
            # Charts
            col1, col2 = st.columns(2)
            with col1:
                fig_timeline = px.line(df_activity, x='mapping_hour', y='features_mapped', 
                                      title='Features Mapped per Jam')
                st.plotly_chart(fig_timeline, use_container_width=True)
            
            with col2:
                fig_mappers = px.bar(df_activity, x='mapping_hour', y='unique_mappers',
                                    title='Active Mappers per Jam')
                st.plotly_chart(fig_mappers, use_container_width=True)

with tab2:
    st.header("Mapper Activity Analysis")
    
    suspicious_query = f"""
    SELECT 
        tags->>'user' as mapper,
        COUNT(*) as total_features,
        COUNT(DISTINCT ST_GeoHash(geom, 8)) as unique_areas,
        MIN(to_timestamp((tags->>'timestamp')::bigint)) as first_edit,
        MAX(to_timestamp((tags->>'timestamp')::bigint)) as last_edit,
        (EXTRACT(EPOCH FROM (MAX(to_timestamp((tags->>'timestamp')::bigint)) - 
         MIN(to_timestamp((tags->>'timestamp')::bigint))))) / 3600 as hours_active,
        COUNT(*) / NULLIF(EXTRACT(EPOCH FROM (MAX(to_timestamp((tags->>'timestamp')::bigint)) - 
         MIN(to_timestamp((tags->>'timestamp')::bigint)))) / 3600, 0) as features_per_hour
    FROM postpass_pointlinepolygon
    WHERE geom && {bbox_wkt}
        AND tags->>'timestamp' IS NOT NULL
        AND to_timestamp((tags->>'timestamp')::bigint) > NOW() - INTERVAL '{hours_back} hours'
    GROUP BY tags->>'user'
    HAVING COUNT(*) > 10
    ORDER BY features_per_hour DESC
    LIMIT 50
    """
    
    result = run_postpass_query(suspicious_query, False)
    
    if result and 'features' in result:
        mapper_data = []
        for feature in result['features']:
            mapper_data.append(feature['properties'])
        
        df_mappers = pd.DataFrame(mapper_data)
        
        if not df_mappers.empty:
            # Flag suspicious mappers
            df_mappers['suspicious_score'] = df_mappers.apply(
                lambda x: 1 if (x['features_per_hour'] > 100 and x['unique_areas'] < 5) else 0, axis=1
            )
            
            st.subheader("Top Mappers by Activity")
            st.dataframe(df_mappers)
            
            # Visualization
            col1, col2 = st.columns(2)
            with col1:
                fig_productivity = px.scatter(df_mappers, x='features_per_hour', y='unique_areas',
                                            color='suspicious_score', hover_data=['mapper'],
                                            title='Mapper Productivity vs Area Coverage')
                st.plotly_chart(fig_productivity, use_container_width=True)

with tab3:
    st.header("Data Quality Issues")
    
    quality_query = f"""
    SELECT 
        issue_type,
        COUNT(*) as issue_count,
        ARRAY_AGG(DISTINCT user_name) as affected_mappers
    FROM (
        -- Invalid geometry
        SELECT 'INVALID_GEOMETRY' as issue_type, osm_id, tags->>'user' as user_name
        FROM postpass_polygon 
        WHERE geom && {bbox_wkt}
            AND NOT ST_IsValid(geom)
        
        UNION ALL
        
        -- Suspicious tagging
        SELECT 'SUSPICIOUS_TAGGING' as issue_type, osm_id, tags->>'user' as user_name
        FROM postpass_pointlinepolygon 
        WHERE geom && {bbox_wkt}
            AND (
                (tags->>'building' = 'yes' AND tags->>'name' IS NULL AND tags->>'amenity' IS NULL)
                OR (tags->>'highway' IS NOT NULL AND tags->>'name' IS NULL)
            )
        
        UNION ALL
        
        -- Missing critical infrastructure tags
        SELECT 'MISSING_CRITICAL_TAGS' as issue_type, osm_id, tags->>'user' as user_name
        FROM postpass_polygon 
        WHERE geom && {bbox_wkt}
            AND tags->>'building' IN ('hospital', 'clinic', 'school')
            AND (tags->>'name' IS NULL OR NOT tags ? 'emergency')
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
            col1, col2 = st.columns(2)
            with col1:
                fig_issues = px.bar(df_quality, x='issue_type', y='issue_count',
                                  title='Data Quality Issues by Type')
                st.plotly_chart(fig_issues, use_container_width=True)
            
            with col2:
                st.subheader("Detail Issues")
                for idx, row in df_quality.iterrows():
                    st.write(f"**{row['issue_type']}**: {row['issue_count']} issues")
                    st.write(f"Affected mappers: {', '.join(row['affected_mappers'][:3])}...")

with tab4:
    st.header("Coverage Analysis")
    
    coverage_query = f"""
    WITH critical_buildings AS (
        SELECT geom 
        FROM postpass_polygon 
        WHERE geom && {bbox_wkt}
        AND tags->>'building' IN ('hospital', 'clinic', 'school')
    ),
    road_coverage AS (
        SELECT COUNT(*) as roads_near_critical
        FROM postpass_line l
        WHERE EXISTS (
            SELECT 1 FROM critical_buildings cb
            WHERE ST_DWithin(cb.geom, l.geom, 0.01)
        )
        AND l.tags->>'highway' IS NOT NULL
    )
    SELECT 
        (SELECT COUNT(*) FROM critical_buildings) as total_critical_buildings,
        (SELECT roads_near_critical FROM road_coverage) as connected_roads,
        (SELECT COUNT(*) FROM postpass_polygon WHERE geom && {bbox_wkt}) as total_buildings,
        (SELECT COUNT(*) FROM postpass_line WHERE geom && {bbox_wkt} AND tags->>'highway' IS NOT NULL) as total_roads
    """
    
    result = run_postpass_query(coverage_query, False)
    
    if result and 'features' in result:
        coverage_data = result['features'][0]['properties']
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Critical Buildings", coverage_data['total_critical_buildings'])
        with col2:
            st.metric("Connected Roads", coverage_data['connected_roads'])
        with col3:
            st.metric("Total Buildings", coverage_data['total_buildings'])
        with col4:
            st.metric("Total Roads", coverage_data['total_roads'])
        
        # Coverage percentage
        if coverage_data['total_critical_buildings'] > 0:
            coverage_pct = (coverage_data['connected_roads'] / coverage_data['total_critical_buildings']) * 100
            st.progress(min(coverage_pct / 100, 1.0))
            st.write(f"Critical Infrastructure Coverage: {coverage_pct:.1f}%")

with tab5:
    st.header("Alert System")
    
    alerts_query = f"""
    SELECT 
        CASE 
            WHEN features_per_hour > 150 THEN 'CRITICAL: Suspicious Mapping Speed'
            WHEN features_per_hour > 100 THEN 'HIGH: Potential Bot Activity' 
            WHEN invalid_geom_count > 10 THEN 'HIGH: Geometry Issues'
            WHEN missing_tags > 20 THEN 'MEDIUM: Tagging Problems'
            ELSE 'LOW: Normal Activity'
        END as alert_level,
        mapper,
        features_per_hour,
        invalid_geom_count,
        missing_tags
    FROM (
        SELECT 
            tags->>'user' as mapper,
            COUNT(*) / NULLIF(EXTRACT(EPOCH FROM (MAX(to_timestamp((tags->>'timestamp')::bigint)) - 
             MIN(to_timestamp((tags->>'timestamp')::bigint)))) / 3600, 0) as features_per_hour,
            SUM(CASE WHEN NOT ST_IsValid(geom) THEN 1 ELSE 0 END) as invalid_geom_count,
            SUM(CASE WHEN tags->>'name' IS NULL AND tags->>'building' = 'yes' THEN 1 ELSE 0 END) as missing_tags
        FROM postpass_pointlinepolygon
        WHERE geom && {bbox_wkt}
            AND tags->>'timestamp' IS NOT NULL
            AND to_timestamp((tags->>'timestamp')::bigint) > NOW() - INTERVAL '{hours_back} hours'
        GROUP BY tags->>'user'
        HAVING COUNT(*) > 5
    ) stats
    WHERE features_per_hour > 50 OR invalid_geom_count > 5 OR missing_tags > 10
    ORDER BY 
        CASE 
            WHEN features_per_hour > 150 THEN 1
            WHEN features_per_hour > 100 THEN 2
            WHEN invalid_geom_count > 10 THEN 3
            WHEN missing_tags > 20 THEN 4
            ELSE 5
        END
    LIMIT 20
    """
    
    result = run_postpass_query(alerts_query, False)
    
    if result and 'features' in result:
        alert_data = []
        for feature in result['features']:
            alert_data.append(feature['properties'])
        
        df_alerts = pd.DataFrame(alert_data)
        
        if not df_alerts.empty:
            for idx, row in df_alerts.iterrows():
                if 'CRITICAL' in row['alert_level']:
                    st.error(f"🚨 {row['alert_level']} - Mapper: {row['mapper']}")
                elif 'HIGH' in row['alert_level']:
                    st.warning(f"⚠️ {row['alert_level']} - Mapper: {row['mapper']}")
                else:
                    st.info(f"ℹ️ {row['alert_level']} - Mapper: {row['mapper']}")
        else:
            st.success("✅ No critical alerts detected")

# Auto-refresh
if st.sidebar.button("Refresh Data"):
    st.rerun()

st.sidebar.info(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
