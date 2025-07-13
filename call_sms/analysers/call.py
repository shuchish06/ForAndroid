import pandas as pd
from datetime import datetime, timedelta
import sys
from collections import Counter
import numpy as np
import os

def parse_datetime_safe(s):
    try:
        return pd.to_datetime(s)
    except Exception:
        return pd.NaT

def enrich_features(df):
    df = df.copy()
    df = df.dropna(subset=["number", "date"])
    df["parsed_date"] = df["date"].apply(parse_datetime_safe)
    df = df.dropna(subset=["parsed_date"])
    df["duration"] = pd.to_numeric(df["duration"], errors="coerce").fillna(0)
    df["call_hour"] = df["parsed_date"].dt.hour
    df["day"] = df["parsed_date"].dt.date
    df["is_known_contact"] = df["name"].notna().astype(int)
    df["is_zero_duration"] = (df["duration"] == 0).astype(int)
    df["is_short_call"] = (df["duration"] < 10).astype(int)
    df["is_long_call"] = (df["duration"] > 1800).astype(int)  # Calls longer than 30 minutes
    df["is_late_night"] = df["call_hour"].between(0, 5).astype(int)
    df["is_foreign"] = df["countryiso"].fillna("").ne(df["countryiso"].mode().iloc[0]).astype(int)
    df["is_hidden_number"] = pd.to_numeric(df["presentation"], errors="coerce").fillna(1).eq(0).astype(int)
    df["is_unknown_number"] = df["is_known_contact"].eq(0)
    df["is_missed_call"] = df["type"].eq(6).astype(int)  # Type 6 is typically missed calls
    df["is_incoming"] = df["type"].isin([1, 6]).astype(int)  # Type 1 = incoming, 6 = missed
    df["is_outgoing"] = df["type"].eq(2).astype(int)  # Type 2 = outgoing
    
    # Short calls from different numbers on same day (potential bot-like behavior)
    short_calls = df[df["is_short_call"] & df["is_unknown_number"]]
    short_calls_count = short_calls.groupby("day")["number"].nunique().rename("short_unknown_calls_today")
    df = df.merge(short_calls_count, on="day", how="left")
    df["short_unknown_calls_today"] = df["short_unknown_calls_today"].fillna(0)
    # Remove the date column as requested
    df = df.drop(columns=["date"])
    
    return df

def detect_call_patterns(df):
    """Detect various suspicious call patterns"""
    patterns = {}
    
    # 1. Frequent calls from same number within short time
    df_sorted = df.sort_values(['number', 'parsed_date'])
    frequent_callers = []
    
    for number in df['number'].unique():
        number_calls = df_sorted[df_sorted['number'] == number].copy()
        if len(number_calls) < 3:
            continue
            
        # Check for calls within 1 hour windows
        number_calls['time_diff'] = number_calls['parsed_date'].diff()
        rapid_calls = number_calls[number_calls['time_diff'] <= timedelta(hours=1)]
        
        if len(rapid_calls) >= 3:
            frequent_callers.append({
                'number': number,
                'rapid_calls_count': len(rapid_calls),
                'total_calls': len(number_calls),
                'is_known': number_calls['is_known_contact'].iloc[0],
                'avg_duration': number_calls['duration'].mean()
            })
    
    patterns['frequent_callers'] = frequent_callers
    
    # 2. Very long or very short call durations
    very_short = df[(df['duration'] < 5) & (df['duration'] > 0)]
    very_long = df[df['duration'] > 3600]  # Calls longer than 1 hour
    
    patterns['very_short_calls'] = {
        'count': len(very_short),
        'numbers': very_short['number'].value_counts().head(10).to_dict()
    }
    
    patterns['very_long_calls'] = {
        'count': len(very_long),
        'numbers': very_long['number'].value_counts().head(10).to_dict()
    }
    
    # 3. Missed/dropped calls frequency
    missed_calls = df[df['is_missed_call'] == 1]
    missed_patterns = missed_calls['number'].value_counts().head(20)
    
    patterns['frequent_missed_calls'] = {
        'total_missed': len(missed_calls),
        'top_numbers': missed_patterns.to_dict()
    }
    
    # 4. Call timing patterns (unusual hours)
    night_calls = df[df['is_late_night'] == 1]
    patterns['night_calls'] = {
        'count': len(night_calls),
        'numbers': night_calls['number'].value_counts().head(10).to_dict()
    }
    
    return patterns

