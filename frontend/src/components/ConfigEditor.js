
import React, { useState, useEffect } from 'react';
import { toast } from 'react-toastify';

const ConfigEditor = ({ getAuthHeaders }) => {
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [newUrl, setNewUrl] = useState({
    url: '',
    random_page: false,
    min_time: 30,
    max_time: 60
  });

  const fetchConfig = async () => {
    try {
      const response = await fetch('/api/config', {
        headers: getAuthHeaders()
      });

      if (response.ok) {
        const data = await response.json();
        setConfig(data.config);
      } else {
        toast.error('Failed to fetch configuration');
      }
    } catch (error) {
      toast.error('Failed to fetch configuration');
    } finally {
      setLoading(false);
    }
  };

  const saveConfig = async () => {
    setSaving(true);
    try {
      const response = await fetch('/api/config', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeaders()
        },
        body: JSON.stringify({ config })
      });

      if (response.ok) {
        toast.success('Configuration saved successfully');
      } else {
        const error = await response.json();
        toast.error(error.detail || 'Failed to save configuration');
      }
    } catch (error) {
      toast.error('Failed to save configuration');
    } finally {
      setSaving(false);
    }
  };

  const addUrl = () => {
    if (!newUrl.url.trim()) {
      toast.error('URL is required');
      return;
    }

    const updatedConfig = {
      ...config,
      urls: [...config.urls, { ...newUrl }]
    };

    setConfig(updatedConfig);
    setNewUrl({
      url: '',
      random_page: false,
      min_time: 30,
      max_time: 60
    });
  };

  const removeUrl = (index) => {
    const updatedConfig = {
      ...config,
      urls: config.urls.filter((_, i) => i !== index)
    };
    setConfig(updatedConfig);
  };

  const updateUrl = (index, field, value) => {
    const updatedConfig = {
      ...config,
      urls: config.urls.map((url, i) => 
        i === index ? { ...url, [field]: value } : url
      )
    };
    setConfig(updatedConfig);
  };

  const updateConfig = (section, field, value) => {
    setConfig({
      ...config,
      [section]: {
        ...config[section],
        [field]: value
      }
    });
  };

  const updateNestedConfig = (section, subsection, field, value) => {
    setConfig({
      ...config,
      [section]: {
        ...config[section],
        [subsection]: {
          ...config[section][subsection],
          [field]: value
        }
      }
    });
  };

  useEffect(() => {
    fetchConfig();
  }, []);

  if (loading) {
    return <div>Loading configuration...</div>;
  }

  if (!config) {
    return <div>Failed to load configuration</div>;
  }

  return (
    <div>
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3>Configuration Settings</h3>
          <button
            className="btn btn-success"
            onClick={saveConfig}
            disabled={saving}
          >
            {saving ? 'Saving...' : 'Save Configuration'}
          </button>
        </div>
      </div>

      {/* Proxy Settings */}
      <div className="card">
        <div className="config-section">
          <h4>Proxy Settings</h4>
          <div className="form-row">
            <div className="form-group">
              <label>Proxy Type</label>
              <select
                value={config.proxy.type}
                onChange={(e) => updateConfig('proxy', 'type', e.target.value)}
                style={{
                  width: '100%',
                  padding: '10px',
                  border: '1px solid #4a5568',
                  borderRadius: '5px',
                  background: '#1a202c',
                  color: '#ffffff'
                }}
              >
                <option value="http">HTTP</option>
                <option value="https">HTTPS</option>
                <option value="socks4">SOCKS4</option>
                <option value="socks5">SOCKS5</option>
              </select>
            </div>
            <div className="form-group">
              <label>Proxy Credentials</label>
              <input
                type="text"
                value={config.proxy.credentials}
                onChange={(e) => updateConfig('proxy', 'credentials', e.target.value)}
                placeholder="user:pass@ip:port or ip:port"
                style={{
                  width: '100%',
                  padding: '10px',
                  border: '1px solid #4a5568',
                  borderRadius: '5px',
                  background: '#1a202c',
                  color: '#ffffff'
                }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Browser Settings */}
      <div className="card">
        <div className="config-section">
          <h4>Browser Settings</h4>
          <div className="form-row">
            <div className="form-group">
              <label>Headless Mode</label>
              <select
                value={config.browser.headless_mode}
                onChange={(e) => updateConfig('browser', 'headless_mode', e.target.value)}
                style={{
                  width: '100%',
                  padding: '10px',
                  border: '1px solid #4a5568',
                  borderRadius: '5px',
                  background: '#1a202c',
                  color: '#ffffff'
                }}
              >
                <option value="True">Headless</option>
                <option value="False">Visible</option>
                <option value="virtual">Virtual</option>
              </select>
            </div>
            <div className="form-group">
              <label>Threads</label>
              <input
                type="number"
                min="1"
                max="100"
                value={config.threads}
                onChange={(e) => setConfig({...config, threads: parseInt(e.target.value)})}
                style={{
                  width: '100%',
                  padding: '10px',
                  border: '1px solid #4a5568',
                  borderRadius: '5px',
                  background: '#1a202c',
                  color: '#ffffff'
                }}
              />
            </div>
          </div>
          
          <div className="checkbox-group">
            <label>
              <input
                type="checkbox"
                checked={config.browser.disable_ublock}
                onChange={(e) => updateConfig('browser', 'disable_ublock', e.target.checked)}
              />
              Disable uBlock
            </label>
            <label>
              <input
                type="checkbox"
                checked={config.browser.random_activity}
                onChange={(e) => updateConfig('browser', 'random_activity', e.target.checked)}
              />
              Random Activity
            </label>
            <label>
              <input
                type="checkbox"
                checked={config.browser.auto_accept_cookies}
                onChange={(e) => updateConfig('browser', 'auto_accept_cookies', e.target.checked)}
              />
              Auto Accept Cookies
            </label>
            <label>
              <input
                type="checkbox"
                checked={config.browser.prevent_redirects}
                onChange={(e) => updateConfig('browser', 'prevent_redirects', e.target.checked)}
              />
              Prevent Redirects
            </label>
          </div>

          <div style={{ marginTop: '15px' }}>
            <label>Activities</label>
            <div className="checkbox-group">
              <label>
                <input
                  type="checkbox"
                  checked={config.browser.activities.includes('scroll')}
                  onChange={(e) => {
                    const activities = e.target.checked
                      ? [...config.browser.activities, 'scroll']
                      : config.browser.activities.filter(a => a !== 'scroll');
                    updateConfig('browser', 'activities', activities);
                  }}
                />
                Scroll
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={config.browser.activities.includes('hover')}
                  onChange={(e) => {
                    const activities = e.target.checked
                      ? [...config.browser.activities, 'hover']
                      : config.browser.activities.filter(a => a !== 'hover');
                    updateConfig('browser', 'activities', activities);
                  }}
                />
                Hover
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={config.browser.activities.includes('click')}
                  onChange={(e) => {
                    const activities = e.target.checked
                      ? [...config.browser.activities, 'click']
                      : config.browser.activities.filter(a => a !== 'click');
                    updateConfig('browser', 'activities', activities);
                  }}
                />
                Click
              </label>
            </div>
          </div>
        </div>
      </div>

      {/* Timing Settings */}
      <div className="card">
        <div className="config-section">
          <h4>Timing Settings</h4>
          <div className="form-row">
            <div className="form-group">
              <label>Min Delay (seconds)</label>
              <input
                type="number"
                min="1"
                value={config.delay.min_time}
                onChange={(e) => updateNestedConfig('delay', null, 'min_time', parseInt(e.target.value))}
                style={{
                  width: '100%',
                  padding: '10px',
                  border: '1px solid #4a5568',
                  borderRadius: '5px',
                  background: '#1a202c',
                  color: '#ffffff'
                }}
              />
            </div>
            <div className="form-group">
              <label>Max Delay (seconds)</label>
              <input
                type="number"
                min="1"
                value={config.delay.max_time}
                onChange={(e) => updateNestedConfig('delay', null, 'max_time', parseInt(e.target.value))}
                style={{
                  width: '100%',
                  padding: '10px',
                  border: '1px solid #4a5568',
                  borderRadius: '5px',
                  background: '#1a202c',
                  color: '#ffffff'
                }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Session Settings */}
      <div className="card">
        <div className="config-section">
          <h4>Session Settings</h4>
          <div className="checkbox-group">
            <label>
              <input
                type="checkbox"
                checked={config.session.enabled}
                onChange={(e) => updateConfig('session', 'enabled', e.target.checked)}
              />
              Enable Session Limit
            </label>
          </div>
          <div className="form-row">
            <div className="form-group">
              <label>Session Count (0 = unlimited)</label>
              <input
                type="number"
                min="0"
                value={config.session.count}
                onChange={(e) => updateConfig('session', 'count', parseInt(e.target.value))}
                style={{
                  width: '100%',
                  padding: '10px',
                  border: '1px solid #4a5568',
                  borderRadius: '5px',
                  background: '#1a202c',
                  color: '#ffffff'
                }}
              />
            </div>
            <div className="form-group">
              <label>Max Session Time (minutes)</label>
              <input
                type="number"
                min="1"
                value={config.session.max_time}
                onChange={(e) => updateConfig('session', 'max_time', parseInt(e.target.value))}
                style={{
                  width: '100%',
                  padding: '10px',
                  border: '1px solid #4a5568',
                  borderRadius: '5px',
                  background: '#1a202c',
                  color: '#ffffff'
                }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Ads Settings */}
      <div className="card">
        <div className="config-section">
          <h4>Ads Settings</h4>
          <div className="form-row">
            <div className="form-group">
              <label>CTR Percentage</label>
              <input
                type="number"
                min="0.1"
                max="100"
                step="0.1"
                value={config.ads.ctr}
                onChange={(e) => updateConfig('ads', 'ctr', parseFloat(e.target.value))}
                style={{
                  width: '100%',
                  padding: '10px',
                  border: '1px solid #4a5568',
                  borderRadius: '5px',
                  background: '#1a202c',
                  color: '#ffffff'
                }}
              />
            </div>
            <div className="form-group">
              <label>Ad Min Time (seconds)</label>
              <input
                type="number"
                min="1"
                value={config.ads.min_time}
                onChange={(e) => updateConfig('ads', 'min_time', parseInt(e.target.value))}
                style={{
                  width: '100%',
                  padding: '10px',
                  border: '1px solid #4a5568',
                  borderRadius: '5px',
                  background: '#1a202c',
                  color: '#ffffff'
                }}
              />
            </div>
            <div className="form-group">
              <label>Ad Max Time (seconds)</label>
              <input
                type="number"
                min="1"
                value={config.ads.max_time}
                onChange={(e) => updateConfig('ads', 'max_time', parseInt(e.target.value))}
                style={{
                  width: '100%',
                  padding: '10px',
                  border: '1px solid #4a5568',
                  borderRadius: '5px',
                  background: '#1a202c',
                  color: '#ffffff'
                }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Referrer Settings */}
      <div className="card">
        <div className="config-section">
          <h4>Referrer Settings</h4>
          <div className="checkbox-group">
            <label>
              <input
                type="checkbox"
                checked={config.referrer.types.includes('direct')}
                onChange={(e) => {
                  const types = e.target.checked
                    ? [...config.referrer.types, 'direct']
                    : config.referrer.types.filter(t => t !== 'direct');
                  updateConfig('referrer', 'types', types);
                }}
              />
              Direct
            </label>
            <label>
              <input
                type="checkbox"
                checked={config.referrer.types.includes('social')}
                onChange={(e) => {
                  const types = e.target.checked
                    ? [...config.referrer.types, 'social']
                    : config.referrer.types.filter(t => t !== 'social');
                  updateConfig('referrer', 'types', types);
                }}
              />
              Social
            </label>
            <label>
              <input
                type="checkbox"
                checked={config.referrer.types.includes('organic')}
                onChange={(e) => {
                  const types = e.target.checked
                    ? [...config.referrer.types, 'organic']
                    : config.referrer.types.filter(t => t !== 'organic');
                  updateConfig('referrer', 'types', types);
                }}
              />
              Organic
            </label>
            <label>
              <input
                type="checkbox"
                checked={config.referrer.types.includes('random')}
                onChange={(e) => {
                  const types = e.target.checked
                    ? ['random']
                    : config.referrer.types.filter(t => t !== 'random');
                  updateConfig('referrer', 'types', types);
                }}
              />
              Random
            </label>
          </div>
          
          <div className="form-group">
            <label>Organic Keywords (one per line)</label>
            <textarea
              className="textarea"
              value={config.referrer.organic_keywords}
              onChange={(e) => updateConfig('referrer', 'organic_keywords', e.target.value)}
              placeholder="Enter organic keywords, one per line"
              rows="5"
            />
          </div>
        </div>
      </div>

      {/* URL List */}
      <div className="card">
        <div className="config-section">
          <h4>URL List</h4>
          
          <div className="add-url-row">
            <input
              type="text"
              value={newUrl.url}
              onChange={(e) => setNewUrl({...newUrl, url: e.target.value})}
              placeholder="Enter URL"
            />
            <input
              type="number"
              value={newUrl.min_time}
              onChange={(e) => setNewUrl({...newUrl, min_time: parseInt(e.target.value)})}
              placeholder="Min Time"
              min="1"
            />
            <input
              type="number"
              value={newUrl.max_time}
              onChange={(e) => setNewUrl({...newUrl, max_time: parseInt(e.target.value)})}
              placeholder="Max Time"
              min="1"
            />
            <label style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
              <input
                type="checkbox"
                checked={newUrl.random_page}
                onChange={(e) => setNewUrl({...newUrl, random_page: e.target.checked})}
              />
              Random Page
            </label>
            <button className="btn btn-primary" onClick={addUrl}>
              Add URL
            </button>
          </div>

          <table className="url-table">
            <thead>
              <tr>
                <th>URL</th>
                <th>Random Page</th>
                <th>Min Time</th>
                <th>Max Time</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {config.urls.map((url, index) => (
                <tr key={index}>
                  <td>
                    <input
                      type="text"
                      value={url.url}
                      onChange={(e) => updateUrl(index, 'url', e.target.value)}
                    />
                  </td>
                  <td>
                    <input
                      type="checkbox"
                      checked={url.random_page}
                      onChange={(e) => updateUrl(index, 'random_page', e.target.checked)}
                    />
                  </td>
                  <td>
                    <input
                      type="number"
                      value={url.min_time}
                      onChange={(e) => updateUrl(index, 'min_time', parseInt(e.target.value))}
                      min="1"
                    />
                  </td>
                  <td>
                    <input
                      type="number"
                      value={url.max_time}
                      onChange={(e) => updateUrl(index, 'max_time', parseInt(e.target.value))}
                      min="1"
                    />
                  </td>
                  <td>
                    <button
                      className="btn btn-danger"
                      onClick={() => removeUrl(index)}
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default ConfigEditor;
