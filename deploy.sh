#!/bin/bash

# nexAds Web Interface Deployment Script
# Automatically configures and deploys the nexAds web interface

set -e  # Exit on any error

echo "🚀 nexAds Web Interface Deployment"
echo "=================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# Function to get local IP
get_local_ip() {
    ip route get 8.8.8.8 | awk -F"src " 'NR==1{split($2,a," ");print a[1]}'
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to cleanup previous deployment
cleanup_previous() {
    print_info "Cleaning up previous deployment..."
    
    # Stop PM2 processes
    pm2 delete nexads-backend 2>/dev/null || true
    pm2 delete nexads-frontend 2>/dev/null || true
    
    # Remove nginx configuration
    sudo rm -f /etc/nginx/sites-available/nexads 2>/dev/null || true
    sudo rm -f /etc/nginx/sites-enabled/nexads 2>/dev/null || true
    
    # Remove SSL certificates (only nexads related)
    if [ -d "/etc/letsencrypt/live" ]; then
        for domain_dir in /etc/letsencrypt/live/*/; do
            if [[ "$domain_dir" == *"nexads"* ]] || [[ "$domain_dir" == *"$DOMAIN"* ]]; then
                domain_name=$(basename "$domain_dir")
                sudo certbot delete --cert-name "$domain_name" --non-interactive 2>/dev/null || true
            fi
        done
    fi
    
    # Kill processes on our ports
    sudo fuser -k ${FRONTEND_PORT}/tcp 2>/dev/null || true
    sudo fuser -k ${BACKEND_PORT}/tcp 2>/dev/null || true
    
    # Reload nginx
    sudo nginx -t 2>/dev/null && sudo systemctl reload nginx 2>/dev/null || true
    
    print_status "Cleanup completed"
}

# Function to install system dependencies
install_system_deps() {
    print_info "Installing system dependencies..."
    
    # Update package list
    sudo apt update
    
    # Install Node.js 18.x
    if ! command_exists node || [[ $(node -v | cut -d'v' -f2 | cut -d'.' -f1) -lt 18 ]]; then
        print_info "Installing Node.js 18.x..."
        curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
        sudo apt-get install -y nodejs
    fi
    
    # Install PM2
    if ! command_exists pm2; then
        print_info "Installing PM2..."
        sudo npm install -g pm2
    fi
    
    # Install nginx
    if ! command_exists nginx; then
        print_info "Installing nginx..."
        sudo apt-get install -y nginx
    fi
    
    # Install certbot if SSL is enabled
    if [ "$SSL_ENABLED" = "true" ]; then
        if ! command_exists certbot; then
            print_info "Installing certbot..."
            sudo apt-get install -y certbot python3-certbot-nginx
        fi
    fi
    
    print_status "System dependencies installed"
}

# Function to install Python dependencies
install_python_deps() {
    print_info "Installing Python dependencies..."
    
    # Install core automation dependencies
    if [ -f "core/requirements.txt" ]; then
        pip3 install -r core/requirements.txt
    fi
    
    # Install backend dependencies
    if [ -f "backend/requirements.txt" ]; then
        pip3 install -r backend/requirements.txt
    else
        # Install manually if requirements.txt doesn't exist
        pip3 install fastapi uvicorn[standard] python-multipart python-jose[cryptography] passlib[bcrypt] python-dotenv psutil
    fi
    
    print_status "Python dependencies installed"
}

# Function to create .env file
create_env_file() {
    print_info "Creating environment configuration..."
    
    cat > .env << EOF
# nexAds Web Interface Configuration
DOMAIN=${DOMAIN}
FRONTEND_PORT=${FRONTEND_PORT}
BACKEND_PORT=${BACKEND_PORT}
SSL_ENABLED=${SSL_ENABLED}

# Authentication
AUTH_USERNAME=admin
AUTH_PASSWORD=admin123

# JWT Secret
JWT_SECRET=nexads-jwt-secret-$(date +%s)

# Database
DATABASE_URL=sqlite:///./nexads.db
EOF
    
    print_status "Environment configuration created"
}

# Function to setup nginx
setup_nginx() {
    print_info "Setting up nginx..."
    
    if [ "$SSL_ENABLED" = "true" ]; then
        # HTTPS configuration
        cat > /tmp/nexads_nginx << EOF
server {
    listen 80;
    server_name ${DOMAIN};
    return 301 https://\$server_name\$request_uri;
}

server {
    listen 443 ssl http2;
    server_name ${DOMAIN};
    
    ssl_certificate /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${DOMAIN}/privkey.pem;
    
    # Security headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    add_header Referrer-Policy "strict-origin-when-cross-origin";
    
    # Prevent crawling
    location /robots.txt {
        return 200 "User-agent: *\\nDisallow: /\\n";
        add_header Content-Type text/plain;
    }
    
    # API routes
    location /api {
        proxy_pass http://localhost:${BACKEND_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
    
    # Frontend
    location / {
        proxy_pass http://localhost:${FRONTEND_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF
    else
        # HTTP configuration
        cat > /tmp/nexads_nginx << EOF
server {
    listen 80;
    server_name ${DOMAIN};
    
    # Security headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    
    # Prevent crawling
    location /robots.txt {
        return 200 "User-agent: *\\nDisallow: /\\n";
        add_header Content-Type text/plain;
    }
    
    # API routes
    location /api {
        proxy_pass http://localhost:${BACKEND_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    }
    
    # Frontend
    location / {
        proxy_pass http://localhost:${FRONTEND_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    }
}
EOF
    fi
    
    # Move nginx config and enable
    sudo mv /tmp/nexads_nginx /etc/nginx/sites-available/nexads
    sudo ln -sf /etc/nginx/sites-available/nexads /etc/nginx/sites-enabled/
    sudo nginx -t
    sudo systemctl reload nginx
    
    print_status "Nginx configured"
}

# Function to setup SSL
setup_ssl() {
    if [ "$SSL_ENABLED" = "true" ]; then
        print_info "Setting up SSL certificate..."
        
        # Get SSL certificate
        sudo certbot --nginx -d ${DOMAIN} --non-interactive --agree-tos --email admin@${DOMAIN} --redirect
        
        print_status "SSL certificate configured"
    fi
}

# Function to build frontend
build_frontend() {
    print_info "Building frontend..."
    
    cd frontend
    npm install
    npm run build
    cd ..
    
    print_status "Frontend built"
}

# Function to start services
start_services() {
    print_info "Starting services..."
    
    # Start backend
    cd backend
    pm2 start main.py --name nexads-backend --interpreter python3
    cd ..
    
    # Start frontend
    cd frontend
    pm2 start npm --name nexads-frontend -- start
    cd ..
    
    # Save PM2 configuration
    pm2 save
    pm2 startup | grep -E '^sudo' | bash || true
    
    print_status "Services started"
}

# Function to get user input with default
get_input() {
    local prompt="$1"
    local default="$2"
    local input
    
    if [ -n "$default" ]; then
        read -p "$prompt (default: $default): " input
        echo "${input:-$default}"
    else
        read -p "$prompt: " input
        echo "$input"
    fi
}

# Main deployment function
main() {
    print_info "Starting nexAds Web Interface deployment..."
    
    # Get configuration from user
    echo ""
    echo "📋 Configuration Setup"
    echo "====================="
    
    # Get domain
    local_ip=$(get_local_ip)
    DOMAIN=$(get_input "Enter domain (press Enter for local IP)" "$local_ip")
    
    # Get ports
    FRONTEND_PORT=$(get_input "Enter frontend port" "4000")
    BACKEND_PORT=$(get_input "Enter backend port" "8000")
    
    # Determine SSL
    SSL_ENABLED="false"
    if [[ "$DOMAIN" != "$local_ip" && "$DOMAIN" != "localhost" && "$DOMAIN" == *.* ]]; then
        ssl_choice=$(get_input "Enable SSL? (y/N)" "N")
        if [[ "$ssl_choice" =~ ^[Yy]$ ]]; then
            SSL_ENABLED="true"
        fi
    fi
    
    echo ""
    print_info "Configuration Summary:"
    print_info "Domain: $DOMAIN"
    print_info "Frontend Port: $FRONTEND_PORT"
    print_info "Backend Port: $BACKEND_PORT"
    print_info "SSL Enabled: $SSL_ENABLED"
    echo ""
    
    read -p "Continue with deployment? (Y/n): " confirm
    if [[ "$confirm" =~ ^[Nn]$ ]]; then
        print_warning "Deployment cancelled"
        exit 0
    fi
    
    # Start deployment
    cleanup_previous
    install_system_deps
    install_python_deps
    create_env_file
    setup_nginx
    setup_ssl
    build_frontend
    start_services
    
    echo ""
    print_status "🎉 Deployment completed successfully!"
    echo ""
    print_info "📱 Frontend: $([ "$SSL_ENABLED" = "true" ] && echo "https" || echo "http")://${DOMAIN}"
    print_info "🔧 Backend API: $([ "$SSL_ENABLED" = "true" ] && echo "https" || echo "http")://${DOMAIN}/api"
    print_info "👤 Username: admin"
    print_info "🔑 Password: admin123"
    echo ""
    print_info "📊 Monitor services: pm2 status"
    print_info "📋 View logs: pm2 logs"
    print_info "🔄 Restart services: pm2 restart all"
    echo ""
}

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    print_error "Please don't run this script as root. It will ask for sudo when needed."
    exit 1
fi

# Check if we're in the right directory
if [ ! -d "core" ] || [ ! -f "core/config.json" ]; then
    print_error "Please run this script from the nexads-main directory"
    print_error "Make sure the 'core' directory with config.json exists"
    exit 1
fi

# Run main function
main "$@"