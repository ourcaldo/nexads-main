#!/usr/bin/env python3
"""
nexAds Web Interface Setup Script
Automatically configures domain, ports, SSL, and deploys the application
"""

import os
import sys
import subprocess
import json
import socket
import time
from pathlib import Path

def get_local_ip():
    """Get the local IP address"""
    try:
        # Connect to a remote server to determine local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

def run_command(command, check=True, shell=True):
    """Run a shell command"""
    print(f"Running: {command}")
    try:
        result = subprocess.run(command, shell=shell, check=check, 
                              capture_output=True, text=True)
        if result.stdout:
            print(result.stdout)
        return result
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {e}")
        if e.stderr:
            print(f"Error output: {e.stderr}")
        if check:
            sys.exit(1)
        return e

def cleanup_previous_deployment():
    """Clean up previous deployment resources"""
    print("🧹 Cleaning up previous deployment...")
    
    # Stop PM2 processes
    run_command("pm2 delete nexads-backend", check=False)
    run_command("pm2 delete nexads-frontend", check=False)
    
    # Remove nginx configuration
    run_command("sudo rm -f /etc/nginx/sites-available/nexads", check=False)
    run_command("sudo rm -f /etc/nginx/sites-enabled/nexads", check=False)
    
    # Remove SSL certificates (only nexads related)
    if os.path.exists("/etc/letsencrypt/live"):
        for domain_dir in os.listdir("/etc/letsencrypt/live"):
            if "nexads" in domain_dir.lower():
                run_command(f"sudo certbot delete --cert-name {domain_dir}", check=False)
    
    # Reload nginx
    run_command("sudo nginx -t", check=False)
    run_command("sudo systemctl reload nginx", check=False)
    
    print("✅ Cleanup completed")

def install_system_dependencies():
    """Install system dependencies"""
    print("📦 Installing system dependencies...")
    
    # Update package list
    run_command("sudo apt update")
    
    # Install Node.js and npm
    run_command("curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -")
    run_command("sudo apt-get install -y nodejs")
    
    # Install PM2
    run_command("sudo npm install -g pm2")
    
    # Install nginx
    run_command("sudo apt-get install -y nginx")
    
    # Install certbot
    run_command("sudo apt-get install -y certbot python3-certbot-nginx")
    
    print("✅ System dependencies installed")

def install_python_dependencies():
    """Install Python dependencies"""
    print("🐍 Installing Python dependencies...")
    
    # Install core automation dependencies
    if os.path.exists("core/requirements.txt"):
        run_command("pip3 install -r core/requirements.txt")
    
    # Install backend dependencies
    backend_deps = [
        "fastapi",
        "uvicorn[standard]",
        "python-multipart",
        "python-jose[cryptography]",
        "passlib[bcrypt]",
        "sqlalchemy",
        "databases[sqlite]",
        "aiosqlite",
        "psutil"
    ]
    
    for dep in backend_deps:
        run_command(f"pip3 install {dep}")
    
    print("✅ Python dependencies installed")

def create_env_file():
    """Create .env file based on user input"""
    print("⚙️  Configuring environment...")
    
    # Get domain
    domain = input("Enter domain (press Enter for localhost): ").strip()
    if not domain:
        domain = get_local_ip()
        print(f"Using local IP: {domain}")
    
    # Get ports
    frontend_port = input("Enter frontend port (default 4000): ").strip()
    if not frontend_port:
        frontend_port = "4000"
    
    backend_port = input("Enter backend port (default 8000): ").strip()
    if not backend_port:
        backend_port = "8000"
    
    # Determine SSL
    ssl_enabled = "false"
    if domain != get_local_ip() and domain != "localhost" and "." in domain:
        ssl_choice = input("Enable SSL? (y/N): ").strip().lower()
        if ssl_choice in ['y', 'yes']:
            ssl_enabled = "true"
    
    # Create .env file
    env_content = f"""# nexAds Web Interface Configuration
DOMAIN={domain}
FRONTEND_PORT={frontend_port}
BACKEND_PORT={backend_port}
SSL_ENABLED={ssl_enabled}

# Authentication
AUTH_USERNAME=admin
AUTH_PASSWORD=admin123

# JWT Secret
JWT_SECRET=nexads-jwt-secret-{int(time.time())}

# Database
DATABASE_URL=sqlite:///./nexads.db
"""
    
    with open(".env", "w") as f:
        f.write(env_content)
    
    print("✅ Environment configuration created")
    return domain, frontend_port, backend_port, ssl_enabled == "true"

