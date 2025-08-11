#!/usr/bin/env python3
"""
Automated iperf3 testing script for mobile RF testing
Runs continuous iperf3 tests while logging GPS coordinates and results
Now with command-line arguments and detailed logging
"""

import json
import csv
import time
import datetime
import subprocess
from pathlib import Path
import signal
import sys
import os
import argparse

# Optional GPS integration (requires gpsd or similar)
try:
    import gpsd
    GPS_AVAILABLE = True
except ImportError:
    GPS_AVAILABLE = False
    print("GPS library not available. Install python-gps3 or gpsd-py3 for GPS logging")

class MobileIperfTester:
    def __init__(self, server_ip, server_port=5201, iperf3_path="iperf3", test_duration=5, test_interval=10, output_dir="test_results"):
        self.server_ip = server_ip
        self.server_port = server_port
        self.iperf3_path = iperf3_path  # Path to iperf3 executable
        self.test_duration = test_duration  # seconds per test
        self.test_interval = test_interval  # seconds between tests
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        # Create timestamped filenames
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        self.csv_file = self.output_dir / f"rf_test_{timestamp}.csv"
        self.detailed_log = self.output_dir / f"detailed_log_{timestamp}.txt"
        
        self.running = True
        self.test_count = 0
        
        # Initialize GPS if available
        if GPS_AVAILABLE:
            try:
                gpsd.connect()
                self.gps_enabled = True
                print("GPS connected successfully")
            except:
                self.gps_enabled = False
                print("GPS connection failed, continuing without GPS")
        else:
            self.gps_enabled = False
        
        # Setup CSV file with headers
        self.setup_csv_file()
        
        # Setup detailed log file
        self.setup_log_file()
        
        # Handle Ctrl+C gracefully
        signal.signal(signal.SIGINT, self.signal_handler)
    
    def setup_csv_file(self):
        """Initialize CSV file with headers"""
        headers = [
            'timestamp', 'test_number', 'latitude', 'longitude', 'altitude',
            'download_mbps', 'upload_mbps', 'download_transfer_gb', 'upload_transfer_gb',
            'download_retransmits', 'upload_retransmits', 'rtt_ms', 'test_duration',
            'download_intervals', 'upload_intervals'
        ]
        
        with open(self.csv_file, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(headers)
        print(f"Created results file: {self.csv_file}")
    
    def setup_log_file(self):
        """Initialize detailed log file"""
        with open(self.detailed_log, 'w') as logfile:
            logfile.write(f"Mobile RF Testing - Detailed Log\n")
            logfile.write(f"Started: {datetime.datetime.now()}\n")
            logfile.write(f"Server: {self.server_ip}:{self.server_port}\n")
            logfile.write("=" * 60 + "\n\n")
        print(f"Created detailed log: {self.detailed_log}")
    
    def log_to_file(self, message):
        """Write message to detailed log file"""
        with open(self.detailed_log, 'a') as logfile:
            timestamp = datetime.datetime.now().strftime('%H:%M:%S')
            logfile.write(f"[{timestamp}] {message}\n")
    
    def get_gps_location(self):
        """Get current GPS coordinates"""
        if not self.gps_enabled:
            return None, None, None
        
        try:
            packet = gpsd.get_current()
            if packet.mode >= 2:  # 2D or 3D fix
                return packet.lat, packet.lon, packet.alt
        except:
            pass
        return None, None, None
    
    def run_iperf3_test(self, reverse=False):
        """Run a single iperf3 test using subprocess"""
        try:
            cmd = [
                self.iperf3_path,
                '-c', self.server_ip,
                '-p', str(self.server_port),
                '-t', str(self.test_duration),
                '-J',  # JSON output
                '-i', '1'  # Interval reporting every second
            ]
            
            if reverse:
                cmd.append('-R')  # Reverse mode (download test)
            
            test_type = "download" if reverse else "upload"
            print(f"Running {test_type} test to {self.server_ip}:{self.server_port}...")
            self.log_to_file(f"Starting {test_type} test - Command: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=self.test_duration + 30
            )
            
            if result.returncode != 0:
                error_msg = f"iperf3 error: {result.stderr}"
                print(error_msg)
                self.log_to_file(error_msg)
                return None
            
            # Log the full JSON output
            self.log_to_file(f"{test_type.upper()} TEST JSON OUTPUT:")
            self.log_to_file(result.stdout)
            self.log_to_file("-" * 40)
            
            # Parse JSON output
            data = json.loads(result.stdout)
            
            # Extract interval data for detailed analysis
            intervals = []
            if 'intervals' in data:
                for interval in data['intervals']:
                    streams = interval.get('streams', [{}])
                    if streams:
                        stream = streams[0]
                        intervals.append({
                            'start': interval.get('streams', [{}])[0].get('start', 0),
                            'end': interval.get('streams', [{}])[0].get('end', 0),
                            'bytes': stream.get('bytes', 0),
                            'bits_per_second': stream.get('bits_per_second', 0),
                            'retransmits': stream.get('retransmits', 0)
                        })
            
            # Extract key metrics from the end summary
            end = data.get('end', {})
            sum_sent = end.get('sum_sent', {})
            sum_received = end.get('sum_received', {})
            
            return {
                'sent_mbps': sum_sent.get('bits_per_second', 0) / 1_000_000,
                'received_mbps': sum_received.get('bits_per_second', 0) / 1_000_000,
                'sent_bytes': sum_sent.get('bytes', 0),
                'received_bytes': sum_received.get('bytes', 0),
                'retransmits': sum_sent.get('retransmits', 0),
                'intervals': intervals
            }
            
        except subprocess.TimeoutExpired:
            error_msg = f"iperf3 {test_type} test timed out"
            print(error_msg)
            self.log_to_file(error_msg)
            return None
        except json.JSONDecodeError as e:
            error_msg = f"Failed to parse iperf3 JSON output: {e}"
            print(error_msg)
            self.log_to_file(error_msg)
            self.log_to_file(f"Raw output was: {result.stdout}")
            return None
        except Exception as e:
            error_msg = f"iperf3 {test_type} test failed: {e}"
            print(error_msg)
            self.log_to_file(error_msg)
            return None
    
    def run_ping_test(self):
        """Run a simple ping test for RTT"""
        try:
            cmd = ['ping', '-n', '3', self.server_ip]
            self.log_to_file(f"Running ping test: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd, 
                capture_output=True, text=True, timeout=10
            )
            
            self.log_to_file(f"Ping output: {result.stdout}")
            
            if result.returncode == 0:
                # Extract average RTT from Windows ping output
                lines = result.stdout.split('\n')
                for line in lines:
                    if 'Average' in line:
                        # Look for pattern like "Average = 123ms"
                        parts = line.split('=')
                        if len(parts) > 1:
                            rtt_str = parts[-1].strip().replace('ms', '')
                            return float(rtt_str)
        except Exception as e:
            self.log_to_file(f"Ping test failed: {e}")
        return None
    
    def log_result(self, download_result, upload_result, rtt):
        """Log test results to CSV file"""
        timestamp = datetime.datetime.now().isoformat()
        lat, lon, alt = self.get_gps_location()
        
        # Prepare data row
        row = [
            timestamp,
            self.test_count,
            lat if lat is not None else '',
            lon if lon is not None else '',
            alt if alt is not None else '',
            download_result['received_mbps'] if download_result else '',
            upload_result['sent_mbps'] if upload_result else '',
            download_result['received_bytes']/1_000_000_000 if download_result else '',  # GB
            upload_result['sent_bytes']/1_000_000_000 if upload_result else '',  # GB
            download_result['retransmits'] if download_result else '',
            upload_result['retransmits'] if upload_result else '',
            rtt if rtt else '',
            self.test_duration,
            len(download_result['intervals']) if download_result else '',
            len(upload_result['intervals']) if upload_result else ''
        ]
        
        # Write to CSV
        with open(self.csv_file, 'a', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(row)
        
        # Print summary
        print(f"Test #{self.test_count} completed:")
        if lat and lon:
            print(f"  Location: {lat:.6f}, {lon:.6f}")
        if download_result:
            print(f"  Download: {download_result['received_mbps']:.2f} Mbps ({download_result['received_bytes']/1_000_000:.1f} MB)")
        if upload_result:
            print(f"  Upload: {upload_result['sent_mbps']:.2f} Mbps ({upload_result['sent_bytes']/1_000_000:.1f} MB)")
        if rtt:
            print(f"  RTT: {rtt:.2f} ms")
        print("-" * 50)
        
        # Log summary to file
        self.log_to_file(f"TEST #{self.test_count} SUMMARY:")
        self.log_to_file(f"Download: {download_result['received_mbps']:.2f} Mbps" if download_result else "Download: FAILED")
        self.log_to_file(f"Upload: {upload_result['sent_mbps']:.2f} Mbps" if upload_result else "Upload: FAILED")
        self.log_to_file(f"RTT: {rtt:.2f} ms" if rtt else "RTT: FAILED")
        self.log_to_file("=" * 50)
    
    def run_test_cycle(self):
        """Run one complete test cycle (download + upload + ping)"""
        self.test_count += 1
        print(f"\nStarting test cycle #{self.test_count}")
        self.log_to_file(f"STARTING TEST CYCLE #{self.test_count}")
        
        # Run download test (reverse=True)
        download_result = self.run_iperf3_test(reverse=True)
        time.sleep(2)  # Brief pause between tests
        
        # Run upload test (reverse=False)
        upload_result = self.run_iperf3_test(reverse=False)
        time.sleep(1)
        
        # Run ping test
        rtt = self.run_ping_test()
        
        # Log results
        self.log_result(download_result, upload_result, rtt)
    
    def start_testing(self):
        """Start the continuous testing loop"""
        print(f"Starting automated iperf3 testing to {self.server_ip}:{self.server_port}")
        print(f"Test duration: {self.test_duration}s, Interval: {self.test_interval}s")
        print(f"Results will be saved to: {self.csv_file}")
        print(f"Detailed logs will be saved to: {self.detailed_log}")
        print("Press Ctrl+C to stop testing\n")
        
        self.log_to_file(f"Testing started - {self.server_ip}:{self.server_port}")
        
        try:
            while self.running:
                start_time = time.time()
                
                self.run_test_cycle()
                
                # Calculate sleep time to maintain interval
                elapsed = time.time() - start_time
                sleep_time = max(0, self.test_interval - elapsed)
                
                if sleep_time > 0 and self.running:
                    print(f"Waiting {sleep_time:.1f}s until next test...")
                    time.sleep(sleep_time)
                    
        except KeyboardInterrupt:
            self.stop_testing()
    
    def stop_testing(self):
        """Stop the testing loop"""
        print("\nStopping tests...")
        self.running = False
        self.log_to_file(f"Testing stopped. Total tests: {self.test_count}")
        print(f"Testing complete. {self.test_count} tests saved to {self.csv_file}")
        print(f"Detailed logs saved to {self.detailed_log}")
    
    def signal_handler(self, sig, frame):
        """Handle Ctrl+C signal"""
        self.stop_testing()
        sys.exit(0)

def main():
    # Setup command line arguments
    parser = argparse.ArgumentParser(description='Mobile RF Testing with iperf3')
    parser.add_argument('server_ip', help='IP address of the iperf3 server')
    parser.add_argument('-p', '--port', type=int, default=5201, help='Server port (default: 5201)')
    parser.add_argument('--iperf3-path', default=r"C:\Users\aweso\OneDrive\Desktop\1School\Summer\2025\Research_Fabio\Project_HaLow\iperf_program\iperf3.exe", 
                        help='Path to iperf3 executable')
    parser.add_argument('-t', '--duration', type=int, default=5, help='Test duration in seconds (default: 5)')
    parser.add_argument('-i', '--interval', type=int, default=10, help='Interval between tests in seconds (default: 10)')
    parser.add_argument('-o', '--output-dir', default='test_results', help='Output directory for results (default: test_results)')
    
    args = parser.parse_args()
    
    print("Mobile RF Testing Script")
    print("=" * 30)
    print(f"Server: {args.server_ip}:{args.port}")
    print(f"Test duration: {args.duration}s")
    print(f"Test interval: {args.interval}s")
    print(f"Output directory: {args.output_dir}")
    print()
    
    # Create and start tester
    tester = MobileIperfTester(
        server_ip=args.server_ip,
        server_port=args.port,
        iperf3_path=args.iperf3_path,
        test_duration=args.duration,
        test_interval=args.interval,
        output_dir=args.output_dir
    )
    
    tester.start_testing()

if __name__ == "__main__":
    main()