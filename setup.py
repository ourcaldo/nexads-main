
#!/usr/bin/env python3
import os
import sys
import subprocess
import json
from pathlib import Path

def run_command(command, check=True):
    """Run shell command and handle errors"""
    try:
        result = subprocess.run(command, shell=True, check=check, capture_output=True, text=True)
        if result.stdout:
            print(result.stdout)
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {command}")
        print(f"Error: {e.stderr}")
        return False

def display_system_info(config):
    """Display comprehensive system information"""
    print("\n" + "="*60)
    print("           NEXADS CONTROL PANEL - SYSTEM INFO")
    print("="*60)
    
    # Environment Variables
    print("\n📋 ENVIRONMENT VARIABLES:")
    print(f"   DOMAIN: {config['DOMAIN']}")
    print(f"   FRONTEND_PORT: {config['FRONTEND_PORT']}")
    print(f"   BACKEND_PORT: {config['BACKEND_PORT']}")
    print(f"   SSL: {config['SSL']}")
    print(f"   USERNAME: {config['USERNAME']}")
    print(f"   PASSWORD: {config['PASSWORD']}")
    
    # URLs
    protocol = 'https' if config['SSL'] == 'true' else 'http'
    print(f"\n🌐 ACCESS URLS:")
    print(f"   Frontend: {protocol}://{config['DOMAIN']}")
    print(f"   Backend API: {protocol}://{config['DOMAIN']}/api")
    print(f"   Health Check: {protocol}://{config['DOMAIN']}/api/health")
    
    # SSL Status
    print(f"\n🔒 SSL STATUS:")
    if config['SSL'] == 'true':
        ssl_result = subprocess.run(['sudo', 'certbot', 'certificates'], capture_output=True, text=True)
        if ssl_result.returncode == 0 and config['DOMAIN'] in ssl_result.stdout:
            print("   ✓ SSL Certificate: ACTIVE")
        else:
            print("   ✗ SSL Certificate: FAILED/NOT FOUND")
    else:
        print("   ⚠ SSL Certificate: DISABLED")
    
    # Nginx Configuration
    print(f"\n⚙️ NGINX CONFIGURATION:")
    print(f"   Config File: /etc/nginx/sites-available/nexads")
    print(f"   Enabled Link: /etc/nginx/sites-enabled/nexads")
    
    # Check nginx status
    nginx_result = subprocess.run(['sudo', 'systemctl', 'is-active', 'nginx'], capture_output=True, text=True)
    print(f"   Nginx Status: {'✓ RUNNING' if nginx_result.stdout.strip() == 'active' else '✗ NOT RUNNING'}")
    
    # PM2 Status
    print(f"\n🚀 SERVICE STATUS:")
    pm2_result = subprocess.run(['pm2', 'list'], capture_output=True, text=True)
    if 'nexads-backend' in pm2_result.stdout:
        print("   ✓ Backend Service: RUNNING (PM2)")
    else:
        print("   ✗ Backend Service: NOT RUNNING")
    
    # Port Status
    print(f"\n🔌 PORT STATUS:")
    try:
        import socket
        def check_port(port):
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(('127.0.0.1', int(port)))
            sock.close()
            return result == 0
        
        backend_status = "✓ OPEN" if check_port(config['BACKEND_PORT']) else "✗ CLOSED"
        print(f"   Backend Port {config['BACKEND_PORT']}: {backend_status}")
        
        nginx_status = "✓ OPEN" if check_port('80') else "✗ CLOSED"
        print(f"   HTTP Port 80: {nginx_status}")
        
        if config['SSL'] == 'true':
            ssl_status = "✓ OPEN" if check_port('443') else "✗ CLOSED"
            print(f"   HTTPS Port 443: {ssl_status}")
    except:
        print("   Could not check port status")
    
    # File Locations
    print(f"\n📁 IMPORTANT FILE LOCATIONS:")
    print(f"   Project Root: {os.getcwd()}")
    print(f"   Core Config: {os.getcwd()}/core/config.json")
    print(f"   Proxy File: {os.getcwd()}/core/proxy.txt")
    print(f"   Environment: {os.getcwd()}/.env")
    print(f"   Nginx Config: /etc/nginx/sites-available/nexads")
    print(f"   SSL Certificates: /etc/letsencrypt/live/{config['DOMAIN']}/ (if SSL enabled)")
    
    # Authentication
    print(f"\n🔐 AUTHENTICATION:")
    print(f"   Username: {config['USERNAME']}")
    print(f"   Password: {config['PASSWORD']}")
    
    print("\n" + "="*60)
    print("Setup completed! Your NexAds control panel is ready.")
    if config['SSL'] == 'false' and config['DOMAIN'] != 'localhost':
        print("\nNote: SSL setup failed. To retry SSL later, run:")
        print(f"sudo certbot --nginx -d {config['DOMAIN']}")
    print("="*60)

