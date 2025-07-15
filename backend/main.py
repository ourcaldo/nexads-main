#!/usr/bin/env python3
"""
nexAds Backend API
FastAPI backend for managing the nexAds automation
"""

import os
import sys
import json
import asyncio
import subprocess
import signal
import psutil
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from pathlib import Path

from fastapi import FastAPI, HTTPException, Depends, status, BackgroundTasks
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from jose import JWTError, jwt
from passlib.context import CryptContext
import uvicorn

# Add core directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'core'))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

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
security = HTTPBearer()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY = os.getenv("JWT_SECRET", "fallback-secret-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Authentication credentials
AUTH_USERNAME = os.getenv("AUTH_USERNAME", "admin")
AUTH_PASSWORD = os.getenv("AUTH_PASSWORD", "admin123")

# Paths
CORE_DIR = Path(__file__).parent.parent / "core"
CONFIG_FILE = CORE_DIR / "config.json"
PROXY_FILE = CORE_DIR / "proxy.txt"
MAIN_SCRIPT = CORE_DIR / "main.py"

# Global variables for process management
automation_process = None
automation_status = "stopped"  # stopped, running, paused

# Pydantic models
class LoginRequest(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class ConfigUpdate(BaseModel):
    config: Dict[str, Any]

class ProxyUpdate(BaseModel):
    proxies: str

class AutomationCommand(BaseModel):
    action: str  # start, stop, pause, resume

class StatusResponse(BaseModel):
    status: str
    pid: Optional[int] = None
    uptime: Optional[str] = None
    memory_usage: Optional[float] = None
    cpu_usage: Optional[float] = None

# Authentication functions
def verify_password(plain_password, hashed_password):
    """Verify a password against its hash"""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    """Hash a password"""
    return pwd_context.hash(password)

def authenticate_user(username: str, password: str):
    """Authenticate user credentials"""
    if username == AUTH_USERNAME and password == AUTH_PASSWORD:
        return {"username": username}
    return False

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get current authenticated user"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    if username != AUTH_USERNAME:
        raise credentials_exception
    
    return {"username": username}

# Utility functions
def load_config():
    """Load configuration from JSON file"""
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Configuration file not found")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON in configuration file")

def save_config(config_data):
    """Save configuration to JSON file"""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config_data, f, indent=4)
        return True
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save configuration: {str(e)}")

def load_proxies():
    """Load proxies from text file"""
    try:
        if PROXY_FILE.exists():
            with open(PROXY_FILE, 'r') as f:
                return f.read().strip()
        return ""
    except Exception:
        return ""

def save_proxies(proxy_data):
    """Save proxies to text file"""
    try:
        with open(PROXY_FILE, 'w') as f:
            f.write(proxy_data.strip())
        return True
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save proxies: {str(e)}")

def get_process_info(pid):
    """Get process information"""
    try:
        process = psutil.Process(pid)
        return {
            "memory_usage": process.memory_info().rss / 1024 / 1024,  # MB
            "cpu_usage": process.cpu_percent(),
            "create_time": process.create_time()
        }
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None

