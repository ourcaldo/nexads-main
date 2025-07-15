
import React, { useState, useEffect } from 'react';
import { toast } from 'react-toastify';

const LogsViewer = ({ getAuthHeaders }) => {
  const [logs, setLogs] = useState('');
  const [loading, setLoading] = useState(true);
  const [autoRefresh, setAutoRefresh] = useState(false);

  const fetchLogs = async () => {
    try {
      const response = await fetch('/api/logs', {
        headers: getAuthHeaders()
      });

      if (response.ok) {
        const data = await response.json();
        setLogs(data.logs);
      } else {
        toast.error('Failed to fetch logs');
      }
    } catch (error) {
      toast.error('Failed to fetch logs');
    } finally {
      setLoading(false);
    }
  };

  const clearLogs = () => {
    setLogs('');
  };

  const downloadLogs = () => {
    const element = document.createElement('a');
    const file = new Blob([logs], { type: 'text/plain' });
    element.href = URL.createObjectURL(file);
    element.download = `nexads-logs-${new Date().toISOString().split('T')[0]}.txt`;
    document.body.appendChild(element);
    element.click();
    document.body.removeChild(element);
  };

  useEffect(() => {
    fetchLogs();
  }, []);

  useEffect(() => {
    let interval;
    if (autoRefresh) {
      interval = setInterval(fetchLogs, 5000);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [autoRefresh]);

  if (loading) {
    return <div>Loading logs...</div>;
  }

  return (
    <div>
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3>System Logs</h3>
          <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
              <input
                type="checkbox"
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
              />
              Auto Refresh
            </label>
            <button
              className="btn btn-primary"
              onClick={fetchLogs}
            >
              Refresh
            </button>
            <button
              className="btn btn-primary"
              onClick={downloadLogs}
              disabled={!logs}
            >
              Download
            </button>
            <button
              className="btn btn-warning"
              onClick={clearLogs}
            >
              Clear View
            </button>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="config-section">
          <h4>Recent Logs (Last 100 entries)</h4>
          {autoRefresh && (
            <p style={{ color: '#48bb78', marginBottom: '15px' }}>
              Auto-refresh enabled (updates every 5 seconds)
            </p>
          )}
          
          <div className="logs-container">
            {logs || 'No logs available'}
          </div>
        </div>
      </div>

      <div className="card">
        <div className="config-section">
          <h4>Log Information</h4>
          <div style={{ color: '#e2e8f0', lineHeight: '1.6' }}>
            <p><strong>Service:</strong> nexads-automation</p>
            <p><strong>Log Source:</strong> systemd journal</p>
            <p><strong>Update Frequency:</strong> {autoRefresh ? 'Every 5 seconds' : 'Manual'}</p>
            <p><strong>Log Level:</strong> All levels</p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default LogsViewer;
