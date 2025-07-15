#!/bin/bash

# nexAds Automation Setup Script
# This script automatically configures the environment and deploys the application

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${BLUE}=== $1 ===${NC}"
}

# Function to get user input with default value
get_input() {
    local prompt="$1"
    local default="$2"
    local result

    if [ -n "$default" ]; then
        read -p "$prompt (default: $default): " result
        result=${result:-$default}
    else
        read -p "$prompt: " result
    fi

    echo "$result"
}

# Function to validate IP address
validate_ip() {
    local ip=$1
    if [[ $ip =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; then
        return 0
    else
        return 1
    fi
}

# Function to validate domain
validate_domain() {
    local domain=$1
    if [[ $domain =~ ^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$ ]]; then
        return 0
    else
        return 1
    fi
}

# Function to get local IP
get_local_ip() {
    hostname -I | awk '{print $1}' 2>/dev/null || echo "0.0.0.0"
}

# Function to check if port is available
check_port() {
    local port=$1
    if netstat -tuln 2>/dev/null | grep -q ":$port "; then
        return 1
    else
        return 0
    fi
}

# Function to run command safely
run_command() {
    local command="$1"
    local check="${2:-true}"

    print_status "Running: $command"
    if [ "$check" = "true" ]; then
        if ! eval "$command"; then
            print_error "Command failed: $command"
            exit 1
        fi
    else
        eval "$command" || true
    fi
}

# Function to cleanup previous deployment
cleanup_previous_deployment() {
    print_status "Cleaning up previous deployment..."

    # Stop PM2 processes
    run_command "pm2 stop nexads-backend nexads-frontend" false
    run_command "pm2 delete nexads-backend nexads-frontend" false

    # Remove nginx configuration
    run_command "sudo rm -f /etc/nginx/sites-available/nexads" false
    run_command "sudo rm -f /etc/nginx/sites-enabled/nexads" false

    # Remove SSL certificates (only nexads related)
    run_command "sudo certbot delete --cert-name nexads --non-interactive" false

    # Kill processes on ports
    run_command "sudo fuser -k 8000/tcp" false
    run_command "sudo fuser -k 5000/tcp" false

    # Reload nginx
    run_command "sudo systemctl reload nginx" false
}

# Main configuration function
configure_environment() {
    print_header "nexAds Environment Configuration"

    # Domain/IP configuration
    echo
    print_status "Domain/IP Configuration"
    echo "1. Use domain name (e.g., example.com)"
    echo "2. Use IP address"
    echo "3. Use localhost/local IP"

    domain_choice=$(get_input "Choose option (1-3)" "3")

    case $domain_choice in
        1)
            while true; do
                domain=$(get_input "Enter domain name" "")
                if validate_domain "$domain"; then
                    break
                else
                    print_error "Invalid domain format. Please try again."
                fi
            done
            use_ssl=true
            ;;
        2)
            while true; do
                domain=$(get_input "Enter IP address" "")
                if validate_ip "$domain"; then
                    break
                else
                    print_error "Invalid IP address format. Please try again."
                fi
            done
            use_ssl=false
            ;;
        3)
            local_ip=$(get_local_ip)
            echo "Available options:"
            echo "1. localhost"
            echo "2. 0.0.0.0 (all interfaces)"
            echo "3. Local IP: $local_ip"

            local_choice=$(get_input "Choose option (1-3)" "2")
            case $local_choice in
                1) domain="localhost" ;;
                2) domain="0.0.0.0" ;;
                3) domain="$local_ip" ;;
                *) domain="0.0.0.0" ;;
            esac
            use_ssl=false
            ;;
        *)
            domain="0.0.0.0"
            use_ssl=false
            ;;
    esac

    # Port configuration
    echo
    print_status "Port Configuration"

    # Frontend port
    while true; do
        frontend_port=$(get_input "Frontend port" "5000")
        if check_port "$frontend_port"; then
            break
        else
            print_warning "Port $frontend_port is already in use. Please choose another."
        fi
    done

    # Backend port
    while true; do
        backend_port=$(get_input "Backend port" "8000")
        if [ "$backend_port" != "$frontend_port" ] && check_port "$backend_port"; then
            break
        elif [ "$backend_port" == "$frontend_port" ]; then
            print_warning "Backend port cannot be the same as frontend port."
        else
            print_warning "Port $backend_port is already in use. Please choose another."
        fi
    done

    # Authentication configuration
    echo
    print_status "Authentication Configuration"
    auth_username=$(get_input "Admin username" "admin")

    while true; do
        auth_password=$(get_input "Admin password" "admin123")
        if [ ${#auth_password} -ge 6 ]; then
            break
        else
            print_error "Password must be at least 6 characters long."
        fi
    done

    # Secret key generation
    secret_key=$(openssl rand -hex 32 2>/dev/null || echo "$(date +%s)-$(whoami)-$(hostname)" | sha256sum | cut -d' ' -f1)

    # SSL configuration
    if [ "$use_ssl" = true ]; then
        echo
        print_status "SSL Configuration"
        echo "SSL will be automatically configured for domain: $domain"
        ssl_email=$(get_input "Email for SSL certificate" "admin@$domain")
    fi

    # Summary
    echo
    print_header "Configuration Summary"
    echo "Domain/IP: $domain"
    echo "Frontend Port: $frontend_port"
    echo "Backend Port: $backend_port"
    echo "SSL Enabled: $use_ssl"
    echo "Admin Username: $auth_username"
    echo "Admin Password: $auth_password"

    # Confirmation
    echo
    confirm=$(get_input "Proceed with this configuration? (y/N)" "y")
    if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
        print_error "Configuration cancelled."
        exit 1
    fi

    # Create .env file
    create_env_file
}

# Function to create .env file
create_env_file() {
    print_status "Creating .env file..."

    protocol="http"
    if [ "$use_ssl" = true ]; then
        protocol="https"
    fi

    cat > .env << EOF
# nexAds Environment Configuration
# Generated on: $(date)

# Domain and SSL
DOMAIN=$domain
USE_SSL=$use_ssl
PROTOCOL=$protocol

# Ports
FRONTEND_PORT=$frontend_port
BACKEND_PORT=$backend_port

# API Configuration
API_URL=$protocol://$domain/api
FRONTEND_URL=$protocol://$domain

# Authentication
AUTH_USERNAME=$auth_username
AUTH_PASSWORD=$auth_password
SECRET_KEY=$secret_key

# SSL Configuration
EOF

    if [ "$use_ssl" = true ]; then
        echo "SSL_EMAIL=$ssl_email" >> .env
    fi

    cat >> .env << EOF

# Automation Configuration
AUTOMATION_SERVICE_NAME=nexads-automation
AUTOMATION_WORKING_DIR=$(pwd)/core
AUTOMATION_SCRIPT=$(pwd)/core/main.py

# Logging
LOG_LEVEL=INFO
LOG_FILE=/var/log/nexads.log

# System Configuration
NODEJS_VERSION=18
PYTHON_VERSION=3.10
EOF

    print_status ".env file created successfully"
}

# Function to validate system requirements
check_requirements() {
    print_header "System Requirements Check"

    # Check if running as root or with sudo access
    if [ "$EUID" -ne 0 ]; then
        print_status "Checking sudo access..."
        if ! sudo -n true 2>/dev/null; then
            print_error "This script requires sudo access. Please run with sudo or ensure your user has sudo privileges."
            exit 1
        fi
    fi

    # Check OS
    if [ ! -f /etc/os-release ]; then
        print_error "Unsupported operating system. This script requires a Linux distribution."
        exit 1
    fi

    # Check available disk space (require at least 1GB)
    available_space=$(df / | awk 'NR==2 {print $4}' 2>/dev/null || echo "999999999")
    if [ "$available_space" -lt 1048576 ]; then
        print_warning "Low disk space detected. At least 1GB free space is recommended."
    fi

    print_status "System requirements check passed"
}

# Function to backup existing configuration
backup_config() {
    if [ -f .env ]; then
        print_status "Backing up existing .env file..."
        cp .env .env.backup.$(date +%Y%m%d_%H%M%S)
    fi

    if [ -f /etc/nginx/sites-enabled/nexads ]; then
        print_status "Backing up existing nginx configuration..."
        sudo cp /etc/nginx/sites-enabled/nexads /tmp/nexads.nginx.backup.$(date +%Y%m%d_%H%M%S) 2>/dev/null || true
    fi
}

# Function to install system dependencies
install_dependencies() {
    print_header "Installing Dependencies"

    # Update package list
    print_status "Updating package list..."
    run_command "sudo apt update -y"

    # Install basic dependencies
    print_status "Installing basic dependencies..."
    run_command "sudo apt install -y curl wget git nginx python3 python3-pip openssl build-essential"

    # Check and install Node.js
    print_status "Checking Node.js installation..."
    node_version=$(node --version 2>/dev/null | sed 's/v//' | cut -d'.' -f1 || echo "0")
    npm_check=$(which npm 2>/dev/null || echo "")

    if [ "$node_version" -lt 16 ] || [ -z "$npm_check" ]; then
        print_status "Installing Node.js 18 and npm..."
        # Remove any existing nodejs/npm
        run_command "sudo apt remove -y nodejs npm" false

        # Install Node.js 18
        run_command "curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -"
        run_command "sudo apt install -y nodejs"

        # Verify installation
        node_version=$(node --version 2>/dev/null | sed 's/v//' | cut -d'.' -f1 || echo "0")
        npm_version=$(npm --version 2>/dev/null || echo "none")

        if [ "$node_version" -lt 16 ] || [ "$npm_version" = "none" ]; then
            print_error "Failed to install Node.js/npm properly. Trying alternative method..."
            # Alternative installation method
            run_command "wget -qO- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash"
            run_command "source ~/.bashrc && nvm install 18 && nvm use 18" false
            # Create symlinks
            run_command "sudo ln -sf ~/.nvm/versions/node/v18.*/bin/node /usr/local/bin/node" false
            run_command "sudo ln -sf ~/.nvm/versions/node/v18.*/bin/npm /usr/local/bin/npm" false
        fi
    else
        print_status "Node.js version is sufficient (v$node_version)"
    fi

    # Verify npm is working
    if ! npm --version >/dev/null 2>&1; then
        print_error "npm is not working properly"
        exit 1
    fi

    # Install PM2
    print_status "Installing/updating PM2..."
    run_command "sudo npm install -g pm2@latest"

    # Verify PM2 installation
    if ! pm2 --version >/dev/null 2>&1; then
        print_warning "PM2 installation failed, trying alternative method..."
        run_command "npm install -g pm2@latest"

        # Add npm global bin to PATH if needed
        if ! pm2 --version >/dev/null 2>&1; then
            export PATH="$PATH:$(npm config get prefix)/bin"
            echo 'export PATH="$PATH:$(npm config get prefix)/bin"' >> ~/.bashrc
        fi
    fi

    # Install Python dependencies
    print_status "Installing Python dependencies..."
    if [ -f core/requirements.txt ]; then
        run_command "pip3 install -r core/requirements.txt"
    fi

    # Install backend dependencies
    run_command "pip3 install fastapi uvicorn python-multipart aiofiles bcrypt python-jose[cryptography] passlib[bcrypt]"

    # Install frontend dependencies
    if [ -d frontend ]; then
        print_status "Installing frontend dependencies..."
        cd frontend

        # Check if package.json exists
        if [ ! -f package.json ]; then
            print_error "package.json not found in frontend directory"
            cd ..
            exit 1
        fi

        # Install with retry mechanism
        for i in {1..3}; do
            if npm install; then
                break
            else
                print_warning "npm install failed, attempt $i/3"
                if [ $i -eq 3 ]; then
                    print_error "Failed to install frontend dependencies after 3 attempts"
                    cd ..
                    exit 1
                fi
                sleep 2
            fi
        done
        cd ..
    fi

    print_status "Dependencies installed successfully"
}

# Function to setup SSL
setup_ssl() {
    print_status "Setting up SSL for domain: $domain"

    # Install certbot
    run_command "sudo apt install -y certbot python3-certbot-nginx"

    # Create basic nginx config first without SSL
    create_basic_nginx_config

    # Get SSL certificate
    print_status "Obtaining SSL certificate..."
    run_command "sudo certbot --nginx -d $domain --non-interactive --agree-tos --email $ssl_email --redirect"

    print_status "SSL certificate obtained and nginx configured automatically"
}

# Function to create basic nginx configuration (without SSL)
create_basic_nginx_config() {
    print_status "Creating basic nginx configuration..."

    config=$(cat << EOF
server {
    listen 80;
    server_name $domain;

    location / {
        proxy_pass http://localhost:$frontend_port;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_cache_bypass \$http_upgrade;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /api {
        proxy_pass http://localhost:$backend_port/api;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_cache_bypass \$http_upgrade;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF
)

    echo "$config" | sudo tee /etc/nginx/sites-available/nexads > /dev/null
    run_command "sudo ln -sf /etc/nginx/sites-available/nexads /etc/nginx/sites-enabled/"
    run_command "sudo nginx -t"
    run_command "sudo systemctl reload nginx"
}

# Function to create nginx configuration
create_nginx_config() {
    print_status "Creating nginx configuration..."

    if [ "$use_ssl" = true ]; then
        config=$(cat << EOF
server {
    listen 80;
    server_name $domain;
    return 301 https://\$server_name\$request_uri;
}

server {
    listen 443 ssl;
    server_name $domain;

    ssl_certificate /etc/letsencrypt/live/$domain/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$domain/privkey.pem;

    location / {
        proxy_pass http://localhost:$frontend_port;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_cache_bypass \$http_upgrade;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /api {
        proxy_pass http://localhost:$backend_port/api;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_cache_bypass \$http_upgrade;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF
)
    else
        config=$(cat << EOF
server {
    listen 80;
    server_name $domain;

    location / {
        proxy_pass http://localhost:$frontend_port;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_cache_bypass \$http_upgrade;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /api {
        proxy_pass http://localhost:$backend_port/api;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_cache_bypass \$http_upgrade;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF
)
    fi

    echo "$config" | sudo tee /etc/nginx/sites-available/nexads > /dev/null
    run_command "sudo ln -sf /etc/nginx/sites-available/nexads /etc/nginx/sites-enabled/"
    run_command "sudo nginx -t"
    run_command "sudo systemctl reload nginx"
}

# Function to start services
start_services() {
    print_status "Starting services with PM2..."

    # Start backend
    cd backend
    run_command "pm2 start main.py --name nexads-backend --interpreter python3"
    cd ..

    # Build and start frontend
    cd frontend
    run_command "npm run build"
    run_command "pm2 serve build/ $frontend_port --name nexads-frontend"
    cd ..

    # Save PM2 configuration
    run_command "pm2 save"
    run_command "pm2 startup" false

    print_status "Services started successfully"
}

# Main execution
main() {
    print_header "nexAds Automation Setup"

    # Check requirements
    check_requirements

    # Backup existing configuration
    backup_config

    # Configure environment
    configure_environment

    # Clean up previous deployment
    cleanup_previous_deployment

    # Install dependencies
    install_dependencies

    # Setup nginx configuration
    if [ "$use_ssl" = true ]; then
        setup_ssl
    else
        print_status "Creating nginx configuration without SSL..."
        create_basic_nginx_config
    fi

    # Start services
    start_services

    print_header "Setup Complete"
    print_status "nexAds automation panel is now ready!"
    echo
    protocol="http"
    if [ "$use_ssl" = true ]; then
        protocol="https"
    fi
    echo "Access your panel at: $protocol://$domain"
    echo "Username: $auth_username"
    echo "Password: $auth_password"
    echo
    print_status "Configuration saved to .env file"
    print_status "Logs can be viewed with: sudo journalctl -u nexads-automation -f"
    print_status "PM2 logs: pm2 logs"
}

# Run main function
main "$@"