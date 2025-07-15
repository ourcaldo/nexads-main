
# nexAds Automation Panel

A web-based control panel for managing the nexAds automation tool.

## Features

- **Web Dashboard**: Modern, responsive interface for managing automation
- **Real-time Control**: Start, stop, and restart automation from the web interface
- **Configuration Management**: Edit all settings through the web interface
- **Proxy Management**: Add, edit, and manage proxy lists
- **Live Logs**: View system logs in real-time
- **Authentication**: Secure login system
- **Production Ready**: Automatic nginx setup with SSL support

## Quick Start

1. Run the deployment script:
   ```bash
   python3 deploy.py
   ```

2. Follow the prompts to configure your domain and ports

3. Access the panel at your configured domain

4. Login with default credentials:
   - Username: `admin`
   - Password: `admin123`

## Manual Installation

If you prefer to install manually:

1. Install dependencies:
   ```bash
   pip3 install -r core/requirements.txt
   pip3 install fastapi uvicorn python-multipart aiofiles bcrypt python-jose[cryptography]
   ```

2. Install frontend dependencies:
   ```bash
   cd frontend
   npm install
   npm run build
   cd ..
   ```

3. Start the backend:
   ```bash
   cd backend
   python3 main.py
   ```

4. Serve the frontend (in another terminal):
   ```bash
   cd frontend
   npm start
   ```

## Configuration

The system uses environment variables for configuration. See `.env.example` for available options.

## Security

- Change default credentials in production
- Use SSL for public deployments
- Restrict access with firewall rules
- Regular security updates

## API Endpoints

- `POST /api/auth/login` - Authentication
- `GET /api/config` - Get configuration
- `POST /api/config` - Update configuration
- `GET /api/proxy` - Get proxy list
- `POST /api/proxy` - Update proxy list
- `GET /api/automation/status` - Get automation status
- `POST /api/automation/start` - Start automation
- `POST /api/automation/stop` - Stop automation
- `POST /api/automation/restart` - Restart automation
- `GET /api/logs` - Get system logs

## Systemd Service

The automation runs as a systemd service for reliability:

```bash
# Check status
sudo systemctl status nexads-automation

# View logs
sudo journalctl -u nexads-automation -f

# Manual control
sudo systemctl start nexads-automation
sudo systemctl stop nexads-automation
```

## Support

For issues and questions, please refer to the documentation or create an issue in the repository.
