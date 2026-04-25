# After making your desired changes, update .memory/memory.md with what you did and why. Read it before each task.
"""
Seed demo collections for the firefighter minimap UI.

Writes the following to MongoDB Atlas (csi_demo db):

    buildings          one floorplan with rooms, doors, walls
    sensors            CSI sender/receiver positions in (x,y) m
    simulated_motion   per-tick motion docs with person ground-truth (x,y)
    trajectories       smoothed person paths inferred from motion
    vitals             per-person breathing rate + heart rate (mmWave-style)
    detections         high-level events (person entered Room A, etc.)
    alerts             "person immobile / vitals weak" — firefighter-actionable
    hazards            simulated fire/smoke timeline

Run:
    python seed_demo_data.py                       # default: walking, 3 min
    python seed_demo_data.py --scenario fire       # walking + fire breakout
    python seed_demo_data.py --scenario trapped    # person collapses, alerts
    python seed_demo_data.py --scenario all        # everything in one timeline
    python seed_demo_data.py --clear               # wipe demo collections first
"""

from __future__ import annotations

import argparse
import math
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from pymongo import ASCENDING, MongoClient, UpdateOne


# ---- floorplan: 20m x 12m, 5 rooms separated by walls ----
BUILDING = {
    "_id": "training-tower-b-f1",
    "name": "Training Tower B — Floor 1",
    "width_m": 20,
    "height_m": 12,
    "rooms": [
        {"id": "lobby",   "name": "Lobby",     "polygon": [[0,0],[8,0],[8,4],[0,4]]},
        {"id": "room_a",  "name": "Room A",    "polygon": [[0,4],[8,4],[8,12],[0,12]]},
        {"id": "hallway", "name": "Hallway",   "polygon": [[8,0],[12,0],[12,12],[8,12]]},
        {"id": "room_b",  "name": "Room B",    "polygon": [[12,0],[20,0],[20,6],[12,6]]},
        {"id": "room_c",  "name": "Room C",    "polygon": [[12,6],[20,6],[20,12],[12,12]]},
    ],
    "doors": [
        {"between": ["lobby", "hallway"],   "x": 8,  "y": 2},
        {"between": ["lobby", "room_a"],    "x": 4,  "y": 4},
        {"between": ["hallway", "room_b"],  "x": 12, "y": 3},
        {"between": ["hallway", "room_c"],  "x": 12, "y": 9},
        {"between": ["lobby", "outside"],   "x": 0,  "y": 2},
    ],
    "walls": [
        # outer walls
        {"a": [0, 0],  "b": [20, 0]},
        {"a": [20, 0], "b": [20, 12]},
        {"a": [20, 12], "b": [0, 12]},
        {"a": [0, 12], "b": [0, 0]},
        # interior dividers
        {"a": [8, 0],  "b": [8, 12]},
        {"a": [12, 0], "b": [12, 12]},
        {"a": [0, 4],  "b": [8, 4]},
        {"a": [12, 6], "b": [20, 6]},
    ],
}

# ---- sensor deployment ----
# Receiver in middle, 4 senders at corners of the floor. Sender_ids match the
# real C6 boards (0x08 and 0xe0); 0x7c and 0x43 are placeholder extras for the demo.
SENSORS = [
    {"_id": "rx-01", "type": "csi_receiver", "node_id": "rx-01",
     "x": 10, "y": 6, "floor": 1, "sender_id": None},
    {"_id": "tx-08", "type": "csi_sender",   "sender_id": 0x08, "x":  2, "y":  2, "floor": 1, "label": "Lobby NW"},
    {"_id": "tx-e0", "type": "csi_sender",   "sender_id": 0xe0, "x": 18, "y":  3, "floor": 1, "label": "Room B"},
    {"_id": "tx-7c", "type": "csi_sender",   "sender_id": 0x7c, "x": 18, "y":  9, "floor": 1, "label": "Room C"},
    {"_id": "tx-43", "type": "csi_sender",   "sender_id": 0x43, "x":  2, "y": 10, "floor": 1, "label": "Room A"},
]


# ---- scenarios ----
def waypoints_walking() -> list[tuple[float, float, float]]:
    """(x, y, dwell_seconds) — a person walks through the building."""
    return [
        ( 0.5,  2.0, 4),  # enters at front door
        ( 4.0,  2.0, 6),  # crosses lobby
        ( 7.0,  3.0, 8),  # pauses near hallway entry
        (10.0,  6.0, 4),  # walks down hallway
        (14.0,  3.0, 12), # enters Room B, dwells (sitting)
        (10.0,  6.0, 4),
        (10.0, 10.0, 6),  # to Room C
        (16.0, 10.0, 18), # dwells in Room C — like trapped
    ]


