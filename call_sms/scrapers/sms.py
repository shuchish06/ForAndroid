#!/usr/bin/env python3

import subprocess
import json
import csv
import sqlite3
import os
from datetime import datetime
from dataclasses import dataclass
from typing import Optional, List, Dict, Any


@dataclass
class Config:
    adb_path: str = "adb"
    max_records: Optional[int] = None
    output_dir: str = "sms_exports"
    csv_filename: str = "sms_export.csv"
    json_filename: str = "sms_export.json"
    temp_db_filename: str = "mmssms.db"
    
    def __post_init__(self):
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
    
    def get_csv_path(self) -> str:
        return os.path.join(self.output_dir, self.csv_filename)
    
    def get_json_path(self) -> str:
        return os.path.join(self.output_dir, self.json_filename)


class ADBManager:
    def __init__(self, config: Config):
        self.config = config
        self.device_id: Optional[str] = None
        self.has_root: bool = False
    
    def check_adb_connection(self) -> bool:
        try:
            result = subprocess.run([self.config.adb_path, "devices"], 
                                  capture_output=True, text=True)
            if result.returncode != 0:
                return False
                
            devices = result.stdout.strip().split('\n')[1:]
            connected_devices = [line.split('\t')[0] for line in devices if 'device' in line]
            
            if not connected_devices:
                return False
                
            self.device_id = connected_devices[0]
            return True
            
        except Exception:
            return False
    
    def check_root_access(self) -> bool:
        try:
            result = subprocess.run([self.config.adb_path, "shell", "su", "-c", "id"], 
                                  capture_output=True, text=True)
            if result.returncode == 0 and "uid=0" in result.stdout:
                self.has_root = True
                return True
            else:
                self.has_root = False
                return False
        except Exception:
            self.has_root = False
            return False


class SMSDataProcessor:
    @staticmethod
    def format_timestamp(timestamp: str) -> str:
        if timestamp and timestamp != 'null':
            try:
                ts = int(timestamp) / 1000
                return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
            except:
                return timestamp
        return timestamp
    
    @staticmethod
    def get_message_type(msg_type: str) -> str:
        type_map = {
            '1': 'Received',
            '2': 'Sent',
            '3': 'Draft',
            '4': 'Outbox',
            '5': 'Failed',
            '6': 'Queued'
        }
        return type_map.get(str(msg_type), f'Unknown ({msg_type})')


class AndroidSMSExtractor:
    def __init__(self, config: Config = None):
        self.config = config or Config()
        self.adb_manager = ADBManager(self.config)
        self.processor = SMSDataProcessor()
        self.adb_path = self.config.adb_path
        self.device_id = None
    
    def check_adb_connection(self):
        return self.adb_manager.check_adb_connection()
    
    def check_root_access(self):
        return self.adb_manager.check_root_access()
    
    def extract_sms_content_provider(self):
        if self.config.max_records:
            pass
        
        cmd = [self.adb_path, "shell", "content", "query", 
               "--uri", "content://sms", 
               "--projection", "_id,thread_id,address,body,date,date_sent,read,type,status"]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                return None
                
            lines = result.stdout.strip().split('\n')
            sms_data = []
            records_processed = 0
            
            for line in lines:
                if line.startswith('Row:'):
                    if self.config.max_records and records_processed >= self.config.max_records:
                        break
                    
                    row_data = {}
                    parts = line.split(',')
                    for part in parts:
                        if '=' in part:
                            key, value = part.split('=', 1)
                            key = key.strip().replace('Row: ', '')
                            row_data[key] = value.strip()
                    
                    if row_data:
                        sms_data.append(row_data)
                        records_processed += 1
            
            return sms_data
            
        except Exception:
            return None
    
    def extract_sms_database(self):
        if self.config.max_records:
            pass
        
        db_path = "/data/data/com.android.providers.telephony/databases/mmssms.db"
        local_db_path = os.path.join(self.config.output_dir, self.config.temp_db_filename)
        
        try:
            subprocess.run([self.adb_path, "shell", "su", "-c", 
                          f"cp {db_path} /sdcard/mmssms.db"], check=True)
            
            subprocess.run([self.adb_path, "pull", "/sdcard/mmssms.db", local_db_path], 
                          check=True)
            
            subprocess.run([self.adb_path, "shell", "rm", "/sdcard/mmssms.db"])
            
            return self.parse_sqlite_database(local_db_path)
            
        except subprocess.CalledProcessError:
            return None
    
    def parse_sqlite_database(self, db_path):
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            query = """
                SELECT _id, thread_id, address, body, date, date_sent, 
                       read, type, status, locked, sub_id
                FROM sms
                ORDER BY date DESC
            """
            
            if self.config.max_records:
                query += f" LIMIT {self.config.max_records}"
            
            cursor.execute(query)
            
            columns = [description[0] for description in cursor.description]
            sms_data = []
            
            for row in cursor.fetchall():
                sms_record = dict(zip(columns, row))
                sms_data.append(sms_record)
            
            conn.close()
            return sms_data
            
        except Exception:
            return None
    
    def format_timestamp(self, timestamp):
        return self.processor.format_timestamp(timestamp)
    
    def get_message_type(self, msg_type):
        return self.processor.get_message_type(msg_type)
    
    def save_to_csv(self, sms_data, filename=None):
        if not sms_data:
            return
        
        if filename is None:
            filename = self.config.get_csv_path()
            
        try:
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = ['id', 'thread_id', 'address', 'body', 'date', 
                             'date_sent', 'read', 'type', 'status']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                writer.writeheader()
                for sms in sms_data:
                    formatted_sms = {
                        'id': sms.get('_id', ''),
                        'thread_id': sms.get('thread_id', ''),
                        'address': sms.get('address', ''),
                        'body': sms.get('body', ''),
                        'date': self.format_timestamp(sms.get('date', '')),
                        'date_sent': self.format_timestamp(sms.get('date_sent', '')),
                        'read': 'Yes' if sms.get('read') == '1' else 'No',
                        'type': self.get_message_type(sms.get('type', '')),
                        'status': sms.get('status', '')
                    }
                    writer.writerow(formatted_sms)
            
        except Exception:
            pass
    
    def save_to_json(self, sms_data, filename=None):
        if not sms_data:
            return
        
        if filename is None:
            filename = self.config.get_json_path()
            
        try:
            formatted_data = []
            for sms in sms_data:
                formatted_sms = {
                    'id': sms.get('_id', ''),
                    'thread_id': sms.get('thread_id', ''),
                    'address': sms.get('address', ''),
                    'body': sms.get('body', ''),
                    'date': self.format_timestamp(sms.get('date', '')),
                    'date_sent': self.format_timestamp(sms.get('date_sent', '')),
                    'read': sms.get('read') == '1',
                    'type': self.get_message_type(sms.get('type', '')),
                    'status': sms.get('status', '')
                }
                formatted_data.append(formatted_sms)
            
            with open(filename, 'w', encoding='utf-8') as jsonfile:
                json.dump(formatted_data, jsonfile, indent=2, ensure_ascii=False)
            
        except Exception:
            pass
    
    def run_extraction(self):
        if not self.check_adb_connection():
            return
        
        has_root = self.check_root_access()
        
        sms_data = None
        
        if has_root:
            sms_data = self.extract_sms_database()
        
        if not sms_data:
            sms_data = self.extract_sms_content_provider()
        
        if sms_data:
            self.save_to_csv(sms_data)
            self.save_to_json(sms_data)


def main():
    extractor = AndroidSMSExtractor()
    extractor.run_extraction()


if __name__ == "__main__":
    main()