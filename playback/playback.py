'''
send a sequence of requests to emulate the game plugin

requests look like this
{"irl_time": "2026-10-17T22:32:10.8043351Z", "scene": "FLIGHT", "paused": false, "soi_name": "Kerbin", "vessel_id": "e29bac43-58ec-48c0-ba7c-e2583a02082d", "vessel_name": "Untitled Space Craft", "situation": "FLYING", "dv_last_stage": 166.495, "total_mass": 1.622, "total_thrust": 23.183, "acceleration": 14.289, "pitch": 89.966, "roll": null, "heading": .354, "static_pressure": 92.395, "altitude_sea_level": 619.15, "altitude_terrain": 546.617, "velocity_h": .493, "velocity_v": 60.425, "velocity_obt": 184.788, "velocity_srf": 60.427, "propellants": [{"name": "SolidFuel", "mass": .182, "remain": .174}], "engines": [{"name": "RT-5 \"Flea\" Solid Fuel Booster", "thrust": 23.183, "isp": 142.305, "propellants": ["SolidFuel"]}]}
'''

import argparse
from datetime import datetime, timedelta, UTC
from functools import partial
import json
import sys
from time import sleep
from uuid import uuid4

from tqdm import tqdm
import requests

def get_log_json(line):
    '''
    return dict, skip the log timestamp
    '''
    try:
        return json.loads(line[line.index(']', 10, 30) + 1:])
    except Exception:
        import pdb; pdb.set_trace()

def extract_log_timestamp(line):
    '''
    get the irl_time from the log line
    might be even better to use igt, because of time warp
    '''
    if isinstance(line, str):
        line = get_log_json(line)
    # otherwise, save some work decoding json
    return datetime.fromisoformat(line['irl_time'])
    # prefer the irl_time field
    # return datetime.fromisoformat(line[1, line.index(']', 10, 20)])

class FrameMaker:
    def __init__(self, log_file, ts):
        self.ts = ts

        # determine length of playback
        start_line = log_file.readline()
        self.start_time = extract_log_timestamp(start_line)

        # seek to 3000 bytes before end, current records are around 1k
        log_file.seek(0, 2) # end
        file_len = log_file.tell()
        log_file.seek(max(file_len - 3000, 0))
        end_lines = []
        while True:
            next_line = log_file.readline()
            if next_line == "":
                # eof
                break
            end_lines.append(next_line)
        self.end_time = extract_log_timestamp(end_lines[-1])
        self.duration = (self.end_time - self.start_time).seconds
        # print('duration:', self.duration)
        self.log_file = log_file
        
    def __iter__(self):
        self.log_file.seek(0) # rewind
        self.time = self.start_time - timedelta(seconds=1)
        return self

    def __next__(self):
        if self.time >= self.end_time:
            raise StopIteration
        line = self.log_file.readline()
        frame_data = get_log_json(line)
        frame_time = extract_log_timestamp(frame_data)
        # print("sleep: ", (frame_time - self.time).seconds / self.ts)
        sleep((frame_time - self.time).seconds / self.ts)

        # advance playback time
        self.time = frame_time
        return frame_data
        
    def __len__(self):
        '''
        this is an estimate, based on 1 frame/s
        getting an accurate number would require reading counting lines in the log
        '''
        return self.duration
        
def print_frame(frame):
    json.dump(frame, sys.stdout, indent=2)
    print('')

def send_frame(endpoint, frame):
    '''
    send the info in the frame to the backend
    '''
    requests.post(endpoint, json=frame)

def main(): 
    argp = argparse.ArgumentParser(
        description="replay a sequence of POSTs as captured in the request log")

    argp.add_argument("request_log", type=argparse.FileType(), help="request log containing messages to be replayed")
    argp.add_argument("--timescale", "-ts", type=float, default=1, help="positive is faster, e.g. 2 == double speed; 0.5 == half speed")
    argp.add_argument("--dry-run", action="store_true", help="print instead of sending")
    argp.add_argument("--endpoint", "-e", default="http://localhost:8000", help="HTTP endpoint for backend server")

    args = argp.parse_args()
    send_fn = print_frame if args.dry_run else partial(send_frame, args.endpoint)
    
    with args.request_log:
        frame_maker = FrameMaker(args.request_log, args.timescale)
        if not args.dry_run:
            frame_maker = tqdm(frame_maker)
        for frame in frame_maker:
            send_fn(frame)


if __name__ == '__main__':
    main()
