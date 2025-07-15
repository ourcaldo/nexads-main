
from fastapi import FastAPI, HTTPException, Depends, status, File, UploadFile, BackgroundTasks
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import json
import os
import subprocess
import secrets
import hashlib
from pathlib import Path
from datetime import datetime
import psutil
import signal
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = FastAPI(title="NexAds Control Panel", version="1.0.0")

# Security
security = HTTPBasic()

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global variables
automation_process = None
automation_status = "stopped"  # stopped, running, paused

# Models
class LoginRequest(BaseModel):
    username: str
    password: str

class ConfigUpdate(BaseModel):
    config: Dict[str, Any]

class ProxyUpdate(BaseModel):
    proxies: str

class AutomationCommand(BaseModel):
    command: str  # start, pause, stop

# Authentication
def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, os.getenv("USERNAME", "admin"))
    correct_password = secrets.compare_digest(credentials.password, os.getenv("PASSWORD", "admin123"))
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

# Utility functions
def get_config_path():
    return Path("core/config.json")

def get_proxy_path():
    return Path("core/proxy.txt")

def get_service_path():
    return Path("/etc/systemd/system/nexads-automation.service")

def load_config():
    """Load configuration from JSON file"""
    try:
        with open(get_config_path(), 'r') as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load config: {str(e)}")

def save_config(config_data):
    """Save configuration to JSON file"""
    try:
        with open(get_config_path(), 'w') as f:
            json.dump(config_data, f, indent=4)
        return True
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save config: {str(e)}")

def load_proxies():
    """Load proxies from file"""
    try:
        proxy_file = get_proxy_path()
        if proxy_file.exists():
            with open(proxy_file, 'r') as f:
                return f.read().strip()
        return ""
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load proxies: {str(e)}")

def save_proxies(proxies_text):
    """Save proxies to file"""
    try:
        with open(get_proxy_path(), 'w') as f:
            f.write(proxies_text)
        return True
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save proxies: {str(e)}")

def create_service_file():
    """Create systemd service file"""
    user = os.getenv("USER")
    working_dir = os.getcwd()
    
    service_content = f"""[Unit]
Description=NexAds Automation Service
After=network.target

[Service]
Type=simple
User={user}
WorkingDirectory={working_dir}/core
ExecStart=/usr/bin/python3 main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
"""
    
    try:
        with open('/tmp/nexads-automation.service', 'w') as f:
            f.write(service_content)
        
        # Move to systemd directory
        subprocess.run(['sudo', 'mv', '/tmp/nexads-automation.service', '/etc/systemd/system/'], check=True)
        subprocess.run(['sudo', 'systemctl', 'daemon-reload'], check=True)
        
        return True
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create service: {str(e)}")

def get_automation_status():
    """Get current automation status"""
    try:
        # Check if service exists and is running
        result = subprocess.run(['sudo', 'systemctl', 'is-active', 'nexads-automation.service'], 
                              capture_output=True, text=True)
        
        if result.returncode == 0 and result.stdout.strip() == 'active':
            return "running"
        else:
            return "stopped"
    except:
        return "stopped"

def get_system_stats():
    """Get system statistics"""
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        return {
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent,
            "memory_used": memory.used,
            "memory_total": memory.total,
            "disk_percent": disk.percent,
            "disk_used": disk.used,
            "disk_total": disk.total
        }
    except Exception as e:
        return {"error": str(e)}

# API Routes
@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.post("/api/login")
async def login(request: LoginRequest):
    correct_username = secrets.compare_digest(request.username, os.getenv("USERNAME", "admin"))
    correct_password = secrets.compare_digest(request.password, os.getenv("PASSWORD", "admin123"))
    
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
    
    return {"message": "Login successful", "token": "authenticated"}

@app.get("/api/config")
async def get_config(username: str = Depends(verify_credentials)):
    """Get current configuration"""
    config = load_config()
    return {"config": config}

@app.post("/api/config")
async def update_config(request: ConfigUpdate, username: str = Depends(verify_credentials)):
    """Update configuration"""
    save_config(request.config)
    return {"message": "Configuration updated successfully"}

@app.get("/api/proxies")
async def get_proxies(username: str = Depends(verify_credentials)):
    """Get proxy list"""
    proxies = load_proxies()
    return {"proxies": proxies}

@app.post("/api/proxies")
async def update_proxies(request: ProxyUpdate, username: str = Depends(verify_credentials)):
    """Update proxy list"""
    save_proxies(request.proxies)
    return {"message": "Proxies updated successfully"}

@app.get("/api/automation/status")
async def automation_status(username: str = Depends(verify_credentials)):
    """Get automation status"""
    status = get_automation_status()
    return {"status": status}

@app.post("/api/automation/control")
async def control_automation(request: AutomationCommand, username: str = Depends(verify_credentials)):
    """Control automation (start/pause/stop)"""
    command = request.command.lower()
    
    try:
        if command == "start":
            # Create service file
            create_service_file()
            
            # Start service
            subprocess.run(['sudo', 'systemctl', 'enable', 'nexads-automation.service'], check=True)
            subprocess.run(['sudo', 'systemctl', 'start', 'nexads-automation.service'], check=True)
            
            return {"message": "Automation started successfully"}
            
        elif command == "stop":
            # Stop service
            subprocess.run(['sudo', 'systemctl', 'stop', 'nexads-automation.service'], check=False)
            subprocess.run(['sudo', 'systemctl', 'disable', 'nexads-automation.service'], check=False)
            
            # Remove service file
            subprocess.run(['sudo', 'rm', '-f', '/etc/systemd/system/nexads-automation.service'], check=False)
            subprocess.run(['sudo', 'systemctl', 'daemon-reload'], check=False)
            
            return {"message": "Automation stopped successfully"}
            
        elif command == "pause":
            # Pause service (stop without disabling)
            subprocess.run(['sudo', 'systemctl', 'stop', 'nexads-automation.service'], check=True)
            
            return {"message": "Automation paused successfully"}
            
        else:
            raise HTTPException(status_code=400, detail="Invalid command")
            
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Command failed: {str(e)}")

@app.get("/api/logs")
async def get_logs(username: str = Depends(verify_credentials), lines: int = 100):
    """Get automation logs"""
    try:
        result = subprocess.run(['sudo', 'journalctl', '-u', 'nexads-automation.service', '-n', str(lines)], 
                              capture_output=True, text=True)
        
        if result.returncode == 0:
            return {"logs": result.stdout}
        else:
            return {"logs": "No logs available"}
            
    except Exception as e:
        return {"logs": f"Error fetching logs: {str(e)}"}

@app.get("/api/stats")
async def get_stats(username: str = Depends(verify_credentials)):
    """Get system statistics"""
    stats = get_system_stats()
    automation_status = get_automation_status()
    
    return {
        "system": stats,
        "automation": {
            "status": automation_status,
            "uptime": "N/A"  # Could be enhanced to show actual uptime
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("BACKEND_PORT", "8000")))
