
import React, { useState } from 'react';
import { toast } from 'react-toastify';

const AutomationControl = ({ status, onStatusChange, getAuthHeaders }) => {
  const [loading, setLoading] = useState(false);

  const handleAction = async (action) => {
    setLoading(true);
    try {
      const response = await fetch(`/api/automation/${action}`, {
        method: 'POST',
        headers: getAuthHeaders()
      });

      if (response.ok) {
        const data = await response.json();
        toast.success(data.message);
        setTimeout(onStatusChange, 1000); // Refresh status after 1 second
      } else {
        const error = await response.json();
        toast.error(error.detail || `Failed to ${action} automation`);
      }
    } catch (error) {
      toast.error(`Failed to ${action} automation`);
    } finally {
      setLoading(false);
    }
  };

  const getStatusInfo = () => {
    const info = {
      running: {
        color: '#48bb78',
        text: 'Running',
        description: 'Automation is currently active'
      },
      stopped: {
        color: '#f56565',
        text: 'Stopped',
        description: 'Automation is not running'
      },
      unknown: {
        color: '#ed8936',
        text: 'Unknown',
        description: 'Status cannot be determined'
      }
    };

    return info[status.status] || info.unknown;
  };

  const statusInfo = getStatusInfo();

  return (
    <div>
      <div className="card">
        <h3>Current Status</h3>
        <div style={{ marginBottom: '20px' }}>
          <div style={{ 
            display: 'flex', 
            alignItems: 'center', 
            gap: '10px',
            marginBottom: '10px'
          }}>
            <div style={{
              width: '12px',
              height: '12px',
              borderRadius: '50%',
              backgroundColor: statusInfo.color
            }}></div>
            <span style={{ fontSize: '18px', fontWeight: 'bold' }}>
              {statusInfo.text}
            </span>
          </div>
          <p style={{ color: '#a0aec0', marginBottom: '15px' }}>
            {statusInfo.description}
          </p>
          
          {status.pid && (
            <div style={{ fontSize: '14px', color: '#e2e8f0' }}>
              <p>Process ID: {status.pid}</p>
              {status.start_time && (
                <p>Started: {new Date(status.start_time).toLocaleString()}</p>
              )}
            </div>
          )}
        </div>

        <div className="button-group">
          <button
            className="btn btn-success"
            onClick={() => handleAction('start')}
            disabled={loading || status.status === 'running'}
          >
            {loading ? 'Starting...' : 'Start'}
          </button>
          
          <button
            className="btn btn-danger"
            onClick={() => handleAction('stop')}
            disabled={loading || status.status === 'stopped'}
          >
            {loading ? 'Stopping...' : 'Stop'}
          </button>
          
          <button
            className="btn btn-warning"
            onClick={() => handleAction('restart')}
            disabled={loading || status.status === 'stopped'}
          >
            {loading ? 'Restarting...' : 'Restart'}
          </button>
        </div>
      </div>

      <div className="card">
        <h3>Quick Actions</h3>
        <div className="button-group">
          <button
            className="btn btn-primary"
            onClick={onStatusChange}
            disabled={loading}
          >
            Refresh Status
          </button>
        </div>
      </div>

      <div className="card">
        <h3>System Information</h3>
        <div style={{ color: '#e2e8f0', lineHeight: '1.6' }}>
          <p><strong>Service Name:</strong> nexads-automation</p>
          <p><strong>Working Directory:</strong> /path/to/nexads-main/core</p>
          <p><strong>Management:</strong> systemd service</p>
          <p><strong>Auto-restart:</strong> Enabled</p>
        </div>
      </div>
    </div>
  );
};

export default AutomationControl;
