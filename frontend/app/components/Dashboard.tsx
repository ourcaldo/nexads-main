'use client'

import { useState, useEffect } from 'react'
import { 
  Play, 
  Square, 
  Pause, 
  RotateCcw, 
  Settings, 
  Globe, 
  LogOut,
  Activity,
  Server,
  Clock,
  Cpu,
  HardDrive
} from 'lucide-react'
import toast from 'react-hot-toast'
import api from '../utils/api'
import ConfigEditor from './ConfigEditor'
import ProxyEditor from './ProxyEditor'
import LogViewer from './LogViewer'

interface DashboardProps {
  onLogout: () => void
}

interface Status {
  status: string
  pid?: number
  uptime?: string
  memory_usage?: number
  cpu_usage?: number
}

export default function Dashboard({ onLogout }: DashboardProps) {
  const [status, setStatus] = useState<Status>({ status: 'stopped' })
  const [activeTab, setActiveTab] = useState('dashboard')
  const [isLoading, setIsLoading] = useState(false)

  useEffect(() => {
    fetchStatus()
    const interval = setInterval(fetchStatus, 5000) // Update every 5 seconds
    return () => clearInterval(interval)
  }, [])

  const fetchStatus = async () => {
    try {
      const response = await api.get('/status')
      setStatus(response.data)
    } catch (error) {
      console.error('Failed to fetch status:', error)
    }
  }

  const handleAutomationControl = async (action: string) => {
    setIsLoading(true)
    try {
      const response = await api.post('/automation', { action })
      toast.success(response.data.message)
      await fetchStatus()
    } catch (error: any) {
      toast.error(error.response?.data?.detail || `Failed to ${action} automation`)
    } finally {
      setIsLoading(false)
    }
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'running':
        return 'status-running'
      case 'paused':
        return 'status-paused'
      case 'stopped':
      default:
        return 'status-stopped'
    }
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'running':
        return <Activity className="h-5 w-5" />
      case 'paused':
        return <Pause className="h-5 w-5" />
      case 'stopped':
      default:
        return <Square className="h-5 w-5" />
    }
  }

  const renderDashboard = () => (
    <div className="space-y-6">
      {/* Status Card */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold text-gray-100">Automation Status</h2>
          <div className={`flex items-center space-x-2 ${getStatusColor(status.status)}`}>
            {getStatusIcon(status.status)}
            <span className="font-medium capitalize">{status.status}</span>
          </div>
        </div>

        {status.status === 'running' && (
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-4">
            <div className="bg-gray-700 rounded-lg p-3">
              <div className="flex items-center space-x-2">
                <Server className="h-4 w-4 text-gray-400" />
                <span className="text-sm text-gray-400">PID</span>
              </div>
              <p className="text-lg font-semibold text-gray-100">{status.pid || 'N/A'}</p>
            </div>
            <div className="bg-gray-700 rounded-lg p-3">
              <div className="flex items-center space-x-2">
                <Clock className="h-4 w-4 text-gray-400" />
                <span className="text-sm text-gray-400">Uptime</span>
              </div>
              <p className="text-lg font-semibold text-gray-100">{status.uptime || 'N/A'}</p>
            </div>
            <div className="bg-gray-700 rounded-lg p-3">
              <div className="flex items-center space-x-2">
                <HardDrive className="h-4 w-4 text-gray-400" />
                <span className="text-sm text-gray-400">Memory</span>
              </div>
              <p className="text-lg font-semibold text-gray-100">
                {status.memory_usage ? `${status.memory_usage.toFixed(1)} MB` : 'N/A'}
              </p>
            </div>
            <div className="bg-gray-700 rounded-lg p-3">
              <div className="flex items-center space-x-2">
                <Cpu className="h-4 w-4 text-gray-400" />
                <span className="text-sm text-gray-400">CPU</span>
              </div>
              <p className="text-lg font-semibold text-gray-100">
                {status.cpu_usage ? `${status.cpu_usage.toFixed(1)}%` : 'N/A'}
              </p>
            </div>
          </div>
        )}

        <div className="flex space-x-3">
          <button
            onClick={() => handleAutomationControl('start')}
            disabled={isLoading || status.status === 'running'}
            className="btn-success disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2"
          >
            <Play className="h-4 w-4" />
            <span>Start</span>
          </button>
          
          <button
            onClick={() => handleAutomationControl('pause')}
            disabled={isLoading || status.status !== 'running'}
            className="btn-secondary disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2"
          >
            <Pause className="h-4 w-4" />
            <span>Pause</span>
          </button>
          
          <button
            onClick={() => handleAutomationControl('resume')}
            disabled={isLoading || status.status !== 'paused'}
            className="btn-primary disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2"
          >
            <RotateCcw className="h-4 w-4" />
            <span>Resume</span>
          </button>
          
          <button
            onClick={() => handleAutomationControl('stop')}
            disabled={isLoading || status.status === 'stopped'}
            className="btn-danger disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2"
          >
            <Square className="h-4 w-4" />
            <span>Stop</span>
          </button>
        </div>
      </div>

      {/* Quick Actions */}
      <div className="card">
        <h2 className="text-xl font-semibold text-gray-100 mb-4">Quick Actions</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <button
            onClick={() => setActiveTab('config')}
            className="btn-secondary flex items-center justify-center space-x-2 py-4"
          >
            <Settings className="h-5 w-5" />
            <span>Edit Configuration</span>
          </button>
          
          <button
            onClick={() => setActiveTab('proxies')}
            className="btn-secondary flex items-center justify-center space-x-2 py-4"
          >
            <Globe className="h-5 w-5" />
            <span>Manage Proxies</span>
          </button>
          
          <button
            onClick={() => setActiveTab('logs')}
            className="btn-secondary flex items-center justify-center space-x-2 py-4"
          >
            <Activity className="h-5 w-5" />
            <span>View Logs</span>
          </button>
        </div>
      </div>
    </div>
  )

  return (
    <div className="min-h-screen bg-gray-900">
      {/* Header */}
      <header className="bg-gray-800 border-b border-gray-700">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center py-4">
            <h1 className="text-2xl font-bold text-gray-100">nexAds Control Panel</h1>
            <button
              onClick={onLogout}
              className="btn-secondary flex items-center space-x-2"
            >
              <LogOut className="h-4 w-4" />
              <span>Logout</span>
            </button>
          </div>
        </div>
      </header>

      {/* Navigation */}
      <nav className="bg-gray-800 border-b border-gray-700">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex space-x-8">
            {[
              { id: 'dashboard', label: 'Dashboard', icon: Activity },
              { id: 'config', label: 'Configuration', icon: Settings },
              { id: 'proxies', label: 'Proxies', icon: Globe },
              { id: 'logs', label: 'Logs', icon: Server },
            ].map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                onClick={() => setActiveTab(id)}
                className={`flex items-center space-x-2 py-4 px-1 border-b-2 font-medium text-sm ${
                  activeTab === id
                    ? 'border-primary-500 text-primary-400'
                    : 'border-transparent text-gray-400 hover:text-gray-300 hover:border-gray-300'
                }`}
              >
                <Icon className="h-4 w-4" />
                <span>{label}</span>
              </button>
            ))}
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {activeTab === 'dashboard' && renderDashboard()}
        {activeTab === 'config' && <ConfigEditor />}
        {activeTab === 'proxies' && <ProxyEditor />}
        {activeTab === 'logs' && <LogViewer />}
      </main>
    </div>
  )
}