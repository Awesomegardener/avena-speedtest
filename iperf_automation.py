#!/usr/bin/env python3

#Make sure you have iperf3 excutable downloaded and make sure it's running before you run this code
# Change iperf3_path to where yuor iperf3 is located

# Below is the command to run this code
# python iperf_automation.py <ip address> -p <port> -t <test length> -i <test interval> -o <saved folder>
import json
import csv
import time
import datetime
import subprocess
import argparse
from pathlib import Path

##Runs both Download and Upload tests for 
def run_tests(server_ip, port, duration, iperf3_path):
    results = {}
    
    # Download test
    print("Running download test...")
    result = subprocess.run([iperf3_path, '-c', server_ip, '-p', str(port), '-t', str(duration), '-R', '-J'], 
                        capture_output=True, text=True)
    data = json.loads(result.stdout)
    results['download_mbps'] = data['end']['sum_received']['bits_per_second'] / 1_000_000

    time.sleep(1)

    # Upload test  
    print("Running upload test...")
    result = subprocess.run([iperf3_path, '-c', server_ip, '-p', str(port), '-t', str(duration), '-J'], 
                        capture_output=True, text=True)
    data = json.loads(result.stdout)
    results['upload_mbps'] = data['end']['sum_sent']['bits_per_second'] / 1_000_000
    
    return results

def save_to_csv(results, csv_file, test_number):
    timestamp = datetime.datetime.now().isoformat()
    
    # If file csv file does not exist, create a new one
    if not csv_file.exists():
        with open(csv_file, 'w', newline='') as f:
            csv.writer(f).writerow(['timestamp', 'test_number', 'download_mbps', 'upload_mbps',])
    
    row = [timestamp, test_number, results['download_mbps'], results['upload_mbps']]
    
    # New Row
    with open(csv_file, 'a', newline='') as f:
        csv.writer(f).writerow(row)
    
    print(f"Test #{test_number}: Down={results['download_mbps']:.2f} Mbps, Up={results['upload_mbps']:.2f} Mbps")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('server_ip')
    parser.add_argument('-p', '--port', type=int, default=5201)
    parser.add_argument('-t', '--duration', type=int, default=5)
    parser.add_argument('-i', '--interval', type=int, default=10)
    parser.add_argument('-o', '--output-dir', default='test_results')
    
    args = parser.parse_args()
    
    iperf3_path = r'C:\Users\aweso\OneDrive\Desktop\1School\Summer\2025\Research_Fabio\Project_HaLow\iperf_program\iperf3.exe'
    
    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    csv_file = output_dir / f"results_{timestamp}.csv"
    
    print(f"Testing {args.server_ip}:{args.port}")
    print(f"Results: {csv_file}")
    
    test_count = 0
    while True:
        test_count += 1
        results = run_tests(args.server_ip, args.port, args.duration, iperf3_path)
        save_to_csv(results, csv_file, test_count)
        time.sleep(args.interval)

if __name__ == "__main__":
    main()