def waypoints_two_persons() -> tuple[list, list]:
    p1 = [(0.5, 2.0, 3), (5.0, 2.5, 4), (10.0, 6.0, 8), (16.0, 9.0, 30)]
    p2 = [(0.5, 2.0, 8), (4.0, 4.5, 4), (4.0, 9.0, 12), (1.0, 11.0, 20)]
    return p1, p2


def waypoints_trapped() -> list[tuple[float, float, float]]:
    """Person walks in, makes it to Room C, then collapses and goes still."""
    return [
        ( 0.5,  2.0,  3),   # enters
        ( 5.0,  2.0,  3),
        ( 9.0,  3.0,  4),   # hallway
        (10.0,  6.0,  3),
        (10.0, 10.0,  3),
        (16.0, 10.0,  4),   # made it into Room C
        (16.5, 10.5, 90),   # collapses — 90 sec immobile (firefighter target)
    ]


# ---- motion physics: a sender's score spikes when the person is near the TX→RX LOS ----
def perpendicular_distance(px: float, py: float,
                           ax: float, ay: float, bx: float, by: float) -> float:
    """Distance from point P to line segment A→B."""
    abx, aby = bx - ax, by - ay
    apx, apy = px - ax, py - ay
    ab2 = abx * abx + aby * aby
    if ab2 == 0:
        return math.hypot(apx, apy)
    t = max(0.0, min(1.0, (apx * abx + apy * aby) / ab2))
    fx, fy = ax + t * abx, ay + t * aby
    return math.hypot(px - fx, py - fy)


def score_for_sender(person, sender, receiver) -> float:
    """Higher score = bigger CSI variance. Models a Fresnel-zone disturbance."""
    if person is None:
        return random.gauss(0.6, 0.15)  # quiet baseline
    d = perpendicular_distance(person[0], person[1],
                               sender["x"], sender["y"],
                               receiver["x"], receiver["y"])
    # Gaussian falloff with sigma=2m around the LOS
    motion_strength = 6.0 * math.exp(-(d ** 2) / (2 * 2.0 ** 2))
    return max(0.0, random.gauss(0.6, 0.15) + motion_strength)


def level_for(score: float) -> tuple[int, str]:
    if score < 1.5: return 0, "QUIET"
    if score < 4.0: return 1, "MOTION"
    return 2, "BUSY"


def room_at(x: float, y: float) -> str | None:
    for r in BUILDING["rooms"]:
        poly = r["polygon"]
        n = len(poly)
        inside = False
        for i in range(n):
            x1, y1 = poly[i]
            x2, y2 = poly[(i + 1) % n]
            if (y1 > y) != (y2 > y):
                xi = (x2 - x1) * (y - y1) / (y2 - y1 + 1e-9) + x1
                if x < xi:
                    inside = not inside
        if inside:
            return r["id"]
    return None


def interpolate_path(waypoints, hz: int = 10):
    """Yield (t_seconds, x, y, dwelling) along the path."""
    t = 0.0
    dt = 1.0 / hz
    px, py = waypoints[0][:2]
    yield (t, px, py, True)
    for (tx, ty, dwell) in waypoints:
        # walk from current to (tx,ty) at ~1 m/s
        speed_mps = 1.2
        dx, dy = tx - px, ty - py
        dist = math.hypot(dx, dy)
        steps_walk = max(1, int(dist / speed_mps * hz))
        for s in range(1, steps_walk + 1):
            t += dt
            x = px + dx * s / steps_walk
            y = py + dy * s / steps_walk
            yield (t, x, y, False)
        px, py = tx, ty
        # dwell
        for s in range(int(dwell * hz)):
            t += dt
            yield (t, px + random.gauss(0, 0.05), py + random.gauss(0, 0.05), True)