def detect_spoof_calls(df):
    """Detect potential spoof or scam calls"""
    spoof_indicators = []
    
    # Analyze each number's behavior
    for number in df['number'].unique():
        number_calls = df[df['number'] == number]
        
        # Calculate spoof score based on multiple factors
        spoof_score = 0
        reasons = []
        
        # Factor 1: Unknown number with multiple calls
        if number_calls['is_unknown_number'].iloc[0] == 1:
            spoof_score += 1
            if len(number_calls) > 1:
                spoof_score += 1
                reasons.append("Multiple calls from unknown number")
        
        # Factor 2: Only incoming calls, no outgoing (never called back)
        incoming_count = number_calls['is_incoming'].sum()
        outgoing_count = number_calls['is_outgoing'].sum()
        
        if incoming_count > 0 and outgoing_count == 0 and incoming_count > 2:
            spoof_score += 2
            reasons.append("Multiple incoming calls, never called back")
        
        # Factor 3: High percentage of missed calls
        missed_ratio = number_calls['is_missed_call'].mean()
        if missed_ratio > 0.7 and len(number_calls) > 2:
            spoof_score += 2
            reasons.append(f"High missed call ratio ({missed_ratio:.1%})")
        
        # Factor 4: Very short or zero duration calls
        short_ratio = number_calls['is_short_call'].mean()
        if short_ratio > 0.8 and len(number_calls) > 1:
            spoof_score += 1
            reasons.append(f"High short call ratio ({short_ratio:.1%})")
        
        # Factor 5: Calls at unusual hours
        night_ratio = number_calls['is_late_night'].mean()
        if night_ratio > 0.5:
            spoof_score += 1
            reasons.append(f"Frequent late night calls ({night_ratio:.1%})")
        
        # Factor 6: Hidden number presentation
        if number_calls['is_hidden_number'].iloc[0] == 1:
            spoof_score += 1
            reasons.append("Hidden number presentation")
        
        # Factor 7: Foreign number (if applicable)
        if number_calls['is_foreign'].iloc[0] == 1:
            spoof_score += 1
            reasons.append("Foreign number")
        
        if spoof_score >= 3:  # Threshold for potential spoof
            spoof_indicators.append({
                'number': number,
                'spoof_score': spoof_score,
                'total_calls': len(number_calls),
                'missed_calls': number_calls['is_missed_call'].sum(),
                'avg_duration': number_calls['duration'].mean(),
                'reasons': reasons,
                'first_call': number_calls['parsed_date'].min(),
                'last_call': number_calls['parsed_date'].max()
            })
    
    return sorted(spoof_indicators, key=lambda x: x['spoof_score'], reverse=True)

def generate_summary(df, patterns, spoof_calls):
    """Generate comprehensive analysis summary"""
    summary = {}
    
    # Basic statistics
    summary['total_calls'] = len(df)
    summary['unique_numbers'] = df['number'].nunique()
    summary['known_contacts'] = df['is_known_contact'].sum()
    summary['unknown_numbers'] = df['is_unknown_number'].sum()
    summary['missed_calls'] = df['is_missed_call'].sum()
    summary['total_duration_hours'] = df['duration'].sum() / 3600
    
    # Call trends
    summary['most_active_contacts'] = df[df['is_known_contact'] == 1]['name'].value_counts().head(10).to_dict()
    summary['most_frequent_numbers'] = df['number'].value_counts().head(10).to_dict()
    
    # Time patterns
    summary['calls_by_hour'] = df['call_hour'].value_counts().sort_index().to_dict()
    summary['calls_by_day'] = df['day'].value_counts().head(10).to_dict()
    
    # Suspicious activity summary
    summary['suspicious_patterns'] = {
        'frequent_callers': len(patterns['frequent_callers']),
        'very_short_calls': patterns['very_short_calls']['count'],
        'very_long_calls': patterns['very_long_calls']['count'],
        'night_calls': patterns['night_calls']['count'],
        'potential_spoof_calls': len(spoof_calls)
    }
    
    return summary