def setup_nginx(domain, frontend_port, backend_port, ssl_enabled):
    """Setup nginx configuration"""
    print("🌐 Setting up nginx...")
    
    if ssl_enabled:
        nginx_config = f"""server {{
    listen 80;
    server_name {domain};
    return 301 https://$server_name$request_uri;
}}

server {{
    listen 443 ssl http2;
    server_name {domain};
    
    ssl_certificate /etc/letsencrypt/live/{domain}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/{domain}/privkey.pem;
    
    # Security headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    add_header Referrer-Policy "strict-origin-when-cross-origin";
    
    # Prevent crawling
    location /robots.txt {{
        return 200 "User-agent: *\\nDisallow: /\\n";
        add_header Content-Type text/plain;
    }}
    
    # API routes
    location /api {{
        proxy_pass http://localhost:{backend_port};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
    
    # Frontend
    location / {{
        proxy_pass http://localhost:{frontend_port};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
}}"""
    else:
        nginx_config = f"""server {{
    listen 80;
    server_name {domain};
    
    # Security headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    
    # Prevent crawling
    location /robots.txt {{
        return 200 "User-agent: *\\nDisallow: /\\n";
        add_header Content-Type text/plain;
    }}
    
    # API routes
    location /api {{
        proxy_pass http://localhost:{backend_port};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }}
    
    # Frontend
    location / {{
        proxy_pass http://localhost:{frontend_port};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }}
}}"""
    
    # Write nginx config
    with open("/tmp/nexads_nginx", "w") as f:
        f.write(nginx_config)
    
    run_command("sudo mv /tmp/nexads_nginx /etc/nginx/sites-available/nexads")
    run_command("sudo ln -sf /etc/nginx/sites-available/nexads /etc/nginx/sites-enabled/")
    run_command("sudo nginx -t")
    run_command("sudo systemctl reload nginx")
    
    print("✅ Nginx configured")

def setup_ssl(domain):
    """Setup SSL certificate"""
    print("🔒 Setting up SSL certificate...")
    
    run_command(f"sudo certbot --nginx -d {domain} --non-interactive --agree-tos --email admin@{domain}")
    
    print("✅ SSL certificate configured")

def build_frontend():
    """Build the frontend"""
    print("🏗️  Building frontend...")
    
    os.chdir("frontend")
    run_command("npm install")
    run_command("npm run build")
    os.chdir("..")
    
    print("✅ Frontend built")

def start_services():
    """Start backend and frontend services"""
    print("🚀 Starting services...")
    
    # Start backend
    run_command("pm2 start backend/main.py --name nexads-backend --interpreter python3")
    
    # Start frontend
    os.chdir("frontend")
    run_command("pm2 start npm --name nexads-frontend -- start")
    os.chdir("..")
    
    # Save PM2 configuration
    run_command("pm2 save")
    run_command("pm2 startup")
    
    print("✅ Services started")

def main():
    """Main setup function"""
    print("🚀 nexAds Web Interface Setup")
    print("=" * 40)
    
    # Check if running as root for some operations
    if os.geteuid() != 0:
        print("⚠️  Some operations require sudo privileges")
    
    try:
        # Cleanup previous deployment
        cleanup_previous_deployment()
        
        # Install dependencies
        install_system_dependencies()
        install_python_dependencies()
        
        # Create environment configuration
        domain, frontend_port, backend_port, ssl_enabled = create_env_file()
        
        # Setup nginx
        setup_nginx(domain, frontend_port, backend_port, ssl_enabled)
        
        # Setup SSL if enabled
        if ssl_enabled:
            setup_ssl(domain)
        
        # Build frontend
        build_frontend()
        
        # Start services
        start_services()
        
        print("\n🎉 Setup completed successfully!")
        print(f"📱 Frontend: {'https' if ssl_enabled else 'http'}://{domain}")
        print(f"🔧 Backend API: {'https' if ssl_enabled else 'http'}://{domain}/api")
        print(f"👤 Username: admin")
        print(f"🔑 Password: admin123")
        print("\n📊 Monitor services: pm2 status")
        print("📋 View logs: pm2 logs")
        
    except KeyboardInterrupt:
        print("\n❌ Setup cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Setup failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()