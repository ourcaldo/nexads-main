# nexAds Web Interface

A comprehensive web-based control panel for managing the nexAds automation system.

## Features

- **Dashboard**: Real-time status monitoring with system metrics
- **Configuration Management**: Web-based config editor with validation
- **Proxy Management**: Upload and manage proxy lists
- **Log Viewer**: Real-time log monitoring with filtering
- **Authentication**: Secure login system
- **Process Control**: Start, stop, pause, and resume automation
- **Production Ready**: SSL support, nginx configuration, PM2 process management

## Quick Setup

1. **Run the setup script**:
   ```bash
   python3 setup.py
   ```

2. **Follow the prompts**:
   - Enter your domain (or press Enter for localhost)
   - Set frontend port (default: 4000)
   - Set backend port (default: 8000)
   - Choose SSL configuration

3. **Access the panel**:
   - Open your browser and navigate to your configured domain
   - Login with: `admin` / `admin123`

## Manual Installation

### Prerequisites

```bash
# Install Node.js 18+
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs

# Install PM2
sudo npm install -g pm2

# Install nginx
sudo apt-get install -y nginx

# Install certbot (for SSL)
sudo apt-get install -y certbot python3-certbot-nginx
```

### Backend Setup

```bash
# Install Python dependencies
pip3 install -r backend/requirements.txt

# Start backend
cd backend
python3 main.py
```

### Frontend Setup

```bash
# Install dependencies
cd frontend
npm install

# Build for production
npm run build

# Start frontend
npm start
```

## Configuration

### Environment Variables

Create a `.env` file in the root directory:

```env
DOMAIN=your-domain.com
FRONTEND_PORT=4000
BACKEND_PORT=8000
SSL_ENABLED=true
AUTH_USERNAME=admin
AUTH_PASSWORD=admin123
JWT_SECRET=your-secret-key
```

### Nginx Configuration

The setup script automatically configures nginx, but you can manually configure it:

```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    location /api {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    
    location / {
        proxy_pass http://localhost:4000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## API Endpoints

### Authentication
- `POST /api/auth/login` - Login and get JWT token

### Configuration
- `GET /api/config` - Get current configuration
- `POST /api/config` - Update configuration

### Proxy Management
- `GET /api/proxies` - Get proxy list
- `POST /api/proxies` - Update proxy list

### Automation Control
- `GET /api/status` - Get automation status
- `POST /api/automation` - Control automation (start/stop/pause/resume)

### Logs
- `GET /api/logs` - Get system logs

## Security Features

- JWT-based authentication
- HTTPS/SSL support
- Security headers (X-Frame-Options, CSP, etc.)
- No indexing (robots.txt)
- Input validation and sanitization
- CORS protection

## Process Management

The system uses systemd services for reliable process management:

- Automatic restart on failure
- Proper logging via journald
- Clean shutdown handling
- Resource monitoring

## Monitoring

The dashboard provides real-time monitoring of:

- Process status (running/stopped/paused)
- System metrics (CPU, memory usage)
- Uptime tracking
- Log analysis

## Troubleshooting

### Common Issues

1. **Port already in use**:
   ```bash
   sudo lsof -i :4000  # Check what's using the port
   sudo kill -9 <PID>  # Kill the process
   ```

2. **Permission denied**:
   ```bash
   sudo chown -R $USER:$USER .
   chmod +x setup.py
   ```

3. **SSL certificate issues**:
   ```bash
   sudo certbot renew --dry-run
   sudo nginx -t
   sudo systemctl reload nginx
   ```

4. **Service not starting**:
   ```bash
   pm2 logs nexads-backend
   pm2 logs nexads-frontend
   journalctl -u nexads-automation -f
   ```

### Log Locations

- Backend logs: `pm2 logs nexads-backend`
- Frontend logs: `pm2 logs nexads-frontend`
- Automation logs: `journalctl -u nexads-automation`
- Nginx logs: `/var/log/nginx/`

## Development

### Backend Development

```bash
cd backend
pip3 install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Frontend Development

```bash
cd frontend
npm install
npm run dev
```

## Production Deployment

The setup script handles production deployment automatically:

1. Builds optimized frontend
2. Configures nginx with security headers
3. Sets up SSL certificates
4. Starts services with PM2
5. Configures automatic startup

## License

This project is for educational purposes only.