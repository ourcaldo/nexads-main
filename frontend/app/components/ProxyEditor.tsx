'use client'

import { useState, useEffect } from 'react'
import { Save, RefreshCw, Upload } from 'lucide-react'
import toast from 'react-hot-toast'
import api from '../utils/api'

export default function ProxyEditor() {
  const [proxies, setProxies] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [isSaving, setIsSaving] = useState(false)

  useEffect(() => {
    fetchProxies()
  }, [])

  const fetchProxies = async () => {
    setIsLoading(true)
    try {
      const response = await api.get('/proxies')
      setProxies(response.data.proxies)
    } catch (error: any) {
      toast.error('Failed to load proxies')
    } finally {
      setIsLoading(false)
    }
  }

  const saveProxies = async () => {
    setIsSaving(true)
    try {
      await api.post('/proxies', { proxies })
      toast.success('Proxies saved successfully!')
    } catch (error: any) {
      toast.error('Failed to save proxies')
    } finally {
      setIsSaving(false)
    }
  }

  const handleFileUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (file) {
      const reader = new FileReader()
      reader.onload = (e) => {
        const content = e.target?.result as string
        setProxies(content)
      }
      reader.readAsText(file)
    }
  }

  const getProxyCount = () => {
    return proxies.split('\n').filter(line => line.trim()).length
  }

  const validateProxies = () => {
    const lines = proxies.split('\n').filter(line => line.trim())
    const validFormats = [
      /^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d+$/,  // IP:Port
      /^.+:.+@\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d+$/,  // User:Pass@IP:Port
      /^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d+@.+:.+$/,  // IP:Port@User:Pass
    ]
    
    const invalid = lines.filter(line => 
      !validFormats.some(format => format.test(line.trim()))
    )
    
    return {
      total: lines.length,
      valid: lines.length - invalid.length,
      invalid: invalid.length,
      invalidLines: invalid
    }
  }

  const validation = validateProxies()

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-500"></div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold text-gray-100">Proxy Management</h2>
        <div className="flex space-x-3">
          <label className="btn-secondary flex items-center space-x-2 cursor-pointer">
            <Upload className="h-4 w-4" />
            <span>Upload File</span>
            <input
              type="file"
              accept=".txt"
              onChange={handleFileUpload}
              className="hidden"
            />
          </label>
          <button
            onClick={fetchProxies}
            disabled={isLoading}
            className="btn-secondary flex items-center space-x-2"
          >
            <RefreshCw className="h-4 w-4" />
            <span>Refresh</span>
          </button>
          <button
            onClick={saveProxies}
            disabled={isSaving}
            className="btn-primary flex items-center space-x-2"
          >
            <Save className="h-4 w-4" />
            <span>{isSaving ? 'Saving...' : 'Save'}</span>
          </button>
        </div>
      </div>

      {/* Proxy Statistics */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="card">
          <div className="text-center">
            <div className="text-2xl font-bold text-primary-400">{validation.total}</div>
            <div className="text-sm text-gray-400">Total Proxies</div>
          </div>
        </div>
        <div className="card">
          <div className="text-center">
            <div className="text-2xl font-bold text-green-400">{validation.valid}</div>
            <div className="text-sm text-gray-400">Valid Proxies</div>
          </div>
        </div>
        <div className="card">
          <div className="text-center">
            <div className="text-2xl font-bold text-red-400">{validation.invalid}</div>
            <div className="text-sm text-gray-400">Invalid Proxies</div>
          </div>
        </div>
      </div>

      {/* Proxy Editor */}
      <div className="card">
        <div className="mb-4">
          <h3 className="text-lg font-semibold text-gray-100 mb-2">Proxy List</h3>
          <p className="text-sm text-gray-400">
            Enter one proxy per line. Supported formats:
          </p>
          <ul className="text-sm text-gray-400 mt-2 space-y-1">
            <li>• <code className="bg-gray-700 px-1 rounded">IP:Port</code></li>
            <li>• <code className="bg-gray-700 px-1 rounded">User:Pass@IP:Port</code></li>
            <li>• <code className="bg-gray-700 px-1 rounded">IP:Port@User:Pass</code></li>
          </ul>
        </div>
        
        <textarea
          value={proxies}
          onChange={(e) => setProxies(e.target.value)}
          className="input-field w-full h-96 font-mono text-sm"
          placeholder="Enter proxies here, one per line..."
        />
        
        {validation.invalid > 0 && (
          <div className="mt-4 p-4 bg-red-900/20 border border-red-700 rounded-lg">
            <h4 className="text-red-400 font-medium mb-2">Invalid Proxy Formats:</h4>
            <div className="text-sm text-red-300 space-y-1 max-h-32 overflow-y-auto">
              {validation.invalidLines.map((line, index) => (
                <div key={index} className="font-mono">{line}</div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Usage Instructions */}
      <div className="card">
        <h3 className="text-lg font-semibold text-gray-100 mb-4">Usage Instructions</h3>
        <div className="space-y-2 text-sm text-gray-300">
          <p>• Proxies will be automatically distributed among threads</p>
          <p>• If you have more proxies than threads, proxies will be randomly selected</p>
          <p>• Each thread will use a different proxy to avoid conflicts</p>
          <p>• Invalid proxies will be skipped during execution</p>
          <p>• Leave empty to run without proxies</p>
        </div>
      </div>
    </div>
  )
}