def get_user_input():
    """Get configuration from user"""
    print("=== NexAds Web Panel Setup ===")
    
    domain = input("Domain (e.g., google.com or localhost): ").strip()
    frontend_port = input("Frontend port [4000]: ").strip() or "4000"
    backend_port = input("Backend port [8000]: ").strip() or "8000"
    
    # Determine SSL based on domain
    is_domain = not (domain.startswith("localhost") or domain.replace(".", "").isdigit())
    ssl = "true" if is_domain else "false"
    
    print(f"SSL will be {'enabled' if ssl == 'true' else 'disabled'} for {domain}")
    
    return {
        "DOMAIN": domain,
        "FRONTEND_PORT": frontend_port,
        "BACKEND_PORT": backend_port,
        "SSL": ssl,
        "USERNAME": "admin",
        "PASSWORD": "admin123"
    }

def create_env_file(config):
    """Create .env file"""
    env_content = f"""DOMAIN={config['DOMAIN']}
FRONTEND_PORT={config['FRONTEND_PORT']}
BACKEND_PORT={config['BACKEND_PORT']}
SSL={config['SSL']}
USERNAME={config['USERNAME']}
PASSWORD={config['PASSWORD']}
"""
    
    with open('.env', 'w') as f:
        f.write(env_content)
    
    print("✓ .env file created")

def cleanup_previous_installation():
    """Clean up previous installation"""
    print("Cleaning up previous installation...")
    
    # Stop PM2 processes
    run_command("pm2 stop nexads-backend nexads-frontend", check=False)
    run_command("pm2 delete nexads-backend nexads-frontend", check=False)
    
    # Stop services
    run_command("sudo systemctl stop nexads-automation.service", check=False)
    run_command("sudo systemctl disable nexads-automation.service", check=False)
    
    # Remove nginx config
    run_command("sudo rm -f /etc/nginx/sites-enabled/nexads", check=False)
    run_command("sudo rm -f /etc/nginx/sites-available/nexads", check=False)
    
    # Remove SSL certificates if they exist
    run_command("sudo certbot delete --cert-name nexads", check=False)
    
    # Reload nginx
    run_command("sudo systemctl reload nginx", check=False)
    
    print("✓ Previous installation cleaned up")

def install_dependencies():
    """Install all dependencies"""
    print("Installing dependencies...")
    
    # Update system
    run_command("sudo apt update")
    
    # Install system dependencies
    run_command("sudo apt install -y python3-pip nginx certbot python3-certbot-nginx nodejs npm")
    
    # Install core automation dependencies
    if os.path.exists("core/requirements.txt"):
        run_command("pip3 install -r core/requirements.txt")
    
    # Install PM2 globally
    run_command("sudo npm install -g pm2")
    
    print("✓ Dependencies installed")

def setup_backend():
    """Set up backend"""
    print("Setting up backend...")
    
    # Create backend directory
    os.makedirs("backend", exist_ok=True)
    
    # Install backend dependencies
    run_command("pip3 install fastapi uvicorn python-multipart python-jose[cryptography] passlib[bcrypt] python-dotenv")
    
    print("✓ Backend setup complete")

def setup_frontend():
    """Set up frontend"""
    print("Setting up frontend...")
    
    # Create frontend directory
    if not os.path.exists("frontend"):
        run_command("npx create-react-app frontend")
    
    # Install additional frontend dependencies
    os.chdir("frontend")
    run_command("npm install axios react-router-dom @mui/material @emotion/react @emotion/styled @mui/icons-material")
    run_command("npm run build")
    os.chdir("..")
    
    print("✓ Frontend setup complete")

