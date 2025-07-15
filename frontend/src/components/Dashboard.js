
import React, { useState, useEffect } from 'react';
import { toast } from 'react-toastify';
import AutomationControl from './AutomationControl';
import ConfigEditor from './ConfigEditor';
import ProxyEditor from './ProxyEditor';
import LogsViewer from './LogsViewer';

const Dashboard = ({ onLogout }) => {
  const [activeTab, setActiveTab] = useState('control');
  const [automationStatus, setAutomationStatus] = useState({
    status: 'unknown'
  });

  const getAuthHeaders = () => {
    const auth = localStorage.getItem('nexads_auth');
    return {
      'Authorization': `Basic ${auth}`
    };
  };

  const fetchStatus = async () => {
    try {
      const response = await fetch('/api/automation/status', {
        headers: getAuthHeaders()
      });

      if (response.ok) {
        const data = await response.json();
        setAutomationStatus(data);
      }
    } catch (error) {
      console.error('Failed to fetch status:', error);
    }
  };

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 5000);
    return () => clearInterval(interval);
  }, []);

  const getStatusBadge = () => {
    const statusClass = `status-badge status-${automationStatus.status}`;
    return (
      <span className={statusClass}>
        {automationStatus.status}
      </span>
    );
  };

  const renderContent = () => {
    switch (activeTab) {
      case 'control':
        return <AutomationControl 
          status={automationStatus} 
          onStatusChange={fetchStatus}
          getAuthHeaders={getAuthHeaders}
        />;
      case 'config':
        return <ConfigEditor getAuthHeaders={getAuthHeaders} />;
      case 'proxy':
        return <ProxyEditor getAuthHeaders={getAuthHeaders} />;
      case 'logs':
        return <LogsViewer getAuthHeaders={getAuthHeaders} />;
      default:
        return <AutomationControl 
          status={automationStatus} 
          onStatusChange={fetchStatus}
          getAuthHeaders={getAuthHeaders}
        />;
    }
  };

  return (
    <div className="dashboard">
      <div className="sidebar">
        <h1>nexAds Panel</h1>
        
        <ul className="nav-menu">
          <li>
            <button
              className={activeTab === 'control' ? 'active' : ''}
              onClick={() => setActiveTab('control')}
            >
              Automation Control
            </button>
          </li>
          <li>
            <button
              className={activeTab === 'config' ? 'active' : ''}
              onClick={() => setActiveTab('config')}
            >
              Configuration
            </button>
          </li>
          <li>
            <button
              className={activeTab === 'proxy' ? 'active' : ''}
              onClick={() => setActiveTab('proxy')}
            >
              Proxy Settings
            </button>
          </li>
          <li>
            <button
              className={activeTab === 'logs' ? 'active' : ''}
              onClick={() => setActiveTab('logs')}
            >
              View Logs
            </button>
          </li>
        </ul>

        <button className="logout-button" onClick={onLogout}>
          Logout
        </button>
      </div>

      <div className="main-content">
        <div className="content-header">
          <h2>
            {activeTab === 'control' && 'Automation Control'}
            {activeTab === 'config' && 'Configuration'}
            {activeTab === 'proxy' && 'Proxy Settings'}
            {activeTab === 'logs' && 'System Logs'}
          </h2>
          {getStatusBadge()}
        </div>

        {renderContent()}
      </div>
    </div>
  );
};

export default Dashboard;
