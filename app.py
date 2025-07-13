import base64
import streamlit as st
import os
import subprocess
import json
import pandas as pd
import importlib
import sys
import uuid
from pathlib import Path

# ----------------------------
# Session Configuration
# ----------------------------
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

SESSION_ID = st.session_state.session_id

# ----------------------------
# App Background Styling
# ----------------------------
st.set_page_config(page_title="ForAndroid - Forensics Toolkit")
with open("App_Images/image3.png", "rb") as img_file:
    img_base64 = base64.b64encode(img_file.read()).decode()
    st.markdown(f"""
        <style>
        .stApp {{
            background-image: url('data:image/png;base64,{img_base64}');
            background-size: cover;
            background-repeat: no-repeat;
            background-attachment: fixed;
        }}
        </style>
    """, unsafe_allow_html=True)

# ----------------------------
# Helper Functions
# ----------------------------
def run_notebook(notebook_path):
    """Execute notebook and return result"""
    return subprocess.run([
        "jupyter", "nbconvert", "--to", "notebook", "--execute", "--inplace", notebook_path
    ], capture_output=True, text=True)

def save_uploaded_file(uploaded_file, save_path):
    """Save uploaded file to specified path"""
    with open(save_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

def display_download_button(file_path, label, file_name, mime_type="text/plain"):
    """Display download button if file exists"""
    if os.path.exists(file_path):
        with open(file_path, "rb") as f:
            st.download_button(
                label=label,
                data=f,
                file_name=file_name,
                mime=mime_type,
                use_container_width=True
            )
    else:
        st.warning(f"File not found: {file_name}")

def ensure_directories(*dirs):
    """Create directories if they don't exist"""
    for dir_path in dirs:
        os.makedirs(dir_path, exist_ok=True)

def clear_directory(directory):
    """Clear all files in directory"""
    if os.path.exists(directory):
        for fname in os.listdir(directory):
            fpath = os.path.join(directory, fname)
            if os.path.isfile(fpath):
                os.remove(fpath)

# ----------------------------
# Tab Layout
# ----------------------------
exif_tab, callsms_tab, extractor_tab = st.tabs(["EXIF Metadata Extraction", "Call & SMS Analysis", "SMS & Call Log Extractor"])

# ----------------------------
# EXIF TAB
# ----------------------------
with exif_tab:
    UPLOAD_DIR = "/home/shuchi-sharma/Desktop/internSHip Poj/images"
    EXIF_NOTEBOOK = "/home/shuchi-sharma/Desktop/internSHip Poj/EXIF_Extraction/EXIF_E.ipynb"
    EXIF_JSON = "/home/shuchi-sharma/Desktop/internSHip Poj/EXIF_Extraction/exif_analyze.json"
    text_file_path = "/home/shuchi-sharma/Desktop/internSHip Poj/EXIF_Extraction/exif_data.txt"

    st.title("Image Upload and Metadata Extraction")
    uploaded_files = st.file_uploader(
        "Upload multiple JPG/JPEG images for forensic metadata extraction",
        type=["jpg", "jpeg"],
        accept_multiple_files=True,
        key="exif_upload"
    )

    if uploaded_files:
        ensure_directories(UPLOAD_DIR)
        clear_directory(UPLOAD_DIR)
        
        for uploaded_file in uploaded_files:
            save_path = os.path.join(UPLOAD_DIR, uploaded_file.name)
            save_uploaded_file(uploaded_file, save_path)

        button_cols = st.columns([1, 2, 1])
        with button_cols[1]:
            find_metadata_clicked = st.button("Find Meta Data", use_container_width=True, key="exif_find_btn")

        if find_metadata_clicked:
            with st.spinner("Extracting metadata... running EXIF_E.ipynb"):
                result = run_notebook(EXIF_NOTEBOOK)

            if result.returncode == 0:
                st.toast("Metadata extracted and saved successfully!")
            else:
                st.error("Execution of EXIF_E.ipynb failed. Refresh and upload again")

        exif_a_cols = st.columns([1, 2, 1])
        with exif_a_cols[1]:
            run_exif_a_clicked = st.button("Generate Analysis", use_container_width=True, key="exif_gen_btn")

        if run_exif_a_clicked:
            with st.spinner("Generating..."):
                result_a = run_notebook("EXIF_Extraction/EXIF_E.ipynb")
            
            if result_a.returncode == 0:
                sys.path.insert(0, os.path.join(os.getcwd(), 'EXIF_Extraction'))
                EXIF_A = importlib.import_module("EXIF_A")
                importlib.reload(EXIF_A)
                
                # Display analysis results
                analysis_sections = [
                    ("Temporal Analysis Table", EXIF_A.df_time),
                    ("Geographical Analysis Table", EXIF_A.df_gps),
                    ("Device Analysis Table", EXIF_A.df_device),
                    ("Editing Softwares Used", EXIF_A.df_edited)
                ]
                
                for title, df in analysis_sections:
                    st.markdown(f"### {title}")
                    st.dataframe(df)
                
                # Display map links
                for image_name, url in EXIF_A.map_link.items():
                    link_text = f"[View Location on Map]({url})" if url and url != "NA" else "Location not available"
                    st.markdown(f"**{image_name}**: {link_text}", unsafe_allow_html=True)
                
                st.markdown("### Summary Analysis")
                st.text(EXIF_A.summary_text)
            else:
                st.write("Return code:", result_a.returncode)
                st.code(result_a.stderr)
                st.toast("No temporal metadata found in the images.")

        if find_metadata_clicked:
            download_cols = st.columns([1, 2, 1])
            with download_cols[1]:
                display_download_button(text_file_path, "Download Metadata", "exif_data.txt")

# ----------------------------
# CALL/SMS TAB
# ----------------------------
with callsms_tab:
    CALL_ANALYSER_SCRIPT = "call_sms/analysers/call.py"
    SMS_ANALYSER_SCRIPT = "call_sms/analysers/sms.py"

    CALL_SMS_UPLOAD_DIR = f"call_sms/uploads/{SESSION_ID}"
    SESSION_OUTPUT_DIR = f"analysis_output/{SESSION_ID}"

    # Output file paths
    CALL_OUTPUT_FILES = {
        "complete": os.path.join(SESSION_OUTPUT_DIR, "calls", "complete_call_analysis.csv"),
        "suspicious": os.path.join(SESSION_OUTPUT_DIR, "calls", "suspicious_calls_scored.csv"),
        "spoof": os.path.join(SESSION_OUTPUT_DIR, "calls", "potential_spoof_calls.csv"),
        "summary": os.path.join(SESSION_OUTPUT_DIR, "calls", "call_analysis_summary.txt")
    }

    SMS_OUTPUT_FILES = {
        "Anomalies": os.path.join(SESSION_OUTPUT_DIR, "sms", "anomalies.csv"),
        "Categorized Messages": os.path.join(SESSION_OUTPUT_DIR, "sms", "categorized_messages.csv"),
        "Keyword Matches": os.path.join(SESSION_OUTPUT_DIR, "sms", "keyword_matches.csv"),
        "URLs Found": os.path.join(SESSION_OUTPUT_DIR, "sms", "url_analysis.csv")
    }

    st.title("Calllogs , SMS Upload and Analysis")
    analysis_type = st.selectbox("Select Analysis Type", ["Call Records", "SMS Records"], key="analysis_selector")
    uploaded_csv = st.file_uploader("Upload CSV file for analysis", type=["csv"], key="csv_uploader")

    if uploaded_csv:
        ensure_directories(CALL_SMS_UPLOAD_DIR, 
                          os.path.join(SESSION_OUTPUT_DIR, "calls"), 
                          os.path.join(SESSION_OUTPUT_DIR, "sms"))

        saved_path = os.path.join(CALL_SMS_UPLOAD_DIR, uploaded_csv.name)
        save_uploaded_file(uploaded_csv, saved_path)
        st.success(f"File '{uploaded_csv.name}' uploaded successfully.")

        run_analysis = st.button(f"Run {analysis_type} Analysis", use_container_width=True, key="run_button")

        if run_analysis:
            with st.spinner("Running analysis..."):
                script_path = CALL_ANALYSER_SCRIPT if analysis_type == "Call Records" else SMS_ANALYSER_SCRIPT

                try:
                    result = subprocess.run(
                        ["python", script_path, saved_path, SESSION_OUTPUT_DIR],
                        capture_output=True, text=True
                    )

                    if result.returncode == 0:
                        st.toast("Analysis complete.")

                        if analysis_type == "Call Records":
                            # Display call analysis results
                            if os.path.exists(CALL_OUTPUT_FILES["complete"]):
                                df = pd.read_csv(CALL_OUTPUT_FILES["complete"])
                                st.markdown("### Suspicious Call Records")
                                st.dataframe(df)
                                display_download_button(
                                    CALL_OUTPUT_FILES["complete"], 
                                    "Download Call Analysis CSV", 
                                    "complete_call_analysis.csv", 
                                    "text/csv"
                                )
                            else:
                                st.error("Call analysis output file not found.")
                            
                            # Display spoof calls
                            if os.path.exists(CALL_OUTPUT_FILES["spoof"]):
                                st.markdown("### 🎭 Potential Spoof or Scam Calls")
                                df_spoof = pd.read_csv(CALL_OUTPUT_FILES["spoof"])
                                st.dataframe(df_spoof)
                                display_download_button(
                                    CALL_OUTPUT_FILES["spoof"], 
                                    "Download Spoof Calls CSV", 
                                    "potential_spoof_calls.csv", 
                                    "text/csv"
                                )
                            else:
                                st.warning("Spoof calls file not found.")

                            # Display summary
                            if os.path.exists(CALL_OUTPUT_FILES["summary"]):
                                st.markdown("### Call Analysis Summary")
                                with open(CALL_OUTPUT_FILES["summary"], "r") as f:
                                    summary_text = f.read()
                                    st.text_area("Summary", summary_text, height=300)
                                
                                st.download_button(
                                    label="Download Summary Report",
                                    data=summary_text,
                                    file_name="call_analysis_summary.txt",
                                    mime="text/plain",
                                    use_container_width=True
                                )
                            else:
                                st.warning("Call summary report not found.")

                        else:
                            # SMS Analysis Results
                            from call_sms.analysers.sms import create_category_pie_chart, create_keyword_pie_chart
                            
                            for label, path in SMS_OUTPUT_FILES.items():
                                if os.path.exists(path):
                                    st.markdown(f"### {label}")
                                    df = pd.read_csv(path)
                                    st.dataframe(df)
                                    
                                    # Display charts for specific categories
                                    if label == "Categorized Messages":
                                        st.pyplot(create_category_pie_chart(df))
                                    elif label == "Keyword Matches":
                                        st.pyplot(create_keyword_pie_chart(df))
                                    
                                    display_download_button(path, f"Download {label} CSV", os.path.basename(path), "text/csv")
                                else:
                                    st.warning(f"{label} file not found: {path}")
                    else:
                        st.error("Analysis script failed.")
                        st.code(result.stderr)
                except Exception as e:
                    st.error(f"Exception occurred: {e}")

# ----------------------------
# SMS & CALL LOG EXTRACTOR TAB
# ----------------------------
with extractor_tab:
    # SMS & CALL LOG EXTRACTOR TAB


# SMS & CALL LOG EXTRACTOR TAB
    st.title("SMS & Call Log Extractor")

    # Prerequisites Section
    st.markdown("### Prerequisites & Setup Instructions")

    with st.expander("📋 Click to view setup requirements", expanded=False):
        st.markdown("""
        **Before using the SMS & Call Log Extractor, please ensure the following:**
        
        #### 1. Android Device Requirements
        - Android device with USB debugging enabled
        - Android version 5.0 or higher recommended
        - Device must be unlocked during extraction
        
        #### 2. Enable USB Debugging
        **Follow these steps on your Android device:**
        1. Go to **Settings** → **About Phone**
        2. Tap **Build Number** 7 times to enable Developer Options
        3. Go back to **Settings** → **Developer Options**
        4. Enable **USB Debugging**
        5. Enable **Stay Awake** (recommended)
        
        #### 3. System Requirements
        - ADB (Android Debug Bridge) installed on your system
        - Python 3.7+ with required dependencies
        - USB cable for device connection
        
        #### 4. Permission Requirements
        - Your device may show a popup asking to "Allow USB Debugging"
        - Select **Always allow from this computer** and tap **OK**
        - Some devices may require additional permissions for SMS/Call log access
        
        #### 5. Before Starting Extraction
        - Connect your Android device via USB cable
        - Ensure device is unlocked and screen is active
        - Close any running ADB processes or Android development tools
        - Grant any permission requests that appear on your device
        
        #### ⚠️ Important Notes
        - This tool requires ROOT access for complete SMS/Call log extraction
        - Non-rooted devices may have limited extraction capabilities
        - Always ensure you have proper authorization before extracting data
        - Keep your device connected throughout the entire extraction process
        """)

    # Step-by-Step Instructions
    st.markdown("### Step-by-Step Extraction Process")

    with st.expander("📝 Click to view extraction steps", expanded=False):
        st.markdown("""
        **Follow these steps in order:**
        
        **Step 1:** Complete all prerequisites from the section above
        
        **Step 2:** Connect your Android device via USB cable
        
        **Step 3:** Click "Connect Device" button below to verify connection
        
        **Step 4:** Select the type of data you want to extract
        
        **Step 5:** Keep your device connected for manual extraction process
        """)


    # Device Connection Section
    st.markdown("### Device Connection")
    device_connection_cols = st.columns([1, 2, 1])
    with device_connection_cols[1]:
        connect_device_clicked = st.button("Connect Device", use_container_width=True, key="connect_device_btn")

    if connect_device_clicked:
        with st.spinner("Checking device connection..."):
            try:
                # Check if ADB is available and device is connected
                result = subprocess.run(
                    ["adb", "devices"],
                    capture_output=True, 
                    text=True,
                    timeout=10
                )
                
                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')[1:]  # Skip header
                    connected_devices = [line for line in lines if line.strip() and not line.endswith('offline')]
                    
                    if connected_devices:
                        st.success("Device connected successfully!")
                        st.session_state.device_connected = True
                    else:
                        st.error("No devices found. Please check USB debugging is enabled.")
                        st.session_state.device_connected = False
                else:
                    st.error("ADB not available or device connection failed.")
                    st.session_state.device_connected = False
                    
            except subprocess.TimeoutExpired:
                st.error("Connection check timed out.")
                st.session_state.device_connected = False
            except FileNotFoundError:
                st.error("ADB not found. Please install Android SDK Platform Tools.")
                st.session_state.device_connected = False
            except Exception as e:
                st.error(f"Connection error: {e}")
                st.session_state.device_connected = False

    # Device Status Display
    if "device_connected" in st.session_state:
        if st.session_state.device_connected:
            st.success("✅ Device Status: Connected")
        else:
            st.error("❌ Device Status: Not Connected")

    # Extraction Options Section
    st.markdown("### Extraction Options")
    extraction_type = st.selectbox(
        "Select data to extract",
        ["Call Logs Only", "SMS Logs Only"],
        key="extraction_selector"
    )

    start_extraction_clicked = st.button("Start Extraction", use_container_width=True, key="start_extraction_btn")

    if start_extraction_clicked:
        if "device_connected" not in st.session_state or not st.session_state.device_connected:
            st.error("❌ Please connect device first using the 'Connect Device' button above.")
        else:
            if extraction_type == "Call Logs Only":
                with st.spinner("📱 Extracting call logs from device..."):
                    try:
                        # Run the call.py script in background  
                        result = subprocess.run(
                            [sys.executable, "call_sms/scrapers/call.py"],
                            capture_output=True, 
                            text=True,
                            timeout=60
                        )
                        
                        if result.returncode == 0:
                            st.success("✅ Extraction completed successfully!")
                            if result.stdout:
                                st.code(result.stdout)
                            
                            # Check if output file was created and provide download
                            output_file = Path("call_exports/call_exports.csv")
                            if output_file.exists():
                                with open(output_file, "rb") as file:
                                    st.download_button(
                                        label="Download Call Logs",
                                        data=file,
                                        file_name="call_logs.csv",
                                        mime="text/csv"
                                    )
                        else:
                            st.error("❌ Extraction failed!")
                            if result.stderr:
                                st.error(f"Error: {result.stderr}")
                                
                    except subprocess.TimeoutExpired:
                        st.error("❌ Extraction timed out. Please try again.")
                    except Exception as e:
                        st.error(f"❌ Extraction error: {e}")
            
            elif extraction_type == "SMS Logs Only":
                with st.spinner("📱 Extracting SMS logs from device..."):
                    try:
                        # Run the sms.py script in background  
                        result = subprocess.run(
                            [sys.executable, "call_sms/scrapers/sms.py"],
                            capture_output=True, 
                            text=True,
                            timeout=60
                        )
                        
                        if result.returncode == 0:
                            st.success("✅ SMS extraction completed successfully!")
                            if result.stdout:
                                st.code(result.stdout)
                            
                            # Check if output file was created and provide download
                            output_file = Path("sms_exports/sms_export.csv")
                            if output_file.exists():
                                with open(output_file, "rb") as file:
                                    st.download_button(
                                        label="Download SMS Logs",
                                        data=file,
                                        file_name="sms_logs.csv",
                                        mime="text/csv"
                                    )
                        else:
                            st.error("❌ SMS extraction failed!")
                            if result.stderr:
                                st.error(f"Error: {result.stderr}")
                                
                    except subprocess.TimeoutExpired:
                        st.error("❌ SMS extraction timed out. Please try again.")
                    except Exception as e:
                        st.error(f"❌ SMS extraction error: {e}")