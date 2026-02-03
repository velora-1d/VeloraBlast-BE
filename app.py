import streamlit as st
import json
import os
import subprocess
import pandas as pd
import time

# Page Config
st.set_page_config(page_title="Google Maps Scraper", page_icon="📍", layout="wide")

# Paths
CONFIG_FILE = "env_parameters.json"
LOG_FILE = "log_script_initial_contact.log"
DATA_DIR = "."

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}

def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)

def run_scraper():
    cmd = ["python3", "script_initial_contact.py"]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return process

# Title
st.title("📍 Google Maps Scraper & WA Automation")

# Sidebar - Configuration
st.sidebar.header("⚙️ Configuration")
config = load_config()

with st.sidebar.form("config_form"):
    api_key = st.text_input("Google Maps API Key", value=config.get("GOOGLE_MAPS_API_KEY", ""), type="password")
    wa_number = st.text_input("WhatsApp Number (Verification)", value=config.get("WHATSAPP_PHONE_NUMBER", ""))
    
    st.markdown("---")
    st.markdown("### 🔍 Search Parameters")
    search_phrase = st.text_input("Search Keyword (e.g., Toko Tasikmalaya)", value=config.get("search_phrase", ""))
    location_link = st.text_input("Google Maps Location Link", value=config.get("GOOGLE_MAPS_LINK", ""))
    radius = st.number_input("Radius (meters)", value=config.get("RADIUS", 5000))
    limit = st.number_input("Message Limit", value=config.get("MESSAGE_LIMIT", 10))
    
    st.markdown("---")
    st.markdown("### 📅 Appointment")
    appt_date = st.text_input("Date", value=config.get("APPOINTMENT_DATE", "2026-03-01"))
    appt_time = st.text_input("Time", value=config.get("APPOINTMENT_TIME", "10:00 AM"))

    submitted = st.form_submit_button("💾 Save Settings")
    if submitted:
        config["GOOGLE_MAPS_API_KEY"] = api_key
        config["WHATSAPP_PHONE_NUMBER"] = wa_number
        config["search_phrase"] = search_phrase
        config["GOOGLE_MAPS_LINK"] = location_link
        config["RADIUS"] = radius
        config["MESSAGE_LIMIT"] = limit
        config["APPOINTMENT_DATE"] = appt_date
        config["APPOINTMENT_TIME"] = appt_time
        save_config(config)
        st.sidebar.success("Settings saved!")

# Main Area
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("🚀 Control Panel")
    
    if st.button("▶️ Start Scraping", type="primary"):
        with st.spinner("Scraping in progress... Check logs for details."):
            process = run_scraper()
            st.session_state["process"] = process
            st.info("Scraper started in background...")

    # Log Viewer
    st.subheader("📜 Live Logs")
    log_placeholder = st.empty()
    
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            logs = f.read()
            st.code(logs[-2000:], language="log")
    else:
        st.code("No logs yet...", language="text")

with col2:
    st.subheader("📊 Results Preview")
    
    # Check for result folders
    if os.path.exists(DATA_DIR):
        folders = [f for f in os.listdir(DATA_DIR) if os.path.isdir(os.path.join(DATA_DIR, f)) and not f.startswith(".")]
        selected_folder = st.selectbox("Select Result Folder", ["Create a search to see results"] + folders)
        
        if selected_folder and selected_folder != "Create a search to see results":
            folder_path = os.path.join(DATA_DIR, selected_folder)
            files = [f for f in os.listdir(folder_path) if f.endswith(".csv")]
            
            for file in files:
                st.write(f"📄 {file}")
                df = pd.read_csv(os.path.join(folder_path, file))
                st.dataframe(df.head())
                
                with open(os.path.join(folder_path, file), "rb") as f:
                    st.download_button(f"⬇️ Download {file}", f, file_name=file)

# Auto-refresh logs (simple)
if st.button("🔄 Refresh Logs"):
    st.rerun()
