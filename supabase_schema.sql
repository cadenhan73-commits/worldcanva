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

-- Optional: index for fast ordering by timestamp
CREATE INDEX IF NOT EXISTS idx_strokes_timestamp ON strokes(timestamp);
