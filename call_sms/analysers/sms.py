import json
import csv
import pandas as pd
import re
from urllib.parse import urlparse
from pathlib import Path
import sys
import os
import matplotlib.pyplot as plt

# -------------------------- #
#  LOAD CONFIG FROM JSON   #
# -------------------------- #
CONFIG_PATH = Path(__file__).parent / "sms_config.json"
if not CONFIG_PATH.exists():
    raise FileNotFoundError(f"Config file not found: {CONFIG_PATH}")

with open(CONFIG_PATH, 'r') as f:
    config = json.load(f)

KEYWORDS_TO_SEARCH = config["keywords_to_search"]
CATEGORIES = config["categories"]
SUSPICIOUS_DOMAINS = config["suspicious_domains"]

# Will be set inside main
OUTPUT_DIR = None
OUTPUT_FILES = {}

# -------------------------- #
#  ANALYSIS FUNCTIONS      #
# -------------------------- #

def set_output_paths(base_output_dir):
    global OUTPUT_DIR, OUTPUT_FILES
    OUTPUT_DIR = Path(base_output_dir)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    OUTPUT_FILES = {
        "categorized": OUTPUT_DIR / "categorized_messages.csv",
        "urls": OUTPUT_DIR / "url_analysis.csv",
        "anomalies": OUTPUT_DIR / "anomalies.csv",
        "keyword_combined": OUTPUT_DIR / "keyword_matches.csv"
    }

def categorize_messages(df):
    print("\n📂 Categorizing messages...")
    categorized = []

    for _, row in df.iterrows():
        body = str(row['body']).lower() if pd.notnull(row['body']) else ""
        category = "Uncategorized"
        for cat, keywords in CATEGORIES.items():
            if any(kw in body for kw in keywords):
                category = cat
                break

        categorized.append({
            "Date": row['date'],
            "Sender": row['address'],
            "Message": str(row['body'])[:100],
            "Category": category
        })

    df_cat = pd.DataFrame(categorized)
    df_cat.to_csv(OUTPUT_FILES["categorized"], index=False)
    print(f" Categorized messages saved to {OUTPUT_FILES['categorized']}")
def create_category_pie_chart(df_categorized):
    import matplotlib.pyplot as plt

    category_counts = df_categorized['Category'].value_counts()
    labels = category_counts.index
    sizes = category_counts.values
    total = sum(sizes)

    legend_labels = [f"{label} - {size/total:.1%}" for label, size in zip(labels, sizes)]

    fig, ax = plt.subplots(figsize=(10, 8))
    wedges, _ = ax.pie(
        sizes,
        startangle=90,
        textprops={'fontsize': 10}
    )

    ax.legend(wedges, legend_labels, title="Categories", loc="center left", bbox_to_anchor=(1, 0, 0.5, 1))
    ax.set_title('SMS Categories Distribution', fontsize=14, fontweight='bold')
    return fig



def analyze_urls(df):
    print("\n🔗 Analyzing URLs...")
    url_data = []

    for _, row in df.iterrows():
        urls = re.findall(r"https?://[^\s]+", str(row['body']))
        for url in urls:
            domain = urlparse(url).netloc
            suspicious = any(s in domain for s in SUSPICIOUS_DOMAINS)
            category = "Banking" if "bank" in domain.lower() else "Promotional"

            url_data.append({
                "Date": row['date'],
                "Sender": row['address'],
                "Message": str(row['body'])[:100],
                "URL": url,
                "Domain": domain,
                "Suspicious": "Yes" if suspicious else "No",
                "Category": category
            })

    if url_data:
        df_url = pd.DataFrame(url_data)
        df_url.to_csv(OUTPUT_FILES["urls"], index=False)
        print(f"URL analysis saved to {OUTPUT_FILES['urls']}")
    else:
        print("No URLs found in messages.")


def detect_anomalies(df):
    print("\n Detecting anomalies...")
    anomalies = []

    for _, row in df.iterrows():
        body = str(row['body']).lower()
        has_money = "rs." in body or "sent" in body or "debited" in body
        suspicious_link = any(domain in body for domain in SUSPICIOUS_DOMAINS)

        if has_money and suspicious_link:
            anomalies.append({
                "Date": row['date'],
                "Sender": row['address'],
                "Message": row['body'][:100],
                "Reason": "Financial + Suspicious URL"
            })

    senders = df['address'].value_counts()
    frequent_senders = senders[senders > 5]
    for sender in frequent_senders.index:
        anomalies.append({
            "Date": "N/A",
            "Sender": sender,
            "Message": f"{senders[sender]} messages from sender",
            "Reason": "High frequency sender"
        })

    if anomalies:
        df_anom = pd.DataFrame(anomalies)
        df_anom.to_csv(OUTPUT_FILES["anomalies"], index=False)
        print(f" Anomalies saved to {OUTPUT_FILES['anomalies']}")
    else:
        print("No suspicious anomalies detected.")


def search_keywords(df, keywords):
    print(f"\n Searching for keywords: {', '.join(keywords)}")
    results = []

    for keyword in keywords:
        pattern = re.compile(fr"\b{keyword}s?\b", re.IGNORECASE)
        matches = df[df['body'].str.contains(pattern, na=False)]

        if not matches.empty:
            for _, row in matches.iterrows():
                results.append({
                    "Date": row['date'],
                    "Sender": row['address'],
                    "Message": row['body'][:100],
                    "MatchedKeyword": keyword
                })
            print(f" Found {len(matches)} messages for keyword '{keyword}'")

    if results:
        df_out = pd.DataFrame(results)
        df_out.to_csv(OUTPUT_FILES["keyword_combined"], index=False, quoting=csv.QUOTE_ALL)
        print(f"✅ All keyword matches saved to {OUTPUT_FILES['keyword_combined']}")
    else:
        print("No messages matched any keyword.")
def create_keyword_pie_chart(df_keywords):
    import matplotlib.pyplot as plt

    keyword_counts = df_keywords['MatchedKeyword'].value_counts()
    labels = keyword_counts.index
    sizes = keyword_counts.values
    total = sum(sizes)

    legend_labels = [f"{label} - {size/total:.1%}" for label, size in zip(labels, sizes)]

    fig, ax = plt.subplots(figsize=(10, 8))
    wedges, _ = ax.pie(sizes, startangle=90, textprops={'fontsize': 10})
    ax.legend(wedges, legend_labels, title="Keywords", loc="center left", bbox_to_anchor=(1, 0, 0.5, 1))
    ax.set_title('Keyword Matches Distribution', fontsize=14, fontweight='bold')
    return fig

# -------------------------- #
# 🚀 MAIN EXECUTION          #
# -------------------------- #

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python sms.py <sms_logs.csv> [output_dir]")
        sys.exit(1)

    input_file = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "analysis_output"

    set_output_paths(os.path.join(output_dir, "sms"))

    df = pd.read_csv(input_file)
    print("\n✅ File loaded successfully.")
    print("Total messages:", len(df))

    # Clean up the DataFrame
    df['body'] = df['body'].fillna("").astype(str)
    df['address'] = df['address'].fillna("Unknown")
    df['date'] = df['date'].fillna("Unknown")

    # Run all tasks
    categorize_messages(df)
    analyze_urls(df)
    detect_anomalies(df)
    search_keywords(df, KEYWORDS_TO_SEARCH)
