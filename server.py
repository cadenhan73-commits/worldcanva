#!/usr/bin/env python3
"""
WorldCanva Server
A real-time collaborative drawing canvas.
"""

import json
import os
import random
import atexit
from threading import Lock

from flask import Flask, send_from_directory, request
from flask_socketio import SocketIO, emit

# Supabase integration (optional — falls back to local file if not configured)
try:
    from supabase import create_client
    HAS_SUPABASE = True
except ImportError:
    HAS_SUPABASE = False

app = Flask(__name__)
app.config['SECRET_KEY'] = 'worldcanva-secret-key'
socketio = SocketIO(app, cors_allowed_origins="*")

STATE_FILE = 'canvas-state.json'
strokes = []
strokes_lock = Lock()
user_names = {}

# Initialize Supabase client if env vars are present
supabase = None
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')

if HAS_SUPABASE and SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("Connected to Supabase")
    except Exception as e:
        print(f"Failed to connect to Supabase: {e}")
        supabase = None

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


def load_state():
    """Load canvas state from Supabase (preferred) or local file."""
    global strokes

    if supabase:
        try:
            result = (
                supabase.table('strokes')
                .select('x0,y0,x1,y1,color,size,tool,timestamp')
                .order('timestamp')
                .execute()
            )
            strokes = result.data
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
    emit('canvas-state', {'strokes': strokes})
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
        if supabase:
            try:
                supabase.table('strokes').insert(data).execute()
            except Exception as e:
                print(f"Failed to save stroke to Supabase: {e}")
    emit('draw', data, broadcast=True, include_self=False)


@socketio.on('cursor-move')
def handle_cursor_move(data):
    data['id'] = request.sid
    data['user'] = user_names.get(request.sid, {})
    emit('cursor-move', data, broadcast=True, include_self=False)


@socketio.on('undo')
def handle_undo():
    with strokes_lock:
        if strokes:
            strokes.pop()
            if supabase:
                try:
                    result = (
                        supabase.table('strokes')
                        .select('id')
                        .order('timestamp', desc=True)
                        .limit(1)
                        .execute()
                    )
                    if result.data:
                        last_id = result.data[0]['id']
                        supabase.table('strokes').delete().eq('id', last_id).execute()
                except Exception as e:
                    print(f"Failed to undo in Supabase: {e}")
    save_state()
    emit('canvas-state', {'strokes': strokes}, broadcast=True)


if __name__ == '__main__':
    load_state()
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
