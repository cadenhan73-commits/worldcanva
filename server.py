#!/usr/bin/env python3
"""
WorldCanva Server
A real-time collaborative drawing canvas.
"""

import base64
import io
import json
import os
import random
import atexit
from threading import Lock

import requests
from flask import Flask, send_from_directory, request
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'worldcanva-secret-key'
socketio = SocketIO(app, cors_allowed_origins="*")

STATE_FILE = 'canvas-state.json'
strokes = []
strokes_lock = Lock()
pending_strokes = []
pending_lock = Lock()
user_names = {}

CANVAS_SIZE = 1500
SNAPSHOT_THRESHOLD = 500

# Supabase REST API config (optional — falls back to local file if not configured)
SUPABASE_URL = os.environ.get('SUPABASE_URL', '').rstrip('/')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')


def supabase_headers(prefer_minimal=True):
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer_minimal:
        headers["Prefer"] = "return=minimal"
    else:
        headers["Prefer"] = "return=representation"
    return headers


ADJECTIVES = [
    "Happy", "Sleepy", "Curious", "Brave", "Silly", "Clever", "Wild", "Gentle",
    "Fierce", "Lazy", "Bright", "Mysterious", "Quick", "Chill", "Hyper", "Zen",
    "Grumpy", "Jolly", "Ninja", "Cosmic", "Sparkly", "Dizzy", "Funky", "Magic"
]

ANIMALS = [
    "Penguin", "Fox", "Octopus", "Dragon", "Koala", "Otter", "Raccoon",
    "Llama", "Platypus", "Axolotl", "Capybara", "Narwhal", "Quokka", "Panda",
    "Sloth", "Hedgehog", "Walrus", "Mongoose", "Falcon", "Turtle", "Parrot",
    "Wombat", "Meerkat", "Leopard", "Dolphin", "Beaver", "Owl", "Mantis"
]


def generate_name():
    """Generate a random user name."""
    return f"{random.choice(ADJECTIVES)} {random.choice(ANIMALS)}"


def flush_pending_strokes():
    """Flush batched strokes to Supabase in the background."""
    global pending_strokes
    with pending_lock:
        if not pending_strokes:
            return
        batch = pending_strokes.copy()
        pending_strokes.clear()

    if not SUPABASE_URL or not SUPABASE_KEY:
        return

    try:
        url = f"{SUPABASE_URL}/rest/v1/strokes"
        resp = requests.post(url, json=batch, headers=supabase_headers(), timeout=15)
        resp.raise_for_status()
        print(f"Flushed {len(batch)} strokes to Supabase")
    except Exception as e:
        print(f"Failed to flush strokes to Supabase: {e}")


def background_flusher():
    """Periodically flush pending strokes to Supabase."""
    while True:
        socketio.sleep(3)
        flush_pending_strokes()


def get_recent_strokes():
    """Return strokes after the latest snapshot, or all strokes if no snapshot."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return strokes

    try:
        url = f"{SUPABASE_URL}/rest/v1/snapshots?select=timestamp&order=timestamp.desc&limit=1"
        resp = requests.get(url, headers=supabase_headers(), timeout=5)
        if resp.status_code == 200:
            snapshots = resp.json()
            if snapshots:
                snapshot_time = snapshots[0]['timestamp']
                return [s for s in strokes if s.get('timestamp', 0) > snapshot_time]
    except Exception as e:
        print(f"Failed to get snapshot timestamp: {e}")

    return strokes


def generate_snapshot():
    """Render all strokes to a PNG and save to Supabase."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("Pillow not installed, skipping snapshot generation")
        return

    with strokes_lock:
        if not strokes:
            return
        strokes_copy = strokes.copy()
        last_timestamp = strokes_copy[-1].get('timestamp', 0)

    try:
        img = Image.new('RGBA', (CANVAS_SIZE, CANVAS_SIZE), (255, 255, 255, 255))
        draw = ImageDraw.Draw(img)

        for stroke in strokes_copy:
            x0, y0 = stroke['x0'], stroke['y0']
            x1, y1 = stroke['x1'], stroke['y1']
            size = int(stroke.get('size', 4))
            tool = stroke.get('tool', 'pen')

            if tool == 'eraser':
                draw.line([(x0, y0), (x1, y1)], fill=(255, 255, 255, 255), width=size)
            else:
                color = stroke.get('color', '#000000')
                if color.startswith('#') and len(color) == 7:
                    r = int(color[1:3], 16)
                    g = int(color[3:5], 16)
                    b = int(color[5:7], 16)
                else:
                    r, g, b = 0, 0, 0
                draw.line([(x0, y0), (x1, y1)], fill=(r, g, b, 255), width=size)

        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

        # Save to Supabase
        url = f"{SUPABASE_URL}/rest/v1/snapshots"
        headers = supabase_headers(prefer_minimal=False)
        resp = requests.post(url, json={
            'image_base64': img_base64,
            'stroke_count': len(strokes_copy),
            'timestamp': last_timestamp
        }, headers=headers, timeout=15)
        resp.raise_for_status()

        new_snapshot = resp.json()[0]
        print(f"Generated snapshot with {len(strokes_copy)} strokes (id={new_snapshot['id']})")

        # Delete old snapshots
        try:
            del_url = f"{SUPABASE_URL}/rest/v1/snapshots?id=neq.{new_snapshot['id']}"
            requests.delete(del_url, headers=supabase_headers(), timeout=10)
        except Exception as e:
            print(f"Failed to clean up old snapshots: {e}")

    except Exception as e:
        print(f"Failed to generate snapshot: {e}")


