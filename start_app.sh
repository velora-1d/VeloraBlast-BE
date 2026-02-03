#!/bin/bash

echo "🚀 Starting Velora Blast System..."

# This script is located in velora-blast-backend
# It starts the backend here and the frontend in the adjacent folder

# Kill existing processes on ports 8000 (API) and 3000 (Frontend)
fuser -k 8000/tcp 2>/dev/null
fuser -k 3000/tcp 2>/dev/null

# Start Backend
echo "🔹 Starting Backend (FastAPI)..."
# We are already in velora-blast-backend
uvicorn api:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
echo "   PID: $BACKEND_PID"

# Wait for backend
sleep 2

# Start Frontend (assuming it is in the adjacent folder)
echo "🔹 Starting Frontend (Next.js)..."
if [ -d "../velora-blast-frontend" ]; then
    cd "../velora-blast-frontend"
    npm run dev -- -p 3000 &
    FRONTEND_PID=$!
    echo "   PID: $FRONTEND_PID"
    cd - > /dev/null
else
    echo "⚠️  Frontend folder not found at ../velora-blast-frontend"
fi

echo "✅ App is running!"
echo "👉 Open http://localhost:3000 in your browser"
echo "Press [CTRL+C] to stop everything."

# Wait for processes
if [ -n "$FRONTEND_PID" ]; then
    wait $BACKEND_PID $FRONTEND_PID
else
    wait $BACKEND_PID
fi
