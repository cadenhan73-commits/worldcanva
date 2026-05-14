/**
 * WorldCanva - Real-time collaborative drawing canvas
 */

// Canvas setup
const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d');

// State
let isDrawing = false;
let lastX = 0;
let lastY = 0;
let currentTool = 'pen';
let currentColor = '#000000';
let currentSize = 4;
let myName = 'You';
let socket = null;

// UI elements
const toolPen = document.getElementById('tool-pen');
const toolEraser = document.getElementById('tool-eraser');
const brushSize = document.getElementById('brush-size');
const sizeValue = document.getElementById('size-value');
const customColor = document.getElementById('custom-color');
const clearBtn = document.getElementById('clear-btn');
const userNameEl = document.getElementById('user-name');
const userCountEl = document.getElementById('user-count');
const colorBtns = document.querySelectorAll('.color-btn');
const cursorLayer = document.getElementById('cursor-layer');

// Remote cursors
const remoteCursors = new Map();

// Resize canvas
function resizeCanvas() {
    const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    ctx.putImageData(imageData, 0, 0);
}

window.addEventListener('resize', () => {
    resizeCanvas();
});

// Initialize canvas size
canvas.width = window.innerWidth;
canvas.height = window.innerHeight;

// Drawing functions
function getPoint(e) {
    if (e.touches && e.touches.length > 0) {
        return {
            x: e.touches[0].clientX,
            y: e.touches[0].clientY
        };
    }
    return {
        x: e.clientX,
        y: e.clientY
    };
}

function startDrawing(e) {
    isDrawing = true;
    const point = getPoint(e);
    lastX = point.x;
    lastY = point.y;
    e.preventDefault();
}

function draw(e) {
    if (!isDrawing) return;
    
    const point = getPoint(e);
    const x0 = lastX;
    const y0 = lastY;
    const x1 = point.x;
    const y1 = point.y;
    
    const stroke = {
        x0, y0, x1, y1,
        color: currentColor,
        size: currentSize,
        tool: currentTool,
        timestamp: Date.now()
    };
    
    drawStroke(stroke);
    
    if (socket && socket.connected) {
        socket.emit('draw', stroke);
    }
    
    lastX = x1;
    lastY = y1;
    e.preventDefault();
}

function stopDrawing() {
    isDrawing = false;
}

function drawStroke(stroke) {
    ctx.save();
    ctx.beginPath();
    ctx.moveTo(stroke.x0, stroke.y0);
    ctx.lineTo(stroke.x1, stroke.y1);
    
    if (stroke.tool === 'eraser') {
        ctx.globalCompositeOperation = 'destination-out';
        ctx.strokeStyle = 'rgba(0,0,0,1)';
    } else {
        ctx.globalCompositeOperation = 'source-over';
        ctx.strokeStyle = stroke.color;
    }
    
    ctx.lineWidth = stroke.size;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.stroke();
    ctx.restore();
}

function clearCanvas() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
}

// Event listeners for drawing
canvas.addEventListener('mousedown', startDrawing);
canvas.addEventListener('mousemove', draw);
canvas.addEventListener('mouseup', stopDrawing);
canvas.addEventListener('mouseout', stopDrawing);

canvas.addEventListener('touchstart', startDrawing, { passive: false });
canvas.addEventListener('touchmove', draw, { passive: false });
canvas.addEventListener('touchend', stopDrawing);
canvas.addEventListener('touchcancel', stopDrawing);

// Cursor tracking
canvas.addEventListener('mousemove', (e) => {
    if (socket && socket.connected) {
        socket.emit('cursor-move', {
            x: e.clientX,
            y: e.clientY
        });
    }
});

// Tool selection
toolPen.addEventListener('click', () => {
    currentTool = 'pen';
    toolPen.classList.add('active');
    toolEraser.classList.remove('active');
    canvas.style.cursor = 'crosshair';
});

