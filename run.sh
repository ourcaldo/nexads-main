
#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== NexAds Complete Setup Script ===${NC}"

# Function to run commands with error handling
run_command() {
    local cmd="$1"
    local check_error="${2:-true}"
    
    echo -e "${YELLOW}Running: $cmd${NC}"
    if eval "$cmd"; then
        return 0
    else
        if [ "$check_error" = "true" ]; then
            echo -e "${RED}Error running: $cmd${NC}"
            return 1
        else
            echo -e "${YELLOW}Warning: $cmd failed (continuing)${NC}"
            return 0
        fi
    fi
}

# Get user input
echo "=== NexAds Web Panel Setup ==="
read -p "Domain (e.g., google.com or localhost): " DOMAIN
read -p "Frontend port [4000]: " FRONTEND_PORT
read -p "Backend port [8000]: " BACKEND_PORT

DOMAIN=${DOMAIN:-localhost}
FRONTEND_PORT=${FRONTEND_PORT:-4000}
BACKEND_PORT=${BACKEND_PORT:-8000}

# Determine SSL based on domain
if [[ "$DOMAIN" == "localhost"* ]] || [[ "$DOMAIN" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    SSL="false"
else
    SSL="true"
fi

echo -e "${GREEN}SSL will be $([ "$SSL" = "true" ] && echo "enabled" || echo "disabled") for $DOMAIN${NC}"

# Create .env file
cat > .env << EOF
DOMAIN=$DOMAIN
FRONTEND_PORT=$FRONTEND_PORT
BACKEND_PORT=$BACKEND_PORT
SSL=$SSL
USERNAME=admin
PASSWORD=admin123
EOF

echo -e "${GREEN}✓ .env file created${NC}"

# Clean up ONLY nexads-related processes and configurations
echo -e "${YELLOW}Cleaning up previous nexads installation...${NC}"

# Stop and delete ONLY nexads PM2 processes
run_command "pm2 stop nexads-backend" false
run_command "pm2 stop nexads-frontend" false
run_command "pm2 delete nexads-backend" false
run_command "pm2 delete nexads-frontend" false

# Stop nexads service
run_command "sudo systemctl stop nexads-automation.service" false
run_command "sudo systemctl disable nexads-automation.service" false

# Remove ONLY nexads nginx config
run_command "sudo rm -f /etc/nginx/sites-enabled/nexads" false
run_command "sudo rm -f /etc/nginx/sites-available/nexads" false

# Remove ONLY nexads SSL certificates
run_command "sudo certbot delete --cert-name $DOMAIN --non-interactive" false

# Reload nginx
run_command "sudo systemctl reload nginx" false

echo -e "${GREEN}✓ Previous nexads installation cleaned up${NC}"

# Install dependencies
echo -e "${YELLOW}Installing dependencies...${NC}"
run_command "sudo apt update"
run_command "sudo apt install -y python3-pip nginx certbot python3-certbot-nginx nodejs npm"

# Install core automation dependencies
if [ -f "core/requirements.txt" ]; then
    run_command "pip3 install -r core/requirements.txt"
fi

# Install PM2 globally if not already installed
if ! command -v pm2 &> /dev/null; then
    run_command "sudo npm install -g pm2"
fi

echo -e "${GREEN}✓ Dependencies installed${NC}"

# Setup backend
echo -e "${YELLOW}Setting up backend...${NC}"
mkdir -p backend
run_command "pip3 install fastapi uvicorn python-multipart python-jose[cryptography] passlib[bcrypt] python-dotenv"
echo -e "${GREEN}✓ Backend setup complete${NC}"

# Setup frontend
echo -e "${YELLOW}Setting up frontend...${NC}"
if [ ! -d "frontend" ]; then
    run_command "npx create-react-app frontend"
fi

cd frontend
run_command "npm install axios react-router-dom @mui/material @emotion/react @emotion/styled @mui/icons-material"
run_command "npm run build"
cd ..

echo -e "${GREEN}✓ Frontend setup complete${NC}"

# Setup nginx
echo -e "${YELLOW}Setting up nginx...${NC}"
CURRENT_DIR=$(pwd)

cat > /tmp/nexads << EOF
server {
    listen 80;
    server_name $DOMAIN;

    location / {
        root $CURRENT_DIR/frontend/build;
        index index.html;
        try_files \$uri \$uri/ /index.html;
    }

    location /api {
        proxy_pass http://127.0.0.1:$BACKEND_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

run_command "sudo mv /tmp/nexads /etc/nginx/sites-available/nexads"
run_command "sudo ln -sf /etc/nginx/sites-available/nexads /etc/nginx/sites-enabled/nexads"

if run_command "sudo nginx -t"; then
    run_command "sudo systemctl reload nginx"
    echo -e "${GREEN}✓ Nginx configured${NC}"
else
    echo -e "${RED}✗ Nginx configuration failed${NC}"
    exit 1
fi

# Setup SSL if needed
if [ "$SSL" = "true" ]; then
    echo -e "${YELLOW}Setting up SSL...${NC}"
    
    # Non-interactive SSL setup with proper email and agreement flags
    SSL_CMD="sudo certbot --nginx -d $DOMAIN --non-interactive --agree-tos --register-unsafely-without-email --redirect"
    
    if run_command "$SSL_CMD" false; then
        echo -e "${GREEN}✓ SSL certificate installed${NC}"
    else
        echo -e "${YELLOW}⚠ SSL setup failed - continuing without SSL${NC}"
        echo -e "${YELLOW}Note: Make sure your domain points to this server's IP address${NC}"
        echo -e "${YELLOW}You can run the following command later to setup SSL:${NC}"
        echo -e "${YELLOW}sudo certbot --nginx -d $DOMAIN --non-interactive --agree-tos --register-unsafely-without-email${NC}"
        
        # Update SSL to false in .env
        sed -i 's/SSL=true/SSL=false/' .env
        SSL="false"
    fi
fi

# Start services
echo -e "${YELLOW}Starting services...${NC}"

# Start backend with PM2
BACKEND_CMD="cd $CURRENT_DIR && python3 -m uvicorn backend.main:app --host 0.0.0.0 --port $BACKEND_PORT"
run_command "pm2 start \"$BACKEND_CMD\" --name nexads-backend"

# Save PM2 processes
run_command "pm2 save"
run_command "pm2 startup" false

echo -e "${GREEN}✓ Services started${NC}"

# Display system information
echo ""
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}           NEXADS CONTROL PANEL - SYSTEM INFO${NC}"
echo -e "${GREEN}============================================================${NC}"

echo -e "\n${YELLOW}📋 ENVIRONMENT VARIABLES:${NC}"
echo "   DOMAIN: $DOMAIN"
echo "   FRONTEND_PORT: $FRONTEND_PORT"
echo "   BACKEND_PORT: $BACKEND_PORT"
echo "   SSL: $SSL"
echo "   USERNAME: admin"
echo "   PASSWORD: admin123"

PROTOCOL=$([ "$SSL" = "true" ] && echo "https" || echo "http")
echo -e "\n${YELLOW}🌐 ACCESS URLS:${NC}"
echo "   Frontend: $PROTOCOL://$DOMAIN"
echo "   Backend API: $PROTOCOL://$DOMAIN/api"
echo "   Health Check: $PROTOCOL://$DOMAIN/api/health"

echo -e "\n${YELLOW}🔒 SSL STATUS:${NC}"
if [ "$SSL" = "true" ]; then
    if sudo certbot certificates 2>/dev/null | grep -q "$DOMAIN"; then
        echo "   ✓ SSL Certificate: ACTIVE"
    else
        echo "   ✗ SSL Certificate: FAILED/NOT FOUND"
    fi
else
    echo "   ⚠ SSL Certificate: DISABLED"
fi

echo -e "\n${YELLOW}⚙️ NGINX CONFIGURATION:${NC}"
echo "   Config File: /etc/nginx/sites-available/nexads"
echo "   Enabled Link: /etc/nginx/sites-enabled/nexads"

NGINX_STATUS=$(sudo systemctl is-active nginx 2>/dev/null)
echo "   Nginx Status: $([ "$NGINX_STATUS" = "active" ] && echo "✓ RUNNING" || echo "✗ NOT RUNNING")"

echo -e "\n${YELLOW}🚀 SERVICE STATUS:${NC}"
if pm2 list | grep -q "nexads-backend"; then
    echo "   ✓ Backend Service: RUNNING (PM2)"
else
    echo "   ✗ Backend Service: NOT RUNNING"
fi

echo -e "\n${YELLOW}🔐 AUTHENTICATION:${NC}"
echo "   Username: admin"
echo "   Password: admin123"

echo -e "\n${GREEN}============================================================${NC}"
echo -e "${GREEN}Setup completed! Your NexAds control panel is ready.${NC}"
if [ "$SSL" = "false" ] && [ "$DOMAIN" != "localhost" ]; then
    echo -e "\n${YELLOW}Note: SSL setup failed. To retry SSL later, run:${NC}"
    echo -e "${YELLOW}sudo certbot --nginx -d $DOMAIN --non-interactive --agree-tos --register-unsafely-without-email${NC}"
fi
echo -e "${GREEN}============================================================${NC}"
