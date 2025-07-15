
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
    hostname -I | awk '{print $1}'
}

# Function to check if port is available
check_port() {
    local port=$1
    if netstat -tuln | grep -q ":$port "; then
        return 1
    else
        return 0
    fi
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
    available_space=$(df / | awk 'NR==2 {print $4}')
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
        sudo cp /etc/nginx/sites-enabled/nexads /tmp/nexads.nginx.backup.$(date +%Y%m%d_%H%M%S)
    fi
}

# Function to install system dependencies
install_dependencies() {
    print_header "Installing Dependencies"
    
    # Update package list
    print_status "Updating package list..."
    sudo apt update -y
    
    # Install basic dependencies
    print_status "Installing basic dependencies..."
    sudo apt install -y curl wget git nginx python3 python3-pip nodejs npm openssl
    
    # Install PM2
    print_status "Installing PM2..."
    sudo npm install -g pm2
    
    # Install Python dependencies
    print_status "Installing Python dependencies..."
    if [ -f core/requirements.txt ]; then
        pip3 install -r core/requirements.txt
    fi
    
    # Install backend dependencies
    pip3 install fastapi uvicorn python-multipart aiofiles bcrypt python-jose[cryptography]
    
    # Install frontend dependencies
    if [ -d frontend ]; then
        print_status "Installing frontend dependencies..."
        cd frontend
        npm install
        cd ..
    fi
    
    print_status "Dependencies installed successfully"
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
    
    # Install dependencies
    install_dependencies
    
    # Run Python deployment script
    print_header "Running Deployment"
    print_status "Starting Python deployment script..."
    
    # Export environment variables for deploy.py
    export DOMAIN="$domain"
    export FRONTEND_PORT="$frontend_port"
    export BACKEND_PORT="$backend_port"
    export USE_SSL="$use_ssl"
    export AUTH_USERNAME="$auth_username"
    export AUTH_PASSWORD="$auth_password"
    export SECRET_KEY="$secret_key"
    
    # Run deployment script
    python3 deploy.py --auto
    
    print_header "Setup Complete"
    print_status "nexAds automation panel is now ready!"
    echo
    echo "Access your panel at: $protocol://$domain"
    echo "Username: $auth_username"
    echo "Password: $auth_password"
    echo
    print_status "Configuration saved to .env file"
    print_status "Logs can be viewed with: sudo journalctl -u nexads-automation -f"
}

# Run main function
main "$@"
