#!/bin/bash

# Configuration
DOMAIN="blast-api.ve-lora.my.id"
EMAIL="nawawimahinutsman@gmail.com"
BACKEND_PORT=8000

# 1. Install Nginx and Certbot
echo "Installing Nginx and Certbot..."
sudo apt-get update
sudo apt-get install -y nginx certbot python3-certbot-nginx

# 2. Configure Nginx Reverse Proxy
echo "Configuring Nginx for $DOMAIN..."
cat <<EOF | sudo tee /etc/nginx/sites-available/velora-backend
server {
    server_name $DOMAIN;

    location / {
        proxy_pass http://localhost:$BACKEND_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

# 3. Enable Site
sudo ln -s /etc/nginx/sites-available/velora-backend /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl restart nginx

# 4. Request SSL Certificate
echo "Requesting SSL Certificate..."
sudo certbot --nginx -d $DOMAIN --non-interactive --agree-tos -m $EMAIL --redirect

echo "✅ SSL Setup Complete! Backend is now accessible at https://$DOMAIN"
