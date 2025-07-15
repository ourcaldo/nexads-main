'use client'

import { useState, useEffect } from 'react'
import { RefreshCw, Download, Trash2 } from 'lucide-react'
import toast from 'react-hot-toast'
import api from '../utils/api'

export default function LogViewer() {
  const [logs, setLogs] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [autoRefresh, setAutoRefresh] = useState(false)
  const [lines, setLines] = useState(100)

  useEffect(() => {
    fetchLogs()
  }, [lines])

  useEffect(() => {
    let interval: NodeJS.Timeout
    if (autoRefresh) {
      interval = setInterval(fetchLogs, 5000) // Refresh every 5 seconds
    }
    return () => {
      if (interval) clearInterval(interval)
    }
  }, [autoRefresh, lines])

  const fetchLogs = async () => {
    setIsLoading(true)
    try {
      const response = await api.get(`/logs?lines=${lines}`)
      setLogs(response.data.logs)
    } catch (error: any) {
      toast.error('Failed to load logs')
    } finally {
      setIsLoading(false)
    }
  }

  const downloadLogs = () => {
    const blob = new Blob([logs], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `nexads-logs-${new Date().toISOString().split('T')[0]}.txt`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  const clearLogs = async () => {
    if (confirm('Are you sure you want to clear the logs? This action cannot be undone.')) {
      try {
        // This would require implementing a clear logs endpoint
        toast.info('Clear logs functionality would be implemented here')
      } catch (error: any) {
        toast.error('Failed to clear logs')
      }
    }
  }

  const formatLogLine = (line: string) => {
    // Basic log formatting - you can enhance this based on your log format
    if (line.includes('ERROR') || line.includes('error')) {
      return 'text-red-400'
    } else if (line.includes('WARNING') || line.includes('warning')) {
      return 'text-yellow-400'
    } else if (line.includes('INFO') || line.includes('info')) {
      return 'text-blue-400'
    } else if (line.includes('SUCCESS') || line.includes('success')) {
      return 'text-green-400'
    }
    return 'text-gray-300'
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold text-gray-100">System Logs</h2>
        <div className="flex items-center space-x-3">
          <div className="flex items-center space-x-2">
            <label className="text-sm text-gray-300">Lines:</label>
            <select
              value={lines}
              onChange={(e) => setLines(parseInt(e.target.value))}
              className="input-field text-sm"
            >
              <option value={50}>50</option>
              <option value={100}>100</option>
              <option value={200}>200</option>
              <option value={500}>500</option>
              <option value={1000}>1000</option>
            </select>
          </div>
          
          <label className="flex items-center space-x-2">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="rounded"
            />
            <span className="text-sm text-gray-300">Auto Refresh</span>
          </label>
          
          <button
            onClick={downloadLogs}
            className="btn-secondary flex items-center space-x-2"
          >
            <Download className="h-4 w-4" />
            <span>Download</span>
          </button>
          
          <button
            onClick={fetchLogs}
            disabled={isLoading}
            className="btn-secondary flex items-center space-x-2"
          >
            <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Log Display */}
      <div className="card">
        <div className="bg-gray-900 rounded-lg p-4 h-96 overflow-y-auto font-mono text-sm">
          {isLoading && !logs ? (
            <div className="flex items-center justify-center h-full">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-500"></div>
            </div>
          ) : logs ? (
            <pre className="whitespace-pre-wrap">
              {logs.split('\n').map((line, index) => (
                <div key={index} className={formatLogLine(line)}>
                  {line}
                </div>
              ))}
            </pre>
          ) : (
            <div className="text-gray-500 text-center">
              No logs available. Start the automation to see logs here.
            </div>
          )}
        </div>
      </div>

      {/* Log Statistics */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="card">
          <div className="text-center">
            <div className="text-lg font-bold text-gray-100">
              {logs.split('\n').filter(line => line.includes('ERROR')).length}
            </div>
            <div className="text-sm text-red-400">Errors</div>
          </div>
        </div>
        <div className="card">
          <div className="text-center">
            <div className="text-lg font-bold text-gray-100">
              {logs.split('\n').filter(line => line.includes('WARNING')).length}
            </div>
            <div className="text-sm text-yellow-400">Warnings</div>
          </div>
        </div>
        <div className="card">
          <div className="text-center">
            <div className="text-lg font-bold text-gray-100">
              {logs.split('\n').filter(line => line.includes('INFO')).length}
            </div>
            <div className="text-sm text-blue-400">Info</div>
          </div>
        </div>
        <div className="card">
          <div className="text-center">
            <div className="text-lg font-bold text-gray-100">
              {logs.split('\n').filter(line => line.trim()).length}
            </div>
            <div className="text-sm text-gray-400">Total Lines</div>
          </div>
        </div>
      </div>

      {/* Log Controls */}
      <div className="card">
        <h3 className="text-lg font-semibold text-gray-100 mb-4">Log Controls</h3>
        <div className="space-y-2 text-sm text-gray-300">
          <p>• Logs are automatically updated when auto-refresh is enabled</p>
          <p>• Use the download button to save logs to your computer</p>
          <p>• Adjust the number of lines to view more or fewer log entries</p>
          <p>• Logs are color-coded: <span className="text-red-400">Errors</span>, <span className="text-yellow-400">Warnings</span>, <span className="text-blue-400">Info</span></p>
        </div>
      </div>
    </div>
  )
}