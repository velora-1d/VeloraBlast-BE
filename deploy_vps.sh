#!/bin/bash

# Configuration
VPS_USER="ubuntu"
VPS_IP="43.156.132.218"
PROJECT_DIR="~/VeloraBlast"
LOCAL_DIR="/home/mahinutsmannawawi/Mahin Project/VeloraBlast/VeloraBlast-BE/"

echo "🚀 Deploying VeloraBlast Backend to $VPS_IP..."

# 1. Create Directory on VPS
ssh -o StrictHostKeyChecking=no "$VPS_USER@$VPS_IP" "mkdir -p $PROJECT_DIR"

# 2. Sync Files (excluding heavy/temp files)
rsync -avz \
  --exclude '.git' \
  --exclude '.env' \
  --exclude 'venv' \
  --exclude '__pycache__' \
  --exclude 'logs' \
  --exclude 'results' \
  "$LOCAL_DIR" "$VPS_USER@$VPS_IP:$PROJECT_DIR"

# 3. Copy Production .env (Optional: You might want to manage this separately for security)
# For now, we assume the user will configure .env or we push a safe version.
# If you have a local .env.production, use that.
# rsync -avz .env.production "$VPS_USER@$VPS_IP:$PROJECT_DIR/.env"

echo "🛠 Building and Restarting Services..."

# 4. Remote Docker Compose Up
ssh -o StrictHostKeyChecking=no "$VPS_USER@$VPS_IP" "cd $PROJECT_DIR && \
  docker-compose down && \
  docker-compose up -d --build"

echo "✅ Deployment Complete!"
echo "API Available at: http://$VPS_IP:8000/docs"
