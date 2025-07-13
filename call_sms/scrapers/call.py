#!/usr/bin/env python3

import csv
import json
import subprocess
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class Config:
    output_file: str = "call_exports.csv"
    output_dir: str = "call_exports"
    device_id: Optional[str] = None
    timeout: int = 30
    encoding: str = "utf-8"
    content_uri: str = "content://call_log/calls"
    adb_command_timeout: int = 30
    csv_delimiter: str = ","
    csv_quotechar: str = '"'
    
    def get_full_output_path(self) -> Path:
        return Path(self.output_dir) / self.output_file


class ADBCallLogExtractor:
    def __init__(self, config: Config):
        self.config = config
        self.output_path = config.get_full_output_path()
        
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.entry_pattern = re.compile(r'Row: (\d+) (.+)')
        self.field_pattern = re.compile(r'(\w+)=([^,]*?)(?:,|$)')
    
    def _filter_null_values(self, row_data: Dict[str, str]) -> Dict[str, str]:
        filtered_data = {}
        
        for key, value in row_data.items():
            if key == "normalized_number":
                if value and value.strip() and value.lower() not in {
                    'null', 'none', 'n/a', 'na', '', '(null)', 'nil', 'undefined'
                }:
                    filtered_data[key] = value.strip()
            else:
                filtered_data[key] = value
        
        return filtered_data
    
    def _build_adb_command(self) -> List[str]:
        cmd = ["adb"]
        
        if self.config.device_id:
            cmd.extend(["-s", self.config.device_id])
        
        cmd.extend([
            "shell", "content", "query",
            "--uri", self.config.content_uri
        ])
        
        return cmd
    
    def _check_adb_available(self) -> bool:
        try:
            result = subprocess.run(
                ["adb", "version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    def _check_device_connected(self) -> bool:
        try:
            cmd = ["adb", "devices"]
            if self.config.device_id:
                cmd = ["adb", "-s", self.config.device_id, "get-state"]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if self.config.device_id:
                return result.returncode == 0 and "device" in result.stdout
            else:
                lines = result.stdout.strip().split('\n')[1:]
                return any(line.strip() and not line.endswith('offline') for line in lines)
                
        except subprocess.TimeoutExpired:
            return False
    
    def run_adb_query(self) -> List[str]:
        if not self._check_adb_available():
            return []
        
        if not self._check_device_connected():
            return []
        
        adb_command = self._build_adb_command()
        
        try:
            result = subprocess.run(
                adb_command,
                capture_output=True,
                text=True,
                timeout=self.config.adb_command_timeout,
                encoding=self.config.encoding
            )
            
            if result.returncode != 0:
                return []
            
            lines = result.stdout.strip().splitlines()
            return lines
            
        except subprocess.TimeoutExpired:
            return []
        except subprocess.CalledProcessError:
            return []
    
    def parse_call_log_data(self, lines: List[str]) -> Tuple[List[Dict[str, str]], List[str]]:
        parsed_data = []
        all_keys = set()
        
        for line in lines:
            try:
                match = self.entry_pattern.match(line)
                if not match:
                    continue
                
                row_id, raw_fields = match.groups()
                
                field_matches = self.field_pattern.findall(raw_fields)
                if not field_matches:
                    continue
                
                row_data = dict(field_matches)
                row_data['_row_id'] = row_id
                
                filtered_row_data = self._filter_null_values(row_data)
                
                if filtered_row_data:
                    parsed_data.append(filtered_row_data)
                    all_keys.update(filtered_row_data.keys())
                
            except Exception:
                continue
        
        sorted_keys = sorted(all_keys)
        
        return parsed_data, sorted_keys
    
    def _write_csv(self, data: List[Dict[str, str]], keys: List[str]) -> None:
        with open(self.output_path, 'w', newline='', encoding=self.config.encoding) as f:
            writer = csv.DictWriter(
                f,
                fieldnames=keys,
                delimiter=self.config.csv_delimiter,
                quotechar=self.config.csv_quotechar,
                quoting=csv.QUOTE_MINIMAL
            )
            writer.writeheader()
            writer.writerows(data)
    
    def _write_json(self, data: List[Dict[str, str]], keys: List[str]) -> None:
        with open(self.output_path, 'w', encoding=self.config.encoding) as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def write_output(self, data: List[Dict[str, str]], keys: List[str]) -> None:
        if not data:
            return
        
        try:
            if self.config.output_file.endswith('.json'):
                self._write_json(data, keys)
            else:
                self._write_csv(data, keys)
            
        except Exception:
            pass
    
    def extract_call_logs(self) -> Dict[str, any]:
        try:
            lines = self.run_adb_query()
            
            if not lines:
                return {"records_extracted": 0}
            
            parsed_data, keys = self.parse_call_log_data(lines)
            
            if not parsed_data:
                return {"records_extracted": 0}
            
            self.write_output(parsed_data, keys)
            
            return {
                "records_extracted": len(parsed_data),
                "fields_count": len(keys),
                "output_file": self.output_path
            }
            
        except Exception:
            return {"records_extracted": 0}


def main():
    config = Config()
    extractor = ADBCallLogExtractor(config)
    extractor.extract_call_logs()


if __name__ == "__main__":
    main()