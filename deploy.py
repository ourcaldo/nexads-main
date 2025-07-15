
#!/usr/bin/env python3
import os
import sys
import subprocess
import json
import socket
from pathlib import Path

def get_local_ip():
    """Get local IP address"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

def run_command(command, check=True):
    """Run shell command"""
    print(f"Running: {command}")
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"Error: {result.stderr}")
        sys.exit(1)
    return result

def cleanup_previous_deployment():
    """Clean up previous deployment resources"""
    print("Cleaning up previous deployment...")
    
    # Stop PM2 processes
    run_command("pm2 stop nexads-backend nexads-frontend", check=False)
    run_command("pm2 delete nexads-backend nexads-frontend", check=False)
    
    # Remove nginx configuration
    run_command("sudo rm -f /etc/nginx/sites-available/nexads", check=False)
    run_command("sudo rm -f /etc/nginx/sites-enabled/nexads", check=False)
    
    # Remove SSL certificates (only nexads related)
    run_command("sudo certbot delete --cert-name nexads", check=False)
    
    # Kill processes on ports
    run_command("sudo fuser -k 8000/tcp", check=False)
    run_command("sudo fuser -k 4000/tcp", check=False)
    
    # Reload nginx
    run_command("sudo systemctl reload nginx", check=False)

def install_dependencies():
    """Install all required dependencies"""
    print("Installing system dependencies...")
    
    # Update system
    run_command("sudo apt update")
    
    # Install Node.js and npm
    run_command("curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -")
    run_command("sudo apt install -y nodejs")
    
    # Install PM2
    run_command("sudo npm install -g pm2")
    
    # Install Python dependencies for main automation
    run_command("pip3 install -r core/requirements.txt")
    
    # Install backend dependencies
    run_command("pip3 install fastapi uvicorn python-multipart aiofiles bcrypt python-jose[cryptography]")
    
    # Install nginx
    run_command("sudo apt install -y nginx")

def setup_ssl(domain):
    """Setup SSL with certbot"""
    print(f"Setting up SSL for domain: {domain}")
    
    # Install certbot
    run_command("sudo apt install -y certbot python3-certbot-nginx")
    
    # Get SSL certificate
    run_command(f"sudo certbot --nginx -d {domain} --non-interactive --agree-tos --email admin@{domain}")

def create_nginx_config(domain, frontend_port, backend_port, use_ssl):
    """Create nginx configuration"""
    print("Creating nginx configuration...")
    
    if use_ssl:
        config = f"""
server {{
    listen 80;
    server_name {domain};
    return 301 https://$server_name$request_uri;
}}

server {{
    listen 443 ssl;
    server_name {domain};
    
    ssl_certificate /etc/letsencrypt/live/{domain}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/{domain}/privkey.pem;
    
    location / {{
        proxy_pass http://localhost:{frontend_port};
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
    
    location /api {{
        proxy_pass http://localhost:{backend_port}/api;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
}}
"""
    else:
        config = f"""
server {{
    listen 80;
    server_name {domain};
    
    location / {{
        proxy_pass http://localhost:{frontend_port};
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
    
    location /api {{
        proxy_pass http://localhost:{backend_port}/api;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
}}
"""
    
    with open('/tmp/nexads_nginx.conf', 'w') as f:
        f.write(config)
    
    run_command("sudo mv /tmp/nexads_nginx.conf /etc/nginx/sites-available/nexads")
    run_command("sudo ln -s /etc/nginx/sites-available/nexads /etc/nginx/sites-enabled/")
    run_command("sudo nginx -t")
    run_command("sudo systemctl reload nginx")

def create_env_file(domain, frontend_port, backend_port, use_ssl):
    """Create .env file"""
    print("Creating .env file...")
    
    protocol = "https" if use_ssl else "http"
    
    env_content = f"""DOMAIN={domain}
FRONTEND_PORT={frontend_port}
BACKEND_PORT={backend_port}
USE_SSL={use_ssl}
API_URL={protocol}://{domain}/api
AUTH_USERNAME=admin
AUTH_PASSWORD=admin123
SECRET_KEY=your-secret-key-here-change-in-production
"""
    
    with open('.env', 'w') as f:
        f.write(env_content)

def start_services():
    """Start backend and frontend services with PM2"""
    print("Starting services with PM2...")
    
    # Start backend
    run_command("pm2 start backend/main.py --name nexads-backend --interpreter python3")
    
    # Start frontend (build and serve)
    os.chdir("frontend")
    run_command("npm run build")
    run_command("pm2 serve build/ --name nexads-frontend --port 4000")
    os.chdir("..")
    
    # Save PM2 configuration
    run_command("pm2 save")
    run_command("pm2 startup")

def main():
    print("=== nexAds Deployment Script ===")
    
    # Get user input
    domain = input("Enter domain (e.g., google.com) or press Enter for localhost: ").strip()
    if not domain:
        domain = get_local_ip()
    
    frontend_port = input("Enter frontend port (default: 4000): ").strip()
    if not frontend_port:
        frontend_port = "4000"
    
    backend_port = input("Enter backend port (default: 8000): ").strip()
    if not backend_port:
        backend_port = "8000"
    
    # Determine SSL usage
    use_ssl = not (domain.replace('.', '').isdigit() or domain == "localhost" or domain.startswith("192.168.") or domain.startswith("10.") or domain.startswith("172."))
    
    print(f"\nConfiguration:")
    print(f"Domain: {domain}")
    print(f"Frontend Port: {frontend_port}")
    print(f"Backend Port: {backend_port}")
    print(f"SSL: {'Yes' if use_ssl else 'No'}")
    
    confirm = input("\nProceed with deployment? (y/N): ").strip().lower()
    if confirm != 'y':
        print("Deployment cancelled.")
        return
    
    try:
        # Clean up previous deployment
        cleanup_previous_deployment()
        
        # Install dependencies
        install_dependencies()
        
        # Create .env file
        create_env_file(domain, frontend_port, backend_port, use_ssl)
        
        # Setup nginx
        create_nginx_config(domain, frontend_port, backend_port, use_ssl)
        
        # Setup SSL if needed
        if use_ssl:
            setup_ssl(domain)
        
        # Start services
        start_services()
        
        print("\n=== Deployment Complete ===")
        protocol = "https" if use_ssl else "http"
        print(f"Frontend: {protocol}://{domain}")
        print(f"Backend API: {protocol}://{domain}/api")
        print(f"Login: admin / admin123")
        
    except Exception as e:
        print(f"Deployment failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