toolEraser.addEventListener('click', () => {
    currentTool = 'eraser';
    toolEraser.classList.add('active');
    toolPen.classList.remove('active');
    canvas.style.cursor = 'cell';
});

// Brush size
brushSize.addEventListener('input', (e) => {
    currentSize = parseInt(e.target.value);
    sizeValue.textContent = currentSize;
});

// Color palette
colorBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        colorBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentColor = btn.dataset.color;
        customColor.value = currentColor;
        if (currentTool === 'eraser') {
            currentTool = 'pen';
            toolPen.classList.add('active');
            toolEraser.classList.remove('active');
            canvas.style.cursor = 'crosshair';
        }
    });
});

customColor.addEventListener('input', (e) => {
    currentColor = e.target.value;
    colorBtns.forEach(b => b.classList.remove('active'));
    if (currentTool === 'eraser') {
        currentTool = 'pen';
        toolPen.classList.add('active');
        toolEraser.classList.remove('active');
        canvas.style.cursor = 'crosshair';
    }
});

// Clear button
clearBtn.addEventListener('click', () => {
    if (confirm('Clear the entire canvas for everyone? This cannot be undone!')) {
        if (socket && socket.connected) {
            socket.emit('clear-canvas');
        }
        clearCanvas();
    }
});

// Remote cursor management
function createCursorElement(id, user) {
    const el = document.createElement('div');
    el.className = 'remote-cursor';
    el.id = `cursor-${id}`;
    
    const color = user.color || '#3498db';
    
    el.innerHTML = `
        <svg viewBox="0 0 24 24" fill="${color}">
            <path d="M3 3l7.07 16.97 2.51-7.39 7.39-2.51L3 3z" stroke="white" stroke-width="1.5"/>
        </svg>
        <span class="remote-cursor-label" style="background:${color}">${escapeHtml(user.name || 'Anonymous')}</span>
    `;
    
    cursorLayer.appendChild(el);
    return el;
}

function updateCursor(id, x, y, user) {
    let el = remoteCursors.get(id);
    if (!el) {
        el = createCursorElement(id, user);
        remoteCursors.set(id, el);
    }
    el.style.transform = `translate(${x}px, ${y}px)`;
}

function removeCursor(id) {
    const el = remoteCursors.get(id);
    if (el) {
        el.remove();
        remoteCursors.delete(id);
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Socket.IO connection
function connectSocket() {
    socket = io();
    
    socket.on('connect', () => {
        console.log('Connected to WorldCanva!');
    });
    
    socket.on('assign-name', (data) => {
        myName = data.name;
        userNameEl.textContent = `🎨 ${myName}`;
        userNameEl.style.color = data.color;
    });
    
    socket.on('user-count', (data) => {
        userCountEl.textContent = `👥 ${data.count}`;
    });
    
    socket.on('canvas-state', (data) => {
        clearCanvas();
        if (data.strokes) {
            data.strokes.forEach(stroke => drawStroke(stroke));
        }
    });
    
    socket.on('draw', (data) => {
        drawStroke(data);
    });
    
    socket.on('clear-canvas', () => {
        clearCanvas();
    });
    
    socket.on('cursor-move', (data) => {
        updateCursor(data.id, data.x, data.y, data.user);
    });
    
    socket.on('cursor-remove', (data) => {
        removeCursor(data.id);
    });
    
    socket.on('disconnect', () => {
        userNameEl.textContent = 'Disconnected';
        userNameEl.style.color = '#e74c3c';
    });
    
    socket.on('connect_error', (err) => {
        console.error('Connection error:', err);
        userNameEl.textContent = 'Connection Error';
        userNameEl.style.color = '#e74c3c';
    });
}

// Initialize
connectSocket();

// Prevent scrolling on mobile
document.body.addEventListener('touchmove', (e) => {
    if (e.target === canvas) {
        e.preventDefault();
    }
}, { passive: false });
