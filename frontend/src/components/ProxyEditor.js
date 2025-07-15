
import React, { useState, useEffect } from 'react';
import { toast } from 'react-toastify';

const ProxyEditor = ({ getAuthHeaders }) => {
  const [proxies, setProxies] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const fetchProxies = async () => {
    try {
      const response = await fetch('/api/proxy', {
        headers: getAuthHeaders()
      });

      if (response.ok) {
        const data = await response.json();
        setProxies(data.proxies);
      } else {
        toast.error('Failed to fetch proxy list');
      }
    } catch (error) {
      toast.error('Failed to fetch proxy list');
    } finally {
      setLoading(false);
    }
  };

  const saveProxies = async () => {
    setSaving(true);
    try {
      const response = await fetch('/api/proxy', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeaders()
        },
        body: JSON.stringify({ proxies })
      });

      if (response.ok) {
        toast.success('Proxy list saved successfully');
      } else {
        const error = await response.json();
        toast.error(error.detail || 'Failed to save proxy list');
      }
    } catch (error) {
      toast.error('Failed to save proxy list');
    } finally {
      setSaving(false);
    }
  };

  const clearProxies = () => {
    setProxies('');
  };

  const getProxyCount = () => {
    return proxies.split('\n').filter(line => line.trim()).length;
  };

  useEffect(() => {
    fetchProxies();
  }, []);

  if (loading) {
    return <div>Loading proxy list...</div>;
  }

  return (
    <div>
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3>Proxy List Management</h3>
          <div style={{ display: 'flex', gap: '10px' }}>
            <button
              className="btn btn-warning"
              onClick={clearProxies}
            >
              Clear All
            </button>
            <button
              className="btn btn-success"
              onClick={saveProxies}
              disabled={saving}
            >
              {saving ? 'Saving...' : 'Save Proxies'}
            </button>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="config-section">
          <h4>Proxy Configuration</h4>
          <p style={{ color: '#a0aec0', marginBottom: '15px' }}>
            Enter one proxy per line. Supported formats:
          </p>
          <ul style={{ color: '#e2e8f0', marginBottom: '20px', paddingLeft: '20px' }}>
            <li>IP:Port (e.g., 192.168.1.1:8080)</li>
            <li>Username:Password@IP:Port (e.g., user:pass@192.168.1.1:8080)</li>
          </ul>
          
          <div style={{ marginBottom: '15px' }}>
            <span style={{ color: '#48bb78', fontWeight: 'bold' }}>
              Total Proxies: {getProxyCount()}
            </span>
          </div>

          <textarea
            className="textarea"
            value={proxies}
            onChange={(e) => setProxies(e.target.value)}
            placeholder="Enter proxies, one per line..."
            rows="15"
            style={{
              fontFamily: 'monospace',
              fontSize: '14px',
              lineHeight: '1.5'
            }}
          />
        </div>
      </div>

      <div className="card">
        <div className="config-section">
          <h4>Proxy Testing</h4>
          <p style={{ color: '#a0aec0', marginBottom: '15px' }}>
            Testing functionality will be available in a future update.
          </p>
          <div className="button-group">
            <button className="btn btn-primary" disabled>
              Test All Proxies
            </button>
            <button className="btn btn-primary" disabled>
              Test Random Sample
            </button>
            <button className="btn btn-primary" disabled>
              Remove Dead Proxies
            </button>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="config-section">
          <h4>Import/Export</h4>
          <div className="button-group">
            <button className="btn btn-primary" disabled>
              Import from File
            </button>
            <button className="btn btn-primary" disabled>
              Export to File
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ProxyEditor;
