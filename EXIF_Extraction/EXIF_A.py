#!/usr/bin/env python
# coding: utf-8

# In[1]:


import json
import pandas as pd
import os


# In[2]:


EXIF_JSON = "/home/shuchi-sharma/Desktop/internSHip Poj/EXIF_Extraction/exif_analyze.json"


# In[3]:


def load_exif_data(json_path):
    if not os.path.exists(json_path):
        raise FileNotFoundError("exif_analyze.json not found")

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


# In[4]:


metadata_dict = load_exif_data(EXIF_JSON)


# In[5]:


def extract_temporal_metadata(metadata_dict):
    temporal_data = []

    for image_name, metadata in metadata_dict.items():
        date_original = metadata.get("EXIF:DateTimeOriginal", "NA")
        date_modified = metadata.get("EXIF:ModifyDate", "NA")
        date_created = metadata.get("EXIF:CreateDate", "NA")
        sub_sec = metadata.get("EXIF:SubSecTimeOriginal", "")

        temporal_data.append({
            "Image": image_name,
            "DateTimeOriginal": date_original + (f".{sub_sec}" if sub_sec else ""),
            "ModifyDate": date_modified,
            "CreateDate": date_created
        })

    df = pd.DataFrame(temporal_data)
    return df


# In[6]:


def create_google_maps_url(gps_coords):
    return f"https://maps.google.com/?q={gps_coords["lat"]},{gps_coords["lon"]}"


# In[7]:


def extract_gps_from_metadata(metadata):
    def clean(value):
        return value if value and str(value).strip() else "NA"

    gps = {
        "Latitude": clean(metadata.get("EXIF:GPSLatitude")),
        "Longitude": clean(metadata.get("EXIF:GPSLongitude")),
        "LatitudeRef": clean(metadata.get("EXIF:GPSLatitudeRef")),
        "LongitudeRef": clean(metadata.get("EXIF:GPSLongitudeRef"))
    }
    return gps


# In[8]:


def create_google_maps_url(coords):
    if all(coords.get(k) not in [None, "", "NA"] for k in ["Latitude", "Longitude", "LatitudeRef", "LongitudeRef"]):
        return f"https://www.google.com/maps?q={coords['Latitude']},{coords['Longitude']}"
    return "NA"


# In[9]:


def process_all_images_for_gps(metadata_dict):
    gps_records = []
    map_urls = {}
    for image_name, metadata in metadata_dict.items():
        coords = extract_gps_from_metadata(metadata)
        gps_records.append({"Image": image_name, **coords})
        map_urls[image_name] = create_google_maps_url(coords)
    return pd.DataFrame(gps_records), map_urls


# In[10]:


def get_device_make(image_metadata):
    make = image_metadata.get("EXIF:Make", "").strip()
    return make if make else "NA"

def get_device_model(image_metadata):
    model = image_metadata.get("EXIF:Model", "").strip()
    return model if model else "NA"

def get_camera_serial(image_metadata):
    possible_keys = [
        "EXIF:BodySerialNumber",
        "MakerNotes:SerialNumber",
        "EXIF:SerialNumber",
        "Composite:SerialNumber"
    ]
    for key in possible_keys:
        serial = image_metadata.get(key, "").strip()
        if serial:
            return serial
    return "NA"

def summarize_device_analysis(image_metadata):
    return {
        "DeviceMake": get_device_make(image_metadata),
        "DeviceModel": get_device_model(image_metadata),
        "CameraSerial": get_camera_serial(image_metadata)
    }




# In[11]:


def analyze_all_devices_for_analysis(metadata_dict):
    result = {}
    for filename, image_metadata in metadata_dict.items():
        result[filename] = summarize_device_analysis(image_metadata)

    return pd.DataFrame.from_dict(result, orient='index')


# In[12]:


def check_multiple_images_for_editors(all_metadata: dict) -> list:
    editors=["photoshop","snapseed","jpegmini","pixlr","lightroom","canva","gimp","paint","picsart"]
    out=[]
    for name,meta in all_metadata.items():
        s=[]
        for k in ["EXIF:Software","File:Comment","ICC_Profile:ProfileDescription"]:
            v=str(meta.get(k,"")).lower()
            s+=[e for e in editors if e in v]
        s=list(set(s))
        out.append({"image":name,"flagged":"Yes" if len(s)>0 else "No","editors_detected":", ".join(s) if s else "none"})
    return out


# In[ ]:


def generate_summary_analysis(df_time, df_gps, df_device, df_edited):
    summary = []

    # Image count
    total_images = len(df_time)
    summary.append(f"Total images analyzed: {total_images}")

    # Temporal analysis
    images_with_datetime = len(df_time[df_time['DateTimeOriginal'] != 'NA'])
    summary.append(f"Images with timestamp data: {images_with_datetime}/{total_images}")

    # Modified images detection
    modified_images = []
    for _, row in df_time.iterrows():
        if row['CreateDate'] != 'NA' and row['ModifyDate'] != 'NA':
            if row['CreateDate'] != row['ModifyDate']:
                modified_images.append(row['Image'])
    

    if modified_images:
        summary.append(f"Images with modification traces: {', '.join(modified_images)}")
    else:
        summary.append(f"Images with modification traces: None ")



    # GPS analysis
    images_with_gps = len(df_gps[(df_gps['Latitude'] != 'NA') & (df_gps['Longitude'] != 'NA')])
    summary.append(f"Images with GPS coordinates: {images_with_gps}/{total_images}")

    # Device analysis
    device_images = []
    for _, row in df_device.iterrows():
        if row['DeviceMake'] != 'NA':
            device_images.append(f"{row.name} ({row['DeviceMake']})")

    if device_images:
        summary.append(f"Device information found: {', '.join(device_images)}")

    # Editing analysis
    edited_image_details = []
    for img in df_edited:
        if img['flagged'] == 'Yes':
            edited_image_details.append(f"{img['image']} ({img['editors_detected']})")

    if edited_image_details:
        summary.append(f"Images with editing traces: {', '.join(edited_image_details)}")

    return '\n'.join(summary)


# In[ ]:


df_time = extract_temporal_metadata(metadata_dict)
df_gps ,map_link=process_all_images_for_gps(metadata_dict)
df_device=analyze_all_devices_for_analysis(metadata_dict)
df_edited=check_multiple_images_for_editors(metadata_dict)
summary_text=generate_summary_analysis(df_time, df_gps, df_device, df_edited)