def load_state():
    """Load canvas state from Supabase (preferred) or local file."""
    global strokes

    if SUPABASE_URL and SUPABASE_KEY:
        try:
            url = f"{SUPABASE_URL}/rest/v1/strokes?select=x0,y0,x1,y1,color,size,tool,timestamp&order=timestamp.asc"
            resp = requests.get(url, headers=supabase_headers(), timeout=10)
            resp.raise_for_status()
            strokes = resp.json()
            print(f"Loaded {len(strokes)} strokes from Supabase")
            return
        except Exception as e:
            print(f"Failed to load from Supabase: {e}")

    # Fallback to local file
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                data = json.load(f)
                strokes = data.get('strokes', [])
            print(f"Loaded {len(strokes)} strokes from {STATE_FILE}")
        except Exception as e:
            print(f"Failed to load state: {e}")
            strokes = []
    else:
        strokes = []


def save_state():
    """Save canvas state to local file as a fallback."""
    with strokes_lock:
        try:
            with open(STATE_FILE, 'w') as f:
                json.dump({'strokes': strokes}, f)
            print(f"Saved {len(strokes)} strokes to {STATE_FILE}")
        except Exception as e:
            print(f"Failed to save state: {e}")


@app.route('/')
def index():
    return send_from_directory('public', 'index.html')


@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('public', path)


@socketio.on('connect')
def handle_connect():
    name = generate_name()
    user_names[request.sid] = {
        'name': name,
        'color': f"hsl({random.randint(0, 360)}, 70%, 50%)"
    }
    print(f"Connected: {name} ({request.sid})")
    emit('assign-name', user_names[request.sid])

    # Send snapshot + recent strokes
    snapshot_base64 = None
    if SUPABASE_URL and SUPABASE_KEY:
        try:
            url = f"{SUPABASE_URL}/rest/v1/snapshots?select=image_base64&order=timestamp.desc&limit=1"
            resp = requests.get(url, headers=supabase_headers(), timeout=5)
            if resp.status_code == 200:
                snapshots = resp.json()
                if snapshots:
                    snapshot_base64 = snapshots[0]['image_base64']
        except Exception as e:
            print(f"Failed to get snapshot for new user: {e}")

    recent_strokes = get_recent_strokes()

    emit('canvas-state', {
        'strokes': recent_strokes,
        'snapshot': snapshot_base64
    })

    emit('user-count', {'count': len(user_names)}, broadcast=True)


@socketio.on('disconnect')
def handle_disconnect():
    name = user_names.pop(request.sid, {}).get('name', 'Unknown')
    print(f"Disconnected: {name} ({request.sid})")
    emit('user-count', {'count': len(user_names)}, broadcast=True)
    emit('cursor-remove', {'id': request.sid}, broadcast=True)


@socketio.on('draw')
def handle_draw(data):
    with strokes_lock:
        strokes.append(data)
        stroke_count = len(strokes)

    # Trigger snapshot generation every N strokes
    if stroke_count > 0 and stroke_count % SNAPSHOT_THRESHOLD == 0:
        socketio.start_background_task(generate_snapshot)

    # Queue stroke for batched background save (no blocking!)
    if SUPABASE_URL and SUPABASE_KEY:
        with pending_lock:
            pending_strokes.append(data)

    emit('draw', data, broadcast=True, include_self=False)


@socketio.on('cursor-move')
def handle_cursor_move(data):
    data['id'] = request.sid
    data['user'] = user_names.get(request.sid, {})
    emit('cursor-move', data, broadcast=True, include_self=False)


@socketio.on('undo')
def handle_undo():
    # Flush any pending strokes first so undo is accurate
    flush_pending_strokes()

    with strokes_lock:
        if strokes:
            strokes.pop()
            if SUPABASE_URL and SUPABASE_KEY:
                try:
                    url = f"{SUPABASE_URL}/rest/v1/strokes?select=id&order=timestamp.desc&limit=1"
                    resp = requests.get(url, headers=supabase_headers(), timeout=10)
                    resp.raise_for_status()
                    result = resp.json()
                    if result:
                        last_id = result[0]['id']
                        del_url = f"{SUPABASE_URL}/rest/v1/strokes?id=eq.{last_id}"
                        requests.delete(del_url, headers=supabase_headers(), timeout=10)
                except Exception as e:
                    print(f"Failed to undo in Supabase: {e}")

    recent_strokes = get_recent_strokes()
    emit('canvas-state', {
        'strokes': recent_strokes,
        'snapshot': None
    }, broadcast=True)


if __name__ == '__main__':
    load_state()

    # Generate initial snapshot if there are many strokes on startup
    if len(strokes) > SNAPSHOT_THRESHOLD:
        print(f"Found {len(strokes)} strokes on startup, generating initial snapshot...")
        generate_snapshot()

    # Start background stroke flusher
    socketio.start_background_task(background_flusher)

    atexit.register(flush_pending_strokes)
    atexit.register(save_state)

    print("=" * 50)
    print("  🎨 WorldCanva Server")
    print("=" * 50)
    print("  Open http://localhost:8080 in your browser")
    print("=" * 50)

    try:
        port = int(os.environ.get('PORT', 8080))
        socketio.run(app, host='0.0.0.0', port=port, debug=False)
    except KeyboardInterrupt:
        save_state()
        print("\nServer stopped. State saved.")