def create_systemd_service(service_name, script_path):
    """Create a systemd service for the automation"""
    service_content = f"""[Unit]
Description=nexAds Automation Service
After=network.target

[Service]
Type=simple
User={os.getenv('USER', 'root')}
WorkingDirectory={CORE_DIR}
ExecStart=/usr/bin/python3 {script_path}
Restart=no
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""
    
    service_file = f"/etc/systemd/system/{service_name}.service"
    
    try:
        # Write service file
        with open(f"/tmp/{service_name}.service", 'w') as f:
            f.write(service_content)
        
        # Move to systemd directory
        subprocess.run(f"sudo mv /tmp/{service_name}.service {service_file}", shell=True, check=True)
        
        # Reload systemd
        subprocess.run("sudo systemctl daemon-reload", shell=True, check=True)
        
        return service_file
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create service: {str(e)}")

def remove_systemd_service(service_name):
    """Remove systemd service"""
    try:
        subprocess.run(f"sudo systemctl stop {service_name}", shell=True, check=False)
        subprocess.run(f"sudo systemctl disable {service_name}", shell=True, check=False)
        subprocess.run(f"sudo rm -f /etc/systemd/system/{service_name}.service", shell=True, check=False)
        subprocess.run("sudo systemctl daemon-reload", shell=True, check=False)
    except Exception:
        pass  # Ignore errors during cleanup

# API Routes
@app.post("/api/auth/login", response_model=Token)
async def login(login_data: LoginRequest):
    """Authenticate user and return JWT token"""
    user = authenticate_user(login_data.username, login_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["username"]}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/api/config")
async def get_config(current_user: dict = Depends(get_current_user)):
    """Get current configuration"""
    return load_config()

@app.post("/api/config")
async def update_config(config_update: ConfigUpdate, current_user: dict = Depends(get_current_user)):
    """Update configuration"""
    save_config(config_update.config)
    return {"message": "Configuration updated successfully"}

@app.get("/api/proxies")
async def get_proxies(current_user: dict = Depends(get_current_user)):
    """Get current proxy list"""
    return {"proxies": load_proxies()}

@app.post("/api/proxies")
async def update_proxies(proxy_update: ProxyUpdate, current_user: dict = Depends(get_current_user)):
    """Update proxy list"""
    save_proxies(proxy_update.proxies)
    return {"message": "Proxies updated successfully"}

@app.get("/api/status", response_model=StatusResponse)
async def get_status(current_user: dict = Depends(get_current_user)):
    """Get automation status"""
    global automation_process, automation_status
    
    if automation_status == "running" and automation_process:
        # Check if process is still running
        try:
            result = subprocess.run(f"systemctl is-active nexads-automation", 
                                  shell=True, capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip() == "active":
                # Get process info
                try:
                    result = subprocess.run("systemctl show nexads-automation --property=MainPID", 
                                          shell=True, capture_output=True, text=True)
                    pid = int(result.stdout.split('=')[1].strip())
                    
                    if pid > 0:
                        process_info = get_process_info(pid)
                        if process_info:
                            uptime = datetime.now() - datetime.fromtimestamp(process_info["create_time"])
                            return StatusResponse(
                                status="running",
                                pid=pid,
                                uptime=str(uptime).split('.')[0],
                                memory_usage=process_info["memory_usage"],
                                cpu_usage=process_info["cpu_usage"]
                            )
                except:
                    pass
            else:
                automation_status = "stopped"
        except:
            automation_status = "stopped"
    
    return StatusResponse(status=automation_status)

@app.post("/api/automation")
async def control_automation(command: AutomationCommand, background_tasks: BackgroundTasks, 
                           current_user: dict = Depends(get_current_user)):
    """Control automation (start/stop/pause/resume)"""
    global automation_process, automation_status
    
    if command.action == "start":
        if automation_status == "running":
            raise HTTPException(status_code=400, detail="Automation is already running")
        
        try:
            # Create systemd service
            service_file = create_systemd_service("nexads-automation", MAIN_SCRIPT)
            
            # Start service
            subprocess.run("sudo systemctl start nexads-automation", shell=True, check=True)
            subprocess.run("sudo systemctl enable nexads-automation", shell=True, check=True)
            
            automation_status = "running"
            return {"message": "Automation started successfully"}
            
        except subprocess.CalledProcessError as e:
            raise HTTPException(status_code=500, detail=f"Failed to start automation: {str(e)}")
    
    elif command.action == "stop":
        if automation_status == "stopped":
            raise HTTPException(status_code=400, detail="Automation is not running")
        
        try:
            # Stop and remove service
            subprocess.run("sudo systemctl stop nexads-automation", shell=True, check=False)
            remove_systemd_service("nexads-automation")
            
            automation_status = "stopped"
            automation_process = None
            return {"message": "Automation stopped successfully"}
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to stop automation: {str(e)}")
    
    elif command.action == "pause":
        if automation_status != "running":
            raise HTTPException(status_code=400, detail="Automation is not running")
        
        try:
            # Send SIGSTOP to pause the process
            result = subprocess.run("systemctl show nexads-automation --property=MainPID", 
                                  shell=True, capture_output=True, text=True)
            pid = int(result.stdout.split('=')[1].strip())
            
            if pid > 0:
                os.kill(pid, signal.SIGSTOP)
                automation_status = "paused"
                return {"message": "Automation paused successfully"}
            else:
                raise HTTPException(status_code=500, detail="Could not find process to pause")
                
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to pause automation: {str(e)}")
    
    elif command.action == "resume":
        if automation_status != "paused":
            raise HTTPException(status_code=400, detail="Automation is not paused")
        
        try:
            # Send SIGCONT to resume the process
            result = subprocess.run("systemctl show nexads-automation --property=MainPID", 
                                  shell=True, capture_output=True, text=True)
            pid = int(result.stdout.split('=')[1].strip())
            
            if pid > 0:
                os.kill(pid, signal.SIGCONT)
                automation_status = "running"
                return {"message": "Automation resumed successfully"}
            else:
                raise HTTPException(status_code=500, detail="Could not find process to resume")
                
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to resume automation: {str(e)}")
    
    else:
        raise HTTPException(status_code=400, detail="Invalid action")

@app.get("/api/logs")
async def get_logs(lines: int = 100, current_user: dict = Depends(get_current_user)):
    """Get automation logs"""
    try:
        result = subprocess.run(f"journalctl -u nexads-automation -n {lines} --no-pager", 
                              shell=True, capture_output=True, text=True)
        return {"logs": result.stdout}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get logs: {str(e)}")

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

if __name__ == "__main__":
    port = int(os.getenv("BACKEND_PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)