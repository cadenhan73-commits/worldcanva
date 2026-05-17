-- Run this in your Supabase SQL Editor (Project Settings -> SQL Editor -> New query)

CREATE TABLE IF NOT EXISTS strokes (
    id SERIAL PRIMARY KEY,
    x0 REAL NOT NULL,
    y0 REAL NOT NULL,
    x1 REAL NOT NULL,
    y1 REAL NOT NULL,
    color TEXT NOT NULL,
    size INTEGER NOT NULL,
    tool TEXT NOT NULL,
    timestamp BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_strokes_timestamp ON strokes(timestamp);

CREATE TABLE IF NOT EXISTS snapshots (
    id SERIAL PRIMARY KEY,
    image_base64 TEXT NOT NULL,
    stroke_count INTEGER NOT NULL DEFAULT 0,
    timestamp BIGINT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