def setup_nginx(config):
    """Set up nginx configuration"""
    print("Setting up nginx...")
    
    nginx_config = f"""server {{
    listen 80;
    server_name {config['DOMAIN']};
    
    location / {{
        root /home/{os.getenv('USER')}/nexads-panel/frontend/build;
        index index.html;
        try_files $uri $uri/ /index.html;
    }}
    
    location /api {{
        proxy_pass http://127.0.0.1:{config['BACKEND_PORT']};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
}}"""
    
    # Write nginx config
    with open('/tmp/nexads', 'w') as f:
        f.write(nginx_config)
    
    run_command("sudo mv /tmp/nexads /etc/nginx/sites-available/nexads")
    run_command("sudo ln -sf /etc/nginx/sites-available/nexads /etc/nginx/sites-enabled/nexads")
    
    # Test nginx config
    if run_command("sudo nginx -t"):
        run_command("sudo systemctl reload nginx")
        print("✓ Nginx configured")
    else:
        print("✗ Nginx configuration failed")
        return False
    
    return True

def setup_ssl(config):
    """Set up SSL with certbot"""
    if config['SSL'] == 'true':
        print("Setting up SSL...")
        
        # Check if domain resolves to this server
        print(f"Checking DNS resolution for {config['DOMAIN']}...")
        
        # First, try to get certificate with webroot method
        print("Attempting SSL certificate generation...")
        ssl_cmd = f"sudo certbot --nginx -d {config['DOMAIN']} --non-interactive --agree-tos --email admin@{config['DOMAIN']} --redirect"
        
        if run_command(ssl_cmd):
            print("✓ SSL certificate installed")
        else:
            print("⚠ SSL setup failed - continuing without SSL")
            print("Note: Make sure your domain points to this server's IP address")
            print("You can run the following command later to setup SSL:")
            print(f"sudo certbot --nginx -d {config['DOMAIN']} --non-interactive --agree-tos --email admin@{config['DOMAIN']}")
            
            # Update nginx config to work without SSL
            nginx_config = f"""server {{
    listen 80;
    server_name {config['DOMAIN']};
    
    location / {{
        root /home/{os.getenv('USER')}/nexads-panel/frontend/build;
        index index.html;
        try_files $uri $uri/ /index.html;
    }}
    
    location /api {{
        proxy_pass http://127.0.0.1:{config['BACKEND_PORT']};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
}}"""
            
            with open('/tmp/nexads', 'w') as f:
                f.write(nginx_config)
            
            run_command("sudo mv /tmp/nexads /etc/nginx/sites-available/nexads")
            run_command("sudo systemctl reload nginx")
            
            # Update .env to reflect no SSL
            config['SSL'] = 'false'
            create_env_file(config)
    
    return True

def start_services(config):
    """Start backend and frontend services"""
    print("Starting services...")
    
    # Start backend with PM2
    backend_cmd = f"cd /home/{os.getenv('USER')}/nexads-panel && python3 -m uvicorn backend.main:app --host 0.0.0.0 --port {config['BACKEND_PORT']}"
    run_command(f'pm2 start "{backend_cmd}" --name nexads-backend')
    
    # Start frontend is handled by nginx serving static files
    
    # Save PM2 processes
    run_command("pm2 save")
    run_command("pm2 startup")
    
    print("✓ Services started")

def main():
    """Main setup function"""
    try:
        # Get user configuration
        config = get_user_input()
        
        # Create .env file
        create_env_file(config)
        
        # Clean up previous installation
        cleanup_previous_installation()
        
        # Install dependencies
        install_dependencies()
        
        # Setup backend
        setup_backend()
        
        # Setup frontend
        setup_frontend()
        
        # Setup nginx
        if not setup_nginx(config):
            return
        
        # Setup SSL
        if not setup_ssl(config):
            return
        
        # Start services
        start_services(config)
        
        # Display comprehensive system information
        display_system_info(config)
        
    except KeyboardInterrupt:
        print("\nSetup cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"Setup failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