def compute_risk_score(row):
    score = 0
    if row["is_unknown_number"]: score += 1
    if row["is_short_call"]: score += 1
    if row["is_late_night"]: score += 1
    if row["is_hidden_number"]: score += 1
    if row["is_foreign"]: score += 2
    if row["short_unknown_calls_today"] >= 3: score += 2
    if row["is_missed_call"]: score += 1
    if row["is_long_call"]: score += 1
    return score

def print_analysis_report(patterns, spoof_calls, summary):
    """Print detailed analysis report"""
    print("\n" + "="*80)
    print("CALL LOG ANALYSIS REPORT")
    print("="*80)
    
    # Basic Statistics
    print(f"\nBASIC STATISTICS")
    print(f"Total calls: {summary['total_calls']}")
    print(f"Unique numbers: {summary['unique_numbers']}")
    print(f"Known contacts: {summary['known_contacts']}")
    print(f"Unknown numbers: {summary['unknown_numbers']}")
    print(f"Missed calls: {summary['missed_calls']}")
    print(f"Total talk time: {summary['total_duration_hours']:.1f} hours")
    
    # Call Patterns
    print(f"\nSUSPICIOUS CALL PATTERNS")
    print(f"Frequent callers (rapid calls): {len(patterns['frequent_callers'])}")
    if patterns['frequent_callers']:
        print("Top frequent callers:")
        for caller in patterns['frequent_callers'][:5]:
            status = "Known" if caller['is_known'] else "Unknown"
            print(f"  - {caller['number']} - {caller['rapid_calls_count']} rapid calls, {caller['total_calls']} total ({status})")
    
    print(f"\nVery short calls (< 5 seconds): {patterns['very_short_calls']['count']}")
    if patterns['very_short_calls']['numbers']:
        print("Top numbers with short calls:")
        for num, count in list(patterns['very_short_calls']['numbers'].items())[:3]:
            print(f"  - {num}: {count} calls")
    
    print(f"\nVery long calls (> 1 hour): {patterns['very_long_calls']['count']}")
    if patterns['very_long_calls']['numbers']:
        print("Numbers with very long calls:")
        for num, count in list(patterns['very_long_calls']['numbers'].items())[:3]:
            print(f"  - {num}: {count} calls")
    
    print(f"\nLate night calls (12 AM - 5 AM): {patterns['night_calls']['count']}")
    if patterns['night_calls']['numbers']:
        print("Top late night callers:")
        for num, count in list(patterns['night_calls']['numbers'].items())[:3]:
            print(f"  - {num}: {count} calls")
    
    # Spoof Call Detection
    print(f"\nPOTENTIAL SPOOF/SCAM CALLS")
    print(f"Suspicious numbers detected: {len(spoof_calls)}")
    
    if spoof_calls:
        print("\nTop suspicious numbers:")
        for i, spoof in enumerate(spoof_calls[:5], 1):
            print(f"\n{i}. {spoof['number']} (Risk Score: {spoof['spoof_score']})")
            print(f"   Total calls: {spoof['total_calls']}, Missed: {spoof['missed_calls']}")
            print(f"   Avg duration: {spoof['avg_duration']:.1f} seconds")
            print(f"   Reasons: {', '.join(spoof['reasons'])}")
            print(f"   First call: {spoof['first_call'].strftime('%Y-%m-%d %H:%M')}")
            print(f"   Last call: {spoof['last_call'].strftime('%Y-%m-%d %H:%M')}")
    
    # Most Active Contacts
    print(f"\nMOST ACTIVE CONTACTS")
    if summary['most_active_contacts']:
        for name, count in list(summary['most_active_contacts'].items())[:5]:
            print(f"  - {name}: {count} calls")
    
    # Recommendations
    print(f"\nRECOMMENDATIONS")
    high_risk_count = len([s for s in spoof_calls if s['spoof_score'] >= 5])
    if high_risk_count > 0:
        print(f"  - Block {high_risk_count} high-risk numbers (score >= 5)")
    
    frequent_unknown = len([p for p in patterns['frequent_callers'] if not p['is_known']])
    if frequent_unknown > 0:
        print(f"  - Review {frequent_unknown} frequent unknown callers")
    
    if patterns['night_calls']['count'] > 10:
        print(f"  - Consider enabling 'Do Not Disturb' mode at night")
    
    print("\n" + "="*80)