# ---- main ----
def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--scenario", default="walking",
                   choices=["walking", "two_persons", "fire", "trapped", "all"])
    p.add_argument("--minutes", type=float, default=3.0,
                   help="cap simulation length")
    p.add_argument("--clear", action="store_true",
                   help="drop demo collections before seeding")
    p.add_argument("--start-offset-min", type=float, default=0,
                   help="shift timestamps to N min ago (default: ends at now)")
    args = p.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    for d in (repo_root, Path(__file__).resolve().parent):
        if (d / ".env").exists():
            load_dotenv(d / ".env")
            break

    uri = os.environ.get("MONGODB_URI")
    if not uri or "USER:PASSWORD" in uri:
        print("error: MONGODB_URI not set in .env", file=sys.stderr)
        return 2

    client = MongoClient(uri, appname="ruview-demo-seed")
    client.admin.command("ping")
    db = client[os.environ.get("MONGODB_DB", "csi_demo")]
    print(f"connected → {db.name}", file=sys.stderr)

    if args.clear:
        for c in ("buildings", "sensors", "simulated_motion", "trajectories",
                  "vitals", "detections", "alerts", "hazards"):
            db[c].drop()
        print("dropped demo collections", file=sys.stderr)

    # 1. Building (upsert)
    db.buildings.replace_one({"_id": BUILDING["_id"]}, BUILDING, upsert=True)
    print(f"buildings: 1 doc ({BUILDING['name']})", file=sys.stderr)

    # 2. Sensors (upsert each)
    db.sensors.bulk_write([
        UpdateOne({"_id": s["_id"]}, {"$set": s}, upsert=True) for s in SENSORS
    ])
    print(f"sensors: {len(SENSORS)} docs", file=sys.stderr)

    receiver = next(s for s in SENSORS if s["type"] == "csi_receiver")
    senders = [s for s in SENSORS if s["type"] == "csi_sender"]

    # 3. Walk a person and synthesize motion docs
    if args.scenario in ("walking", "fire"):
        person_paths = [waypoints_walking()]
    elif args.scenario == "two_persons":
        a, b = waypoints_two_persons()
        person_paths = [a, b]
    elif args.scenario == "trapped":
        person_paths = [waypoints_trapped()]
    else:  # all — combine two persons + a trapped victim
        a, b = waypoints_two_persons()
        person_paths = [a, b, waypoints_trapped()]

    # absolute time anchor: end the simulation at "now" so it lines up with live UI
    end_time = datetime.now(tz=timezone.utc) - timedelta(minutes=args.start_offset_min)
    # collect all per-person samples first to find total duration
    per_person_samples = []
    total_seconds = 0.0
    for path in person_paths:
        samples = list(interpolate_path(path, hz=10))
        per_person_samples.append(samples)
        total_seconds = max(total_seconds, samples[-1][0])
    total_seconds = min(total_seconds, args.minutes * 60)
    start_time = end_time - timedelta(seconds=total_seconds)

    motion_buf, traj_buf, detection_buf = [], [], []
    vitals_buf: list[dict] = []
    alerts_buf: list[dict] = []
    last_room_per_person: dict[int, str | None] = {}
    # immobility tracker: when did the person last move >0.5m?
    last_motion_ts: dict[int, datetime] = {}
    immobility_alert_fired: dict[int, bool] = {}
    last_xy: dict[int, tuple[float, float]] = {}

    for pid, samples in enumerate(per_person_samples):
        for (t_s, px, py, dwelling) in samples:
            if t_s > total_seconds:
                break
            ts = start_time + timedelta(seconds=t_s)

            # one motion doc per sender per tick (≈10 Hz)
            for s in senders:
                score = score_for_sender((px, py), s, receiver)
                level, label = level_for(score)
                motion_buf.append({
                    "ts": ts, "node": "rx-01", "sender_id": s["sender_id"],
                    "score": round(score, 4), "level": level, "label": label,
                    "source": "sim",
                    "person_xy": [round(px, 2), round(py, 2)],
                })

            # trajectory point ~2 Hz (subsample)
            if int(t_s * 10) % 5 == 0:
                traj_buf.append({
                    "ts": ts, "person_id": f"p{pid+1}",
                    "x": round(px, 2), "y": round(py, 2),
                    "speed_mps": 0 if dwelling else 1.2,
                    "confidence": round(random.uniform(0.7, 0.95), 2),
                    "source": "sim",
                })

            # detection event when person changes rooms
            cur_room = room_at(px, py)
            prev_room = last_room_per_person.get(pid)
            if cur_room != prev_room:
                if cur_room is not None:
                    detection_buf.append({
                        "ts": ts, "type": "person_entered",
                        "person_id": f"p{pid+1}",
                        "room": cur_room,
                        "x": round(px, 2), "y": round(py, 2),
                        "confidence": round(random.uniform(0.75, 0.95), 2),
                        "source": "sim",
                    })
                last_room_per_person[pid] = cur_room

            # vitals: emit ~1 Hz per person
            if int(t_s * 10) % 10 == 0:
                # Heart rate: resting 65-75, elevated when moving (~+25), small noise.
                # Breathing: 12-16 at rest, 18-26 when moving.
                # If we've been immobile a while, model panic/injury — HR rises then falls.
                seconds_immobile = 0
                if pid in last_motion_ts:
                    seconds_immobile = (ts - last_motion_ts[pid]).total_seconds()

                if dwelling and seconds_immobile > 30:
                    # injured / unconscious — HR drops, breathing shallow
                    hr = max(50, 90 - (seconds_immobile - 30) * 0.4) + random.gauss(0, 2)
                    br = max(8,  18 - (seconds_immobile - 30) * 0.1) + random.gauss(0, 1)
                    vitals_conf = round(random.uniform(0.55, 0.78), 2)
                else:
                    walking_bump = 0 if dwelling else 25
                    hr = 70 + walking_bump + random.gauss(0, 3)
                    br = 14 + (walking_bump * 0.4) + random.gauss(0, 1)
                    vitals_conf = round(random.uniform(0.78, 0.93), 2)
                vitals_buf.append({
                    "ts": ts, "person_id": f"p{pid+1}",
                    "heart_rate_bpm": round(hr, 1),
                    "breathing_rate_bpm": round(br, 1),
                    "x": round(px, 2), "y": round(py, 2),
                    "room": cur_room,
                    "confidence": vitals_conf,
                    "source": "sim",
                })

            # immobility tracker: did this person move >0.5m since last sample?
            prev_xy = last_xy.get(pid)
            moved_far = (prev_xy is None or math.hypot(px - prev_xy[0], py - prev_xy[1]) > 0.4)
            if moved_far:
                last_motion_ts[pid] = ts
                last_xy[pid] = (px, py)
                immobility_alert_fired[pid] = False
            elif (pid in last_motion_ts
                  and (ts - last_motion_ts[pid]).total_seconds() >= 30
                  and not immobility_alert_fired.get(pid, False)):
                # 30 sec immobile → fire alert once
                alerts_buf.append({
                    "ts": ts, "type": "person_immobile",
                    "severity": "high",
                    "person_id": f"p{pid+1}",
                    "room": cur_room,
                    "x": round(px, 2), "y": round(py, 2),
                    "details": "no significant movement for 30s — possible incapacitation",
                    "source": "sim",
                })
                immobility_alert_fired[pid] = True

    if motion_buf:
        db.simulated_motion.insert_many(motion_buf, ordered=False)
        db.simulated_motion.create_index([("ts", ASCENDING)])
        db.simulated_motion.create_index([("sender_id", ASCENDING), ("ts", ASCENDING)])
    if traj_buf:
        db.trajectories.insert_many(traj_buf, ordered=False)
        db.trajectories.create_index([("ts", ASCENDING)])
        db.trajectories.create_index([("person_id", ASCENDING), ("ts", ASCENDING)])
    if vitals_buf:
        db.vitals.insert_many(vitals_buf, ordered=False)
        db.vitals.create_index([("ts", ASCENDING)])
        db.vitals.create_index([("person_id", ASCENDING), ("ts", ASCENDING)])
    if detection_buf:
        db.detections.insert_many(detection_buf, ordered=False)
        db.detections.create_index([("ts", ASCENDING)])
    if alerts_buf:
        db.alerts.insert_many(alerts_buf, ordered=False)
        db.alerts.create_index([("ts", ASCENDING)])
        db.alerts.create_index([("severity", ASCENDING), ("ts", ASCENDING)])
    print(f"simulated_motion: {len(motion_buf)} docs", file=sys.stderr)
    print(f"trajectories:     {len(traj_buf)} docs", file=sys.stderr)
    print(f"vitals:           {len(vitals_buf)} docs", file=sys.stderr)
    print(f"detections:       {len(detection_buf)} docs", file=sys.stderr)
    print(f"alerts:           {len(alerts_buf)} docs", file=sys.stderr)

    # 4. Hazards (fire scenario adds smoke + temperature spikes)
    hazard_buf = []
    if args.scenario in ("fire", "all"):
        # fire originates in Room B at t = 60s, spreads
        fire_start = start_time + timedelta(seconds=60)
        for i in range(40):
            ts = fire_start + timedelta(seconds=i * 5)
            intensity = min(1.0, 0.1 + i * 0.025)
            hazard_buf.append({
                "ts": ts, "type": "smoke", "room": "room_b",
                "x": 16, "y": 4, "intensity": round(intensity, 3),
                "temperature_c": round(25 + intensity * 200, 1),
                "co_ppm": round(intensity * 1500, 0),
                "source": "sim",
            })
        # alarm event
        hazard_buf.append({
            "ts": fire_start + timedelta(seconds=10),
            "type": "alarm_triggered",
            "alarm_id": "fire-alarm-1",
            "room": "room_b",
            "source": "sim",
        })
        # structural collapse risk warning at later time
        hazard_buf.append({
            "ts": fire_start + timedelta(seconds=120),
            "type": "structural_warning",
            "room": "room_b",
            "details": "ceiling temperature exceeds 200°C — possible collapse",
            "source": "sim",
        })
    if hazard_buf:
        db.hazards.insert_many(hazard_buf, ordered=False)
        db.hazards.create_index([("ts", ASCENDING)])
    print(f"hazards:          {len(hazard_buf)} docs", file=sys.stderr)

    print("\nseed complete. quick checks:")
    for c in ("buildings", "sensors", "simulated_motion", "trajectories",
              "vitals", "detections", "alerts", "hazards"):
        print(f"  db.{c}.countDocuments()  →  {db[c].count_documents({})}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
