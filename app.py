import streamlit as st
import requests
import json
import time

# ===========================
# Page Configuration
# ===========================
st.set_page_config(
    page_title="HOT Campaign Creator",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ===========================
# Custom CSS
# ===========================
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        color: #FF6B35;
        text-align: center;
        margin-bottom: 2rem;
    }
    .success-box {
        padding: 1.5rem;
        border-radius: 10px;
        background: linear-gradient(135deg, #d4ffd4, #a8e6a8);
        border: 2px solid #4CAF50;
        color: #155724;
        margin: 1rem 0;
    }
    .error-box {
        padding: 1.5rem;
        border-radius: 10px;
        background: linear-gradient(135deg, #ffd4d4, #e6a8a8);
        border: 2px solid #f44336;
        color: #721c24;
        margin: 1rem 0;
    }
    .info-box {
        padding: 1.5rem;
        border-radius: 10px;
        background: linear-gradient(135deg, #d4f1f9, #a8d8e6);
        border: 2px solid #2196F3;
        color: #0c5460;
        margin: 1rem 0;
    }
    .stButton button {
        width: 100%;
        border-radius: 10px;
        height: 3rem;
        font-weight: bold;
        font-size: 1.1rem;
    }
</style>
""", unsafe_allow_html=True)

# ===========================
# Header
# ===========================
st.markdown('<div class="main-header">🌍 HOT Tasking Manager - Campaign Creator</div>', unsafe_allow_html=True)

# ===========================
# Sidebar - Instructions & About
# ===========================
with st.sidebar:
    st.image("https://tasks.hotosm.org/assets/img/hot-tm-logo.svg", width=100)
    st.header("ℹ️ About")
    st.markdown("""
    Create mapping campaigns for humanitarian efforts 
    using the HOT Tasking Manager API.
    """)
    
    st.header("📋 Step-by-Step Guide")
    
    with st.expander("1. Get Session Token"):
        st.markdown("""
        - Login to [HOT Tasking Manager](https://tasks.hotosm.org)
        - Open Developer Tools (F12)
        - Go to Application/Storage tab
        - Copy the `session` cookie value
        - Format: `Token your_token_here==`
        """)
    
    with st.expander("2. Fill Campaign Details"):
        st.markdown("""
        - **Name**: Unique campaign name
        - **Description**: Clear objectives
        - **Logo**: Public image URL
        - **URL**: Related website
        - **Org ID**: Usually 1 (HOT)
        """)
    
    with st.expander("3. Create & Monitor"):
        st.markdown("""
        - Click Create Campaign
        - Wait for API response
        - Save your Campaign ID
        """)
    
    st.markdown("---")
    st.header("🔗 Useful Links")
    st.markdown("""
    - [HOT Tasking Manager](https://tasks.hotosm.org)
    - [HOT Website](https://hotosm.org)
    - [API Documentation](https://tasks.hotosm.org/api/docs)
    - [Learn About Mapping](https://learnosm.org)
    """)

# ===========================
# Main Content Area
# ===========================
tab1, tab2 = st.tabs(["🚀 Create Campaign", "📚 Campaign Info"])

with tab1:
    st.subheader("Create New Mapping Campaign")
    
    # Authentication Section
    with st.container():
        st.markdown("### 🔐 Authentication")
        col1, col2 = st.columns([3, 1])
        
        with col1:
            session_token = st.text_input(
                "Session Token*",
                placeholder="Token your_actual_token_here==",
                type="password",
                help="Your HOT TM session token starting with 'Token '"
            )
        
        with col2:
            organisation_id = st.number_input(
                "Org ID*",
                min_value=1,
                value=1,
                help="Organization ID (1 = HOT)"
            )
    
    # Campaign Details Section
    with st.container():
        st.markdown("### 📝 Campaign Details")
        
        campaign_name = st.text_input(
            "Campaign Name*",
            placeholder="e.g., Flood Response - Thailand 2024",
            help="Unique name for your campaign"
        )
        
        campaign_description = st.text_area(
            "Description*",
            placeholder="Describe the purpose, area, and objectives of this mapping campaign...",
            height=120,
            help="Detailed description helps volunteers understand the context"
        )
        
        col3, col4 = st.columns(2)
        
        with col3:
            campaign_logo = st.text_input(
                "Logo URL",
                value="https://tasks.hotosm.org/assets/img/hot-tm-logo.svg",
                help="Public URL to campaign logo image"
            )
        
        with col4:
            campaign_url = st.text_input(
                "Campaign URL",
                placeholder="https://hotosm.org/projects/...",
                help="External URL with more information"
            )
    
    # Create Campaign Button
    st.markdown("---")
    
    if st.button("🚀 Create Campaign", type="primary", use_container_width=True):
        # Validation
        required_fields = {
            "Session Token": session_token,
            "Campaign Name": campaign_name,
            "Description": campaign_description
        }
        
        missing_fields = [field for field, value in required_fields.items() if not value]
        
        if missing_fields:
            st.error(f"❌ Please fill all required fields: {', '.join(missing_fields)}")
        else:
            # Show progress
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # API Call
            status_text.text("🔄 Connecting to HOT Tasking Manager...")
            progress_bar.progress(30)
            
            api_url = "https://tasks.hotosm.org/api/v2/campaigns/"
            
            headers = {
                "Authorization": session_token.strip(),
                "Accept-Language": "en",
                "Content-Type": "application/json"
            }
            
            campaign_data = {
                "name": campaign_name.strip(),
                "logo": campaign_logo.strip(),
                "url": campaign_url.strip(),
                "description": campaign_description.strip(),
                "organisations": [int(organisation_id)]
            }
            
            try:
                status_text.text("🔄 Creating campaign...")
                progress_bar.progress(60)
                
                response = requests.post(api_url, headers=headers, json=campaign_data)
                progress_bar.progress(90)
                
                # Handle response
                if response.status_code == 201:
                    progress_bar.progress(100)
                    status_text.text("✅ Campaign created successfully!")
                    
                    response_data = response.json()
                    
                    st.markdown(f"""
                    <div class="success-box">
                    <h3>🎉 Campaign Created Successfully!</h3>
                    <p><strong>Campaign ID:</strong> {response_data.get('campaignId', 'N/A')}</p>
                    <p><strong>Name:</strong> {response_data.get('name', 'N/A')}</p>
                    <p><strong>Status:</strong> Active ✅</p>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # Campaign details in columns
                    col_s1, col_s2 = st.columns(2)
                    
                    with col_s1:
                        st.info(f"**Next Steps:**\n\n1. Add projects to this campaign\n2. Recruit mappers\n3. Monitor progress")
                    
                    with col_s2:
                        st.info(f"**Quick Links:**\n\n- [HOT Tasking Manager](https://tasks.hotosm.org)\n- [Campaign Management Guide](https://learnosm.org)")
                    
                    # Raw response
                    with st.expander("📋 View API Response"):
                        st.json(response_data)
                        
                elif response.status_code == 401:
                    st.markdown('<div class="error-box">❌ Invalid session token. Please check your authorization token.</div>', unsafe_allow_html=True)
                elif response.status_code == 403:
                    st.markdown('<div class="error-box">❌ Permission denied. Your account may not have campaign creation rights.</div>', unsafe_allow_html=True)
                elif response.status_code == 409:
                    st.markdown('<div class="error-box">⚠️ Campaign name already exists. Please choose a different name.</div>', unsafe_allow_html=True)
                elif response.status_code == 400:
                    st.markdown('<div class="error-box">❌ Bad request. Please check your input parameters.</div>', unsafe_allow_html=True)
                    try:
                        error_details = response.json()
                        st.write("Error details:", error_details)
                    except:
                        st.write("Error response:", response.text)
                else:
                    st.markdown(f'<div class="error-box">❌ Error {response.status_code}: {response.text}</div>', unsafe_allow_html=True)
                    
            except requests.exceptions.ConnectionError:
                st.markdown('<div class="error-box">❌ Connection error. Please check your internet connection.</div>', unsafe_allow_html=True)
            except Exception as e:
                st.markdown(f'<div class="error-box">❌ Unexpected error: {str(e)}</div>', unsafe_allow_html=True)
            
            progress_bar.empty()
            status_text.empty()

with tab2:
    st.subheader("About HOT Campaigns")
    
    col_info1, col_info2 = st.columns(2)
    
    with col_info1:
        st.markdown("""
        ### 🎯 What are HOT Campaigns?
        
        Campaigns in HOT Tasking Manager help organize multiple mapping projects around a common theme or emergency response.
        
        **Common Campaign Types:**
        - 🚨 Disaster Response
        - 🏥 Health Initiatives  
        - 🌳 Environmental Projects
        - 🏠 Community Development
        - 📊 Data Quality Improvements
        """)
    
    with col_info2:
        st.markdown("""
        ### 📊 Campaign Benefits
        
        **Organization:**
        - Group related projects
        - Track overall progress
        - Coordinate volunteers
        
        **Visibility:**
        - Showcase impact areas
        - Attract specialized mappers
        - Report to stakeholders
        
        **Management:**
        - Centralized settings
        - Bulk operations
        - Unified reporting
        """)
    
    st.markdown("---")
    st.markdown("""
    ### 🌟 Best Practices
    
    1. **Clear Naming**: Use descriptive, unique names
    2. **Detailed Description**: Explain purpose and impact
    3. **Regular Updates**: Keep volunteers informed
    4. **Proper Organization**: Assign correct org ID
    5. **Quality Control**: Set up validation processes
    """)

# ===========================
# Footer
# ===========================
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: #666; padding: 2rem;'>"
    "Made with ❤️ for Humanitarian Mapping | "
    "Powered by HOT Tasking Manager API | "
    "<a href='https://hotosm.org' target='_blank'>Support Humanitarian OpenStreetMap Team</a>"
    "</div>", 
    unsafe_allow_html=True
)
