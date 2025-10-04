#!/usr/bin/env python3
# Make sure you have iperf3 executable downloaded and make sure it's running before you run this code
# Below is the command to run this code
# TCP: python iperf_automation.py <ip address> -p <port> -t <test length> -i <test interval> -o <saved folder>
# Example: python iperf_automation.py 127.0.0.1 -p 5201 -t 8 -i 20 -o highway_test_Linux
# UDP: python iperf_automation.py <ip address> -p <port> -t <test length> -i <test interval> -o <saved folder> -u -b <bandwidth>
# Example: python iperf_automation.py 127.0.0.1 -p 5201 -t 8 -i 20 -o highway_test_Linux_udp -u -b 100M
# -b 100M = 100 Mbps
# -b 1G = 1 Gbps
# -b 500M = 500 Mbps
# -b 10M = 10 Mbps
import json
import csv
import time
import datetime
import subprocess
import argparse
from pathlib import Path

## Runs both Download and Upload tests
def run_tests(server_ip, port, duration, iperf3_path, output_dir, test_count, protocol, bandwidth):
    results = {}
    
    # Download test
    print("Running download test...")
    cmd = [iperf3_path, '-c', server_ip, '-p', str(port), '-t', str(duration), '-R', '-J']
    if protocol == 'udp':
        cmd.insert(-2, '-u')
        cmd.insert(-2, '-b')
        cmd.insert(-2, bandwidth)
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    data = json.loads(result.stdout)
    
    if protocol == 'udp':
        results['download_mbps'] = data['end']['sum']['bits_per_second'] / 1_000_000
        results['download_jitter_ms'] = data['end']['sum'].get('jitter_ms', 0)
        results['download_lost_packets'] = data['end']['sum'].get('lost_packets', 0)
        results['download_lost_percent'] = data['end']['sum'].get('lost_percent', 0)
    else:
        results['download_mbps'] = data['end']['sum_received']['bits_per_second'] / 1_000_000
    
    # Save raw JSON
    with open(output_dir / f"raw_download_{test_count:03d}.json", 'w') as f:
        f.write(result.stdout)
    
    time.sleep(1)
    
    # Upload test  
    print("Running upload test...")
    cmd = [iperf3_path, '-c', server_ip, '-p', str(port), '-t', str(duration), '-J']
    if protocol == 'udp':
        cmd.insert(-1, '-u')
        cmd.insert(-1, '-b')
        cmd.insert(-1, bandwidth)
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    data = json.loads(result.stdout)
    
    if protocol == 'udp':
        results['upload_mbps'] = data['end']['sum']['bits_per_second'] / 1_000_000
        results['upload_jitter_ms'] = data['end']['sum'].get('jitter_ms', 0)
        results['upload_lost_packets'] = data['end']['sum'].get('lost_packets', 0)
        results['upload_lost_percent'] = data['end']['sum'].get('lost_percent', 0)
    else:
        results['upload_mbps'] = data['end']['sum_sent']['bits_per_second'] / 1_000_000
    
    # Save raw JSON
    with open(output_dir / f"raw_upload_{test_count:03d}.json", 'w') as f:
        f.write(result.stdout)
    
    return results

def save_to_csv(results, csv_file, test_number, protocol):
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
    
    # If file csv file does not exist, create a new one
    if not csv_file.exists():
        with open(csv_file, 'w', newline='') as f:
            if protocol == 'tcp':
                csv.writer(f).writerow(['timestamp', 'test_number', 'download_mbps', 'upload_mbps'])
            else:
                csv.writer(f).writerow([
                    'timestamp', 'test_number', 
                    'download_mbps', 'download_jitter_ms', 'download_lost_packets', 'download_lost_percent',
                    'upload_mbps', 'upload_jitter_ms', 'upload_lost_packets', 'upload_lost_percent'
                ])
    
    # Build row based on protocol
    if protocol == 'tcp':
        row = [timestamp, test_number, results['download_mbps'], results['upload_mbps']]
    else:
        row = [
            timestamp, test_number,
            results['download_mbps'], results['download_jitter_ms'], 
            results['download_lost_packets'], results['download_lost_percent'],
            results['upload_mbps'], results['upload_jitter_ms'],
            results['upload_lost_packets'], results['upload_lost_percent']
        ]
    
    # New Row
    with open(csv_file, 'a', newline='') as f:
        csv.writer(f).writerow(row)
    
    if protocol == 'tcp':
        print(f"Test #{test_number}: Down={results['download_mbps']:.2f} Mbps, Up={results['upload_mbps']:.2f} Mbps")
    else:
        print(f"Test #{test_number}: Down={results['download_mbps']:.2f} Mbps, Up={results['upload_mbps']:.2f} Mbps | DL Loss: {results['download_lost_percent']:.2f}%, UL Loss: {results['upload_lost_percent']:.2f}%")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('server_ip')
    parser.add_argument('-p', '--port', type=int, default=5201)
    parser.add_argument('-t', '--duration', type=int, default=5)
    parser.add_argument('-i', '--interval', type=int, default=10)
    parser.add_argument('-o', '--output-dir', default='test_results')
    parser.add_argument('-u', '--udp', action='store_true', help='Use UDP instead of TCP')
    parser.add_argument('-b', '--bandwidth', default='100M')
    
    args = parser.parse_args()
    
    protocol = 'udp' if args.udp else 'tcp'
    
    iperf3_path = 'iperf3'
    
    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    csv_file = output_dir / f"results_{protocol}_{timestamp}.csv"
    
    print(f"Testing {args.server_ip}:{args.port} using {protocol.upper()}")
    if protocol == 'udp':
        print(f"UDP bandwidth: {args.bandwidth}")
    print(f"Results: {csv_file}")
    
    test_count = 0
    while True:
        test_count += 1
        results = run_tests(args.server_ip, args.port, args.duration, iperf3_path, output_dir, test_count, protocol, args.bandwidth)
        save_to_csv(results, csv_file, test_count, protocol)
        time.sleep(args.interval)

if __name__ == "__main__":
    main()
