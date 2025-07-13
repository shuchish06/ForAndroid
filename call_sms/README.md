# 📄 CyberGuard Toolkit Documentation

## 🛡️ Project Context: CyberGuard – Android Cybersecurity Toolkit

**CyberGuard** is a suite of cybersecurity tools designed to identify suspicious, potentially malicious activity on Android devices — particularly in scenarios involving:

* Data leaks via social engineering
* SIM hijacks and number takeovers
* Scam or phishing attempts via SMS or call
* Bot/spam communication patterns

It requires **no root access**, leveraging Android’s `content://` ADB interfaces.

---

## 🔧 Modules

### 1. 📞 Call Log Risk Scorer

Analyzes call history (`content://call_log/calls`) and assigns a **risk score** to each call event using heuristics tailored to malicious behavior patterns.

### 2. ✉️ SMS Risk Scorer

Analyzes SMS history (`content://sms/`) to detect suspicious messages based on:

* Metadata patterns (short messages, late-night activity, burst patterns)
* Number behavior (foreign, hidden, new)
* Optional: keyword matching (e.g., OTP, urgent, "click here", "verify")

---

# ✉️ SMS Risk Scorer

## Purpose

Detect SMS messages that could indicate phishing, unauthorized verification attempts, or spam — with risk scoring based on behavioral + content heuristics.

---

## 📁 Input Requirements

Export SMS logs using:

```bash
adb shell content query --uri content://sms > sms_logs_full_dump.csv
```

Ensure output includes fields such as:

* `address`, `date`, `body`, `type`, `read`, `service_center`, `status`

---

## 🔍 Risk Scoring Heuristics

| Feature                      | Description                              | Risk Weight |
| ---------------------------- | ---------------------------------------- | ----------- |
| `is_unknown_number`          | Number not in contacts (if available)    | +1          |
| `is_foreign_number`          | Based on country prefix                  | +2          |
| `contains_phishing_keywords` | e.g., "verify", "click", "OTP", "urgent" | +2          |
| `is_late_night_sms`          | Sent between 00:00 and 05:00             | +1          |
| `sms_burst_from_number`      | Multiple messages in short time window   | +2          |
| `short_message_with_link`    | SMS < 25 chars + contains URL            | +2          |
| `unread_critical`            | Unread and critical keywords present     | +1          |

Default risk threshold: **score ≥ 3**

---

## 🚀 Usage

```bash
python detect_malicious_sms.py sms_logs_full_dump.csv
```

### Output:

* A file named `suspicious_sms_scored.csv`
* Each row: SMS message metadata + risk score + key triggers

---

## 🧠 Example Output

| address | date                | body                                                      | score | triggers                      |
| ------- | ------------------- | --------------------------------------------------------- | ----- | ----------------------------- |
| +252xxx | 2022-04-02 03:30:00 | "Verify your OTP now: 123456"                             | 5     | foreign, late\_night, keyword |
| Unknown | 2022-04-03 10:00:00 | "Click here for reward: [http://xyz.com](http://xyz.com)" | 4     | keyword, link                 |

---

## 🔐 Privacy & Safety

* SMS content is analyzed locally — no upload or remote processing.
* Scripts can be run offline on extracted data only.
* Intended for use in **forensics**, **user protection**, and **telecom security analysis**.

---

## 🧩 Integration Points

| Component           | Role                                   |
| ------------------- | -------------------------------------- |
| SMS Collector       | Exports via `content://sms`            |
| ML/Heuristic Engine | Flags high-risk messages               |
| Alert Module        | User notification or enterprise SOC    |
| Reporting           | CSV/JSON for review or dashboard input |

---

## 🧪 Use Cases

* **Phishing attempt detection**
* **Unauthorized OTP use**
* **Foreign SMS audit**
* **Silent SIM testing / service access**
* **Mass-texting detection (bot SMS)**

---

## 📂 File Structure (Updated)

```
cyberguard/
├── modules/
│   ├── detect_malicious_calls.py
│   └── detect_malicious_sms.py
├── data/
│   ├── call_logs_full_dump.csv
│   └── sms_logs_full_dump.csv
├── output/
│   ├── suspicious_calls_scored.csv
│   └── suspicious_sms_scored.csv
└── README.md
```

---

## ✅ Deployment Strategy

* Deploy on host machine with ADB access to user devices (for analysis).
* Schedule ADB exports daily or hourly.
* Run detection module as batch jobs or through CI/CD for threat monitoring.
* Combine outputs from both modules for **cross-channel correlation** (e.g., SMS scam → call follow-up).

---

## 🧭 Future Work

* NLP for message intent classification
* LLM-based semantic risk detection
* Integration with spam databases or threat intel feeds
* Cross-modal linking: suspicious call → follow-up SMS from same number
* Dashboards and user-facing reports