def process_call_log(file_path, output_dir, risk_threshold=5):
    print(f"[*] Loading: {file_path}")
    os.makedirs(output_dir, exist_ok=True)
    df = pd.read_csv(file_path)
    
    # Enrich features
    df = enrich_features(df)
    
    # Detect patterns
    print("[*] Analyzing call patterns...")
    patterns = detect_call_patterns(df)
    
    # Detect spoof calls
    print("[*] Detecting potential spoof calls...")
    spoof_calls = detect_spoof_calls(df)
    
    # Generate summary
    print("[*] Generating summary...")
    summary = generate_summary(df, patterns, spoof_calls)
    
    # Compute risk scores
    df["risk_score"] = df.apply(compute_risk_score, axis=1)
    
    # Filter suspicious calls
    suspicious = df[df["risk_score"] >= risk_threshold].sort_values("risk_score", ascending=False)
    
    # Print analysis report
    print_analysis_report(patterns, spoof_calls, summary)
    
    # Save results
    if suspicious.empty:
        print(f"\n[+] No suspicious calls found with risk score >= {risk_threshold}")
    else:
        print(f"\n[!] {len(suspicious)} suspicious calls detected (score >= {risk_threshold})")
        
        suspicious_cols = [
            "number", "duration", "countryiso", "geocoded_location",
            "is_short_call", "is_long_call", "is_unknown_number", "is_foreign", 
            "is_hidden_number", "is_late_night", "is_missed_call", 
            "short_unknown_calls_today", "risk_score"
        ]
        
        # Only include columns that exist in the dataframe
        available_suspicious_cols = [col for col in suspicious_cols if col in suspicious.columns]
        suspicious[available_suspicious_cols].to_csv("suspicious_calls_scored.csv", index=False)
        print("[*] Suspicious calls saved to suspicious_calls_scored.csv")
    
    # Save spoof call analysis
    if spoof_calls:
        spoof_df = pd.DataFrame(spoof_calls)
        spoof_df.to_csv(os.path.join(output_dir, "potential_spoof_calls.csv"), index=False)
        print("[*] Potential spoof calls saved to potential_spoof_calls.csv")
    
    # Save complete analyzed data to CSV
    # Add spoof scores to main dataframe
    spoof_score_dict = {item['number']: item['spoof_score'] for item in spoof_calls}
    spoof_reasons_dict = {item['number']: '; '.join(item['reasons']) for item in spoof_calls}
    
    df['spoof_score'] = df['number'].map(spoof_score_dict).fillna(0)
    df['spoof_reasons'] = df['number'].map(spoof_reasons_dict).fillna('')
    df = df.sort_values(by='spoof_score', ascending=False)

    
    # Add pattern indicators
    frequent_caller_numbers = {caller['number'] for caller in patterns['frequent_callers']}
    df['is_frequent_caller'] = df['number'].isin(frequent_caller_numbers).astype(int)
    
    very_short_numbers = set(patterns['very_short_calls']['numbers'].keys())
    df['has_very_short_calls'] = df['number'].isin(very_short_numbers).astype(int)
    
    very_long_numbers = set(patterns['very_long_calls']['numbers'].keys())
    df['has_very_long_calls'] = df['number'].isin(very_long_numbers).astype(int)
    
    night_caller_numbers = set(patterns['night_calls']['numbers'].keys())
    df['is_night_caller'] = df['number'].isin(night_caller_numbers).astype(int)
    
    frequent_missed_numbers = set(patterns['frequent_missed_calls']['top_numbers'].keys())
    df['has_frequent_missed'] = df['number'].isin(frequent_missed_numbers).astype(int)
    
    # Calculate per-number statistics
    number_stats = df.groupby('number').agg({
        'duration': ['count', 'mean', 'sum'],
        'is_missed_call': 'sum',
        'is_short_call': 'mean',
        'is_incoming': 'sum',
        'is_outgoing': 'sum'
    }).round(2)
    
    number_stats.columns = ['total_calls_from_number', 'avg_duration_from_number', 
                           'total_duration_from_number', 'total_missed_from_number',
                           'short_call_ratio_from_number', 'incoming_calls_from_number',
                           'outgoing_calls_from_number']
    
    df = df.merge(number_stats, left_on='number', right_index=True, how='left')
    
    # Define columns for complete analysis CSV - REMOVED 'date', 'day', and 'parsed_date' columns
    complete_analysis_cols = [
        # Original data columns (excluding 'date')
        'number', 'name', 'duration', 'type', 'countryiso', 
        'geocoded_location', 'presentation', 'formatted_number',
        
        # Enriched features (excluding 'day' and 'parsed_date')
        'call_hour', 'is_known_contact', 'is_zero_duration',
        'is_short_call', 'is_long_call', 'is_late_night', 'is_foreign',
        'is_hidden_number', 'is_unknown_number', 'is_missed_call',
        'is_incoming', 'is_outgoing', 'short_unknown_calls_today',
        
        # Pattern indicators
        'is_frequent_caller', 'has_very_short_calls', 'has_very_long_calls',
        'is_night_caller', 'has_frequent_missed',
        
        # Per-number statistics
        'total_calls_from_number', 'avg_duration_from_number', 
        'total_duration_from_number', 'total_missed_from_number',
        'short_call_ratio_from_number', 'incoming_calls_from_number',
        'outgoing_calls_from_number',
        
        # Scoring
        'risk_score', 'spoof_score', 'spoof_reasons'
    ]
    
    # Save complete analysis
    available_cols = [col for col in complete_analysis_cols if col in df.columns]
    df[available_cols].to_csv(os.path.join(output_dir, "complete_call_analysis.csv"), index=False)
    print("[*] Complete analysis saved to complete_call_analysis.csv")
    
    # Save summary report
    with open(os.path.join(output_dir, "call_analysis_summary.txt"), "w") as f:
        f.write("CALL LOG ANALYSIS SUMMARY\n")
        f.write("=" * 50 + "\n\n")
        f.write(f"Total calls analyzed: {summary['total_calls']}\n")
        f.write(f"Unique numbers: {summary['unique_numbers']}\n")
        f.write(f"Known contacts: {summary['known_contacts']}\n")
        f.write(f"Potential spoof calls: {len(spoof_calls)}\n")
        f.write(f"High-risk calls (score >= {risk_threshold}): {len(suspicious)}\n")
        f.write(f"\nColumns in complete analysis CSV: {len(available_cols)}\n")
        f.write(f"Analysis completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        # Include top suspicious calls
        f.write("\nMost Suspicious Calls:\n")
        f.write("-" * 50 + "\n")
        if not suspicious.empty:
            top_suspicious = suspicious.sort_values("risk_score", ascending=False).head(5)
            for _, row in top_suspicious.iterrows():
                f.write(f"Number: {row['number']}, Risk Score: {row['risk_score']}, "
                        f"Missed: {row['is_missed_call']}, Short Call: {row['is_short_call']}, "
                        f"Late Night: {row['is_late_night']}, Foreign: {row['is_foreign']}, "
                        f"Hidden: {row['is_hidden_number']}\n")
        else:
            f.write("No suspicious calls detected.\n")



if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python call.py <input_file> [output_dir]")
        sys.exit(1)

    input_file = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "analysis_output"

    process_call_log(input_file, os.path.join(output_dir, "calls"))