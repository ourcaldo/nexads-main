
import os
import sys
import json
import subprocess
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Depends, status, UploadFile, File
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import secrets
from jose import JWTError, jwt
from passlib.context import CryptContext
import uvicorn
import multiprocessing
import signal
import time

# Add core directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'core'))

app = FastAPI(title="nexAds API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
security = HTTPBasic()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Configuration
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-here")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
AUTH_USERNAME = os.getenv("AUTH_USERNAME", "admin")
AUTH_PASSWORD = os.getenv("AUTH_PASSWORD", "admin123")

# Global variables
automation_process = None
automation_service_name = "nexads-automation"

# Pydantic models
class Token(BaseModel):
    access_token: str
    token_type: str

class User(BaseModel):
    username: str

class ConfigUpdate(BaseModel):
    config: Dict[str, Any]

class AutomationStatus(BaseModel):
    status: str
    pid: Optional[int] = None
    start_time: Optional[str] = None
    uptime: Optional[str] = None

class ProxyUpdate(BaseModel):
    proxies: str

# Helper functions
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, AUTH_USERNAME)
    correct_password = secrets.compare_digest(credentials.password, AUTH_PASSWORD)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

def run_command(command: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run shell command"""
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"Command failed: {result.stderr}")
    return result

def create_systemd_service():
    """Create systemd service for automation"""
    service_content = f"""[Unit]
Description=nexAds Automation Service
After=network.target

[Service]
Type=simple
User={os.getenv('USER', 'root')}
WorkingDirectory={os.path.abspath('../core')}
ExecStart=/usr/bin/python3 {os.path.abspath('../core/main.py')}
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
"""
    
    service_path = f"/etc/systemd/system/{automation_service_name}.service"
    with open(f"/tmp/{automation_service_name}.service", "w") as f:
        f.write(service_content)
    
    run_command(f"sudo mv /tmp/{automation_service_name}.service {service_path}")
    run_command("sudo systemctl daemon-reload")

def get_automation_status():
    """Get current automation status"""
    try:
        result = run_command(f"sudo systemctl status {automation_service_name}", check=False)
        
        if "active (running)" in result.stdout:
            # Get PID and start time
            pid_result = run_command(f"sudo systemctl show {automation_service_name} --property=MainPID", check=False)
            pid = pid_result.stdout.split("=")[1].strip() if "=" in pid_result.stdout else None
            
            start_result = run_command(f"sudo systemctl show {automation_service_name} --property=ActiveEnterTimestamp", check=False)
            start_time = start_result.stdout.split("=")[1].strip() if "=" in start_result.stdout else None
            
            return {
                "status": "running",
                "pid": int(pid) if pid and pid != "0" else None,
                "start_time": start_time,
                "uptime": "N/A"
            }
        elif "inactive (dead)" in result.stdout:
            return {"status": "stopped"}
        else:
            return {"status": "unknown"}
    except:
        return {"status": "error"}

# API Routes
@app.post("/api/auth/login", response_model=Token)
async def login(credentials: HTTPBasicCredentials = Depends(security)):
    """Login endpoint"""
    correct_username = secrets.compare_digest(credentials.username, AUTH_USERNAME)
    correct_password = secrets.compare_digest(credentials.password, AUTH_PASSWORD)
    
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": credentials.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/api/config")
async def get_config(current_user: str = Depends(get_current_user)):
    """Get current configuration"""
    try:
        config_path = "../core/config.json"
        if not os.path.exists(config_path):
            raise HTTPException(status_code=404, detail="Config file not found")
        
        with open(config_path, "r") as f:
            config = json.load(f)
        
        return {"config": config}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/config")
async def update_config(config_update: ConfigUpdate, current_user: str = Depends(get_current_user)):
    """Update configuration"""
    try:
        config_path = "../core/config.json"
        
        # Validate config structure
        required_keys = ["proxy", "browser", "delay", "session", "threads", "os_fingerprint", "device_type", "referrer", "urls", "ads"]
        for key in required_keys:
            if key not in config_update.config:
                raise HTTPException(status_code=400, detail=f"Missing required key: {key}")
        
        # Save config
        with open(config_path, "w") as f:
            json.dump(config_update.config, f, indent=4)
        
        return {"message": "Configuration updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/proxy")
async def get_proxy(current_user: str = Depends(get_current_user)):
    """Get proxy list"""
    try:
        proxy_path = "../core/proxy.txt"
        if not os.path.exists(proxy_path):
            return {"proxies": ""}
        
        with open(proxy_path, "r") as f:
            proxies = f.read()
        
        return {"proxies": proxies}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/proxy")
async def update_proxy(proxy_update: ProxyUpdate, current_user: str = Depends(get_current_user)):
    """Update proxy list"""
    try:
        proxy_path = "../core/proxy.txt"
        
        with open(proxy_path, "w") as f:
            f.write(proxy_update.proxies)
        
        return {"message": "Proxy list updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/automation/status")
async def get_automation_status_endpoint(current_user: str = Depends(get_current_user)):
    """Get automation status"""
    status = get_automation_status()
    return status

@app.post("/api/automation/start")
async def start_automation(current_user: str = Depends(get_current_user)):
    """Start automation"""
    try:
        # Create systemd service
        create_systemd_service()
        
        # Start service
        run_command(f"sudo systemctl start {automation_service_name}")
        run_command(f"sudo systemctl enable {automation_service_name}")
        
        return {"message": "Automation started successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/automation/stop")
async def stop_automation(current_user: str = Depends(get_current_user)):
    """Stop automation"""
    try:
        # Stop service
        run_command(f"sudo systemctl stop {automation_service_name}", check=False)
        run_command(f"sudo systemctl disable {automation_service_name}", check=False)
        
        # Remove service file
        run_command(f"sudo rm -f /etc/systemd/system/{automation_service_name}.service", check=False)
        run_command("sudo systemctl daemon-reload", check=False)
        
        return {"message": "Automation stopped successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/automation/restart")
async def restart_automation(current_user: str = Depends(get_current_user)):
    """Restart automation"""
    try:
        # Stop first
        run_command(f"sudo systemctl stop {automation_service_name}", check=False)
        
        # Start again
        run_command(f"sudo systemctl start {automation_service_name}")
        
        return {"message": "Automation restarted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/logs")
async def get_logs(current_user: str = Depends(get_current_user)):
    """Get automation logs"""
    try:
        result = run_command(f"sudo journalctl -u {automation_service_name} -n 100 --no-pager", check=False)
        return {"logs": result.stdout}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    port = int(os.getenv("BACKEND_PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
