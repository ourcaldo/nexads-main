import React, { useState, useEffect } from 'react';
import {
  AppBar,
  Toolbar,
  Typography,
  Container,
  Paper,
  Grid,
  Card,
  CardContent,
  Button,
  TextField,
  Box,
  Alert,
  Chip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  FormControl,
  FormLabel,
  FormGroup,
  FormControlLabel,
  Checkbox,
  Switch,
  MenuItem,
  Select,
  Slider,
  TextareaAutosize,
  Table,
  TableHead,
  TableRow,
  TableCell,
  TableBody,
  IconButton,
  Snackbar
} from '@mui/material';
import {
  PlayArrow,
  Pause,
  Stop,
  Settings,
  Computer,
  Speed,
  Delete,
  Add,
  Visibility,
  VisibilityOff
} from '@mui/icons-material';
import axios from 'axios';

const API_BASE = '/api';

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [automationStatus, setAutomationStatus] = useState('stopped');
  const [config, setConfig] = useState({});
  const [proxies, setProxies] = useState('');
  const [logs, setLogs] = useState('');
  const [stats, setStats] = useState({});
  const [configDialog, setConfigDialog] = useState(false);
  const [proxyDialog, setProxyDialog] = useState(false);
  const [logsDialog, setLogsDialog] = useState(false);
  const [alert, setAlert] = useState({ show: false, message: '', severity: 'info' });
  const [loading, setLoading] = useState(false);

  // Create axios instance with auth
  const api = axios.create({
    baseURL: API_BASE,
    auth: {
      username: username,
      password: password
    }
  });

  useEffect(() => {
    if (isAuthenticated) {
      fetchStatus();
      fetchConfig();
      fetchProxies();
      fetchStats();

      // Set up polling
      const interval = setInterval(() => {
        fetchStatus();
        fetchStats();
      }, 5000);

      return () => clearInterval(interval);
    }
  }, [isAuthenticated]);

  const handleLogin = async () => {
    try {
      setLoading(true);
      await api.post('/login', { username, password });
      setIsAuthenticated(true);
      showAlert('Login successful', 'success');
    } catch (error) {
      showAlert('Login failed', 'error');
    } finally {
      setLoading(false);
    }
  };

  const fetchStatus = async () => {
    try {
      const response = await api.get('/automation/status');
      setAutomationStatus(response.data.status);
    } catch (error) {
      console.error('Failed to fetch status:', error);
    }
  };

  const fetchConfig = async () => {
    try {
      const response = await api.get('/config');
      setConfig(response.data.config);
    } catch (error) {
      console.error('Failed to fetch config:', error);
    }
  };

  const fetchProxies = async () => {
    try {
      const response = await api.get('/proxies');
      setProxies(response.data.proxies);
    } catch (error) {
      console.error('Failed to fetch proxies:', error);
    }
  };

  const fetchStats = async () => {
    try {
      const response = await api.get('/stats');
      setStats(response.data);
    } catch (error) {
      console.error('Failed to fetch stats:', error);
    }
  };

  const fetchLogs = async () => {
    try {
      const response = await api.get('/logs');
      setLogs(response.data.logs);
    } catch (error) {
      console.error('Failed to fetch logs:', error);
    }
  };

  const controlAutomation = async (command) => {
    try {
      setLoading(true);
      await api.post('/automation/control', { command });
      showAlert(`Automation ${command}ed successfully`, 'success');
      fetchStatus();
    } catch (error) {
      showAlert(`Failed to ${command} automation`, 'error');
    } finally {
      setLoading(false);
    }
  };

  const saveConfig = async () => {
    try {
      setLoading(true);
      await api.post('/config', { config });
      showAlert('Configuration saved successfully', 'success');
      setConfigDialog(false);
    } catch (error) {
      showAlert('Failed to save configuration', 'error');
    } finally {
      setLoading(false);
    }
  };

  const saveProxies = async () => {
    try {
      setLoading(true);
      await api.post('/proxies', { proxies });
      showAlert('Proxies saved successfully', 'success');
      setProxyDialog(false);
    } catch (error) {
      showAlert('Failed to save proxies', 'error');
    } finally {
      setLoading(false);
    }
  };

  const showAlert = (message, severity) => {
    setAlert({ show: true, message, severity });
  };

  const updateConfig = (path, value) => {
    const newConfig = { ...config };
    const keys = path.split('.');
    let current = newConfig;

    for (let i = 0; i < keys.length - 1; i++) {
      current = current[keys[i]];
    }

    current[keys[keys.length - 1]] = value;
    setConfig(newConfig);
  };

  const addUrl = () => {
    const newUrl = {
      url: '',
      random_page: false,
      min_time: 30,
      max_time: 60
    };
    setConfig({
      ...config,
      urls: [...(config.urls || []), newUrl]
    });
  };

  const removeUrl = (index) => {
    const newUrls = config.urls.filter((_, i) => i !== index);
    setConfig({
      ...config,
      urls: newUrls
    });
  };

  const updateUrl = (index, field, value) => {
    const newUrls = [...config.urls];
    newUrls[index][field] = value;
    setConfig({
      ...config,
      urls: newUrls
    });
  };

  if (!isAuthenticated) {
    return (
      <Container maxWidth="sm" style={{ marginTop: '100px' }}>
        <Paper elevation={3} style={{ padding: '40px' }}>
          <Typography variant="h4" align="center" gutterBottom>
            NexAds Control Panel
          </Typography>
          <Box component="form" onSubmit={(e) => { e.preventDefault(); handleLogin(); }}>
            <TextField
              fullWidth
              label="Username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              margin="normal"
              required
            />
            <TextField
              fullWidth
              label="Password"
              type={showPassword ? 'text' : 'password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              margin="normal"
              required
              InputProps={{
                endAdornment: (
                  <IconButton onClick={() => setShowPassword(!showPassword)}>
                    {showPassword ? <VisibilityOff /> : <Visibility />}
                  </IconButton>
                )
              }}
            />
            <Button
              type="submit"
              fullWidth
              variant="contained"
              style={{ marginTop: '20px' }}
              disabled={loading}
            >
              {loading ? 'Logging in...' : 'Login'}
            </Button>
          </Box>
        </Paper>
      </Container>
    );
  }

  return (
    <div>
      <AppBar position="static">
        <Toolbar>
          <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
            NexAds Control Panel
          </Typography>
          <Chip
            label={automationStatus.toUpperCase()}
            color={automationStatus === 'running' ? 'success' : 'default'}
            variant="outlined"
            style={{ color: 'white' }}
          />
        </Toolbar>
      </AppBar>

      <Container maxWidth="lg" style={{ marginTop: '20px' }}>
        <Grid container spacing={3}>
          {/* Control Panel */}
          <Grid item xs={12} md={6}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Automation Control
                </Typography>
                <Box display="flex" gap={2}>
                  <Button
                    variant="contained"
                    color="success"
                    startIcon={<PlayArrow />}
                    onClick={() => controlAutomation('start')}
                    disabled={automationStatus === 'running' || loading}
                  >
                    Start
                  </Button>
                  <Button
                    variant="contained"
                    color="warning"
                    startIcon={<Pause />}
                    onClick={() => controlAutomation('pause')}
                    disabled={automationStatus !== 'running' || loading}
                  >
                    Pause
                  </Button>
                  <Button
                    variant="contained"
                    color="error"
                    startIcon={<Stop />}
                    onClick={() => controlAutomation('stop')}
                    disabled={automationStatus === 'stopped' || loading}
                  >
                    Stop
                  </Button>
                </Box>
              </CardContent>
            </Card>
          </Grid>

          {/* System Stats */}
          <Grid item xs={12} md={6}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  System Statistics
                </Typography>
                {stats.system && (
                  <Box>
                    <Typography variant="body2">
                      CPU: {stats.system.cpu_percent}%
                    </Typography>
                    <Typography variant="body2">
                      Memory: {stats.system.memory_percent}%
                    </Typography>
                    <Typography variant="body2">
                      Disk: {stats.system.disk_percent}%
                    </Typography>
                  </Box>
                )}
              </CardContent>
            </Card>
          </Grid>

          {/* Management Buttons */}
          <Grid item xs={12}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Management
                </Typography>
                <Box display="flex" gap={2}>
                  <Button
                    variant="outlined"
                    startIcon={<Settings />}
                    onClick={() => setConfigDialog(true)}
                  >
                    Configuration
                  </Button>
                  <Button
                    variant="outlined"
                    startIcon={<Computer />}
                    onClick={() => setProxyDialog(true)}
                  >
                    Proxies
                  </Button>
                  <Button
                    variant="outlined"
                    startIcon={<Speed />}
                    onClick={() => { fetchLogs(); setLogsDialog(true); }}
                  >
                    Logs
                  </Button>
                </Box>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </Container>

      {/* Configuration Dialog */}
      <Dialog open={configDialog} onClose={() => setConfigDialog(false)} maxWidth="md" fullWidth>
        <DialogTitle>Configuration Settings</DialogTitle>
        <DialogContent>
          {config.proxy && (
            <Box mb={3}>
              <Typography variant="h6">Proxy Settings</Typography>
              <TextField
                fullWidth
                label="Proxy Type"
                select
                value={config.proxy.type}
                onChange={(e) => updateConfig('proxy.type', e.target.value)}
                margin="normal"
              >
                <MenuItem value="http">HTTP</MenuItem>
                <MenuItem value="https">HTTPS</MenuItem>
                <MenuItem value="socks4">SOCKS4</MenuItem>
                <MenuItem value="socks5">SOCKS5</MenuItem>
              </TextField>
              <TextField
                fullWidth
                label="Proxy Credentials"
                value={config.proxy.credentials}
                onChange={(e) => updateConfig('proxy.credentials', e.target.value)}
                margin="normal"
                placeholder="user:pass@ip:port or ip:port"
              />
            </Box>
          )}

          {config.browser && (
            <Box mb={3}>
              <Typography variant="h6">Browser Settings</Typography>
              <FormControl component="fieldset" margin="normal">
                <FormLabel component="legend">Headless Mode</FormLabel>
                <FormGroup>
                  <FormControlLabel
                    control={
                      <Switch
                        checked={config.browser?.headless_mode === 'True'}
                        onChange={(e) => updateConfig('browser.headless_mode', e.target.checked ? 'True' : 'False')}
                      />
                    }
                    label="Headless Mode"
                  />
                </FormGroup>
              </FormControl>

              <FormControlLabel
                control={
                  <Checkbox
                    checked={config.browser.disable_ublock}
                    onChange={(e) => updateConfig('browser.disable_ublock', e.target.checked)}
                  />
                }
                label="Disable uBlock"
              />

              <FormControlLabel
                control={
                  <Checkbox
                    checked={config.browser.random_activity}
                    onChange={(e) => updateConfig('browser.random_activity', e.target.checked)}
                  />
                }
                label="Random Activity"
              />

              <FormControlLabel
                control={
                  <Checkbox
                    checked={config.browser.auto_accept_cookies}
                    onChange={(e) => updateConfig('browser.auto_accept_cookies', e.target.checked)}
                  />
                }
                label="Auto Accept Cookies"
              />
            </Box>
          )}

          {config.urls && (
            <Box mb={3}>
              <Typography variant="h6">URLs</Typography>
              <Button startIcon={<Add />} onClick={addUrl} style={{ marginBottom: '10px' }}>
                Add URL
              </Button>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>URL</TableCell>
                    <TableCell>Random Page</TableCell>
                    <TableCell>Min Time</TableCell>
                    <TableCell>Max Time</TableCell>
                    <TableCell>Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {config.urls.map((url, index) => (
                    <TableRow key={index}>
                      <TableCell>
                        <TextField
                          value={url.url}
                          onChange={(e) => updateUrl(index, 'url', e.target.value)}
                          size="small"
                        />
                      </TableCell>
                      <TableCell>
                        <Checkbox
                          checked={url.random_page}
                          onChange={(e) => updateUrl(index, 'random_page', e.target.checked)}
                        />
                      </TableCell>
                      <TableCell>
                        <TextField
                          type="number"
                          value={url.min_time}
                          onChange={(e) => updateUrl(index, 'min_time', parseInt(e.target.value))}
                          size="small"
                        />
                      </TableCell>
                      <TableCell>
                        <TextField
                          type="number"
                          value={url.max_time}
                          onChange={(e) => updateUrl(index, 'max_time', parseInt(e.target.value))}
                          size="small"
                        />
                      </TableCell>
                      <TableCell>
                        <IconButton onClick={() => removeUrl(index)}>
                          <Delete />
                        </IconButton>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Box>
          )}

          {config.threads && (
            <Box mb={3}>
              <Typography variant="h6">Threads</Typography>
              <TextField
                type="number"
                label="Number of Threads"
                value={config.threads}
                onChange={(e) => updateConfig('threads', parseInt(e.target.value))}
                margin="normal"
              />
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfigDialog(false)}>Cancel</Button>
          <Button onClick={saveConfig} variant="contained" disabled={loading}>
            {loading ? 'Saving...' : 'Save'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Proxy Dialog */}
      <Dialog open={proxyDialog} onClose={() => setProxyDialog(false)} maxWidth="md" fullWidth>
        <DialogTitle>Proxy Configuration</DialogTitle>
        <DialogContent>
          <Typography variant="body2" gutterBottom>
            Enter one proxy per line in format: ip:port or user:pass@ip:port
          </Typography>
          <TextareaAutosize
            minRows={10}
            maxRows={20}
            style={{ width: '100%', marginTop: '10px' }}
            value={proxies}
            onChange={(e) => setProxies(e.target.value)}
            placeholder="127.0.0.1:8080&#10;user:pass@127.0.0.1:8080"
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setProxyDialog(false)}>Cancel</Button>
          <Button onClick={saveProxies} variant="contained" disabled={loading}>
            {loading ? 'Saving...' : 'Save'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Logs Dialog */}
      <Dialog open={logsDialog} onClose={() => setLogsDialog(false)} maxWidth="lg" fullWidth>
        <DialogTitle>Automation Logs</DialogTitle>
        <DialogContent>
          <TextField
            multiline
            rows={20}
            value={logs}
            InputProps={{
              readOnly: true,
              style: { fontFamily: 'monospace', fontSize: '12px' }
            }}
            fullWidth
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setLogsDialog(false)}>Close</Button>
          <Button onClick={fetchLogs} variant="contained">
            Refresh
          </Button>
        </DialogActions>
      </Dialog>

      {/* Alert Snackbar */}
      <Snackbar
        open={alert.show}
        autoHideDuration={4000}
        onClose={() => setAlert({ ...alert, show: false })}
      >
        <Alert
          onClose={() => setAlert({ ...alert, show: false })}
          severity={alert.severity}
          sx={{ width: '100%' }}
        >
          {alert.message}
        </Alert>
      </Snackbar>
    </div>
  );
}

export default App;