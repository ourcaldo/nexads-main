'use client'

import { useState, useEffect } from 'react'
import { Save, RefreshCw } from 'lucide-react'
import toast from 'react-hot-toast'
import api from '../utils/api'

export default function ConfigEditor() {
  const [config, setConfig] = useState<any>({})
  const [isLoading, setIsLoading] = useState(false)
  const [isSaving, setIsSaving] = useState(false)

  useEffect(() => {
    fetchConfig()
  }, [])

  const fetchConfig = async () => {
    setIsLoading(true)
    try {
      const response = await api.get('/config')
      setConfig(response.data)
    } catch (error: any) {
      toast.error('Failed to load configuration')
    } finally {
      setIsLoading(false)
    }
  }

  const saveConfig = async () => {
    setIsSaving(true)
    try {
      await api.post('/config', { config })
      toast.success('Configuration saved successfully!')
    } catch (error: any) {
      toast.error('Failed to save configuration')
    } finally {
      setIsSaving(false)
    }
  }

  const updateConfig = (path: string, value: any) => {
    const keys = path.split('.')
    const newConfig = { ...config }
    let current = newConfig
    
    for (let i = 0; i < keys.length - 1; i++) {
      current = current[keys[i]]
    }
    
    current[keys[keys.length - 1]] = value
    setConfig(newConfig)
  }

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
        <h2 className="text-2xl font-bold text-gray-100">Configuration</h2>
        <div className="flex space-x-3">
          <button
            onClick={fetchConfig}
            disabled={isLoading}
            className="btn-secondary flex items-center space-x-2"
          >
            <RefreshCw className="h-4 w-4" />
            <span>Refresh</span>
          </button>
          <button
            onClick={saveConfig}
            disabled={isSaving}
            className="btn-primary flex items-center space-x-2"
          >
            <Save className="h-4 w-4" />
            <span>{isSaving ? 'Saving...' : 'Save'}</span>
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Proxy Configuration */}
        <div className="card">
          <h3 className="text-lg font-semibold text-gray-100 mb-4">Proxy Configuration</h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">Proxy Type</label>
              <select
                value={config.proxy?.type || 'http'}
                onChange={(e) => updateConfig('proxy.type', e.target.value)}
                className="input-field w-full"
              >
                <option value="http">HTTP</option>
                <option value="https">HTTPS</option>
                <option value="socks4">SOCKS4</option>
                <option value="socks5">SOCKS5</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">Proxy Credentials</label>
              <input
                type="text"
                value={config.proxy?.credentials || ''}
                onChange={(e) => updateConfig('proxy.credentials', e.target.value)}
                placeholder="IP:Port or User:Pass@IP:Port"
                className="input-field w-full"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">Proxy File</label>
              <input
                type="text"
                value={config.proxy?.file || ''}
                onChange={(e) => updateConfig('proxy.file', e.target.value)}
                placeholder="proxy.txt"
                className="input-field w-full"
              />
            </div>
          </div>
        </div>

        {/* Browser Configuration */}
        <div className="card">
          <h3 className="text-lg font-semibold text-gray-100 mb-4">Browser Configuration</h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">Headless Mode</label>
              <select
                value={config.browser?.headless_mode || 'True'}
                onChange={(e) => updateConfig('browser.headless_mode', e.target.value)}
                className="input-field w-full"
              >
                <option value="False">Off (Visible)</option>
                <option value="True">Headless Mode</option>
                <option value="virtual">Virtual Mode</option>
              </select>
            </div>
            <div className="flex items-center space-x-4">
              <label className="flex items-center">
                <input
                  type="checkbox"
                  checked={config.browser?.disable_ublock || false}
                  onChange={(e) => updateConfig('browser.disable_ublock', e.target.checked)}
                  className="mr-2"
                />
                <span className="text-sm text-gray-300">Disable uBlock</span>
              </label>
              <label className="flex items-center">
                <input
                  type="checkbox"
                  checked={config.browser?.random_activity || false}
                  onChange={(e) => updateConfig('browser.random_activity', e.target.checked)}
                  className="mr-2"
                />
                <span className="text-sm text-gray-300">Random Activity</span>
              </label>
            </div>
            <div className="flex items-center space-x-4">
              <label className="flex items-center">
                <input
                  type="checkbox"
                  checked={config.browser?.auto_accept_cookies || false}
                  onChange={(e) => updateConfig('browser.auto_accept_cookies', e.target.checked)}
                  className="mr-2"
                />
                <span className="text-sm text-gray-300">Auto Accept Cookies</span>
              </label>
              <label className="flex items-center">
                <input
                  type="checkbox"
                  checked={config.browser?.prevent_redirects || false}
                  onChange={(e) => updateConfig('browser.prevent_redirects', e.target.checked)}
                  className="mr-2"
                />
                <span className="text-sm text-gray-300">Prevent Redirects</span>
              </label>
            </div>
          </div>
        </div>

        {/* Delay Settings */}
        <div className="card">
          <h3 className="text-lg font-semibold text-gray-100 mb-4">Delay Settings</h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">Min Time (seconds)</label>
              <input
                type="number"
                value={config.delay?.min_time || 3}
                onChange={(e) => updateConfig('delay.min_time', parseInt(e.target.value))}
                className="input-field w-full"
                min="1"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">Max Time (seconds)</label>
              <input
                type="number"
                value={config.delay?.max_time || 10}
                onChange={(e) => updateConfig('delay.max_time', parseInt(e.target.value))}
                className="input-field w-full"
                min="1"
              />
            </div>
          </div>
        </div>

        {/* Session Settings */}
        <div className="card">
          <h3 className="text-lg font-semibold text-gray-100 mb-4">Session Settings</h3>
          <div className="space-y-4">
            <div className="flex items-center">
              <input
                type="checkbox"
                checked={config.session?.enabled || false}
                onChange={(e) => updateConfig('session.enabled', e.target.checked)}
                className="mr-2"
              />
              <span className="text-sm text-gray-300">Enable Session Limit</span>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">Session Count (0=unlimited)</label>
              <input
                type="number"
                value={config.session?.count || 0}
                onChange={(e) => updateConfig('session.count', parseInt(e.target.value))}
                className="input-field w-full"
                min="0"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">Max Session Time (minutes)</label>
              <input
                type="number"
                value={config.session?.max_time || 100}
                onChange={(e) => updateConfig('session.max_time', parseInt(e.target.value))}
                className="input-field w-full"
                min="1"
              />
            </div>
          </div>
        </div>

        {/* Thread Settings */}
        <div className="card">
          <h3 className="text-lg font-semibold text-gray-100 mb-4">Thread Settings</h3>
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Number of Threads</label>
            <input
              type="number"
              value={config.threads || 1}
              onChange={(e) => updateConfig('threads', parseInt(e.target.value))}
              className="input-field w-full"
              min="1"
              max="100"
            />
          </div>
        </div>

        {/* Ads Settings */}
        <div className="card">
          <h3 className="text-lg font-semibold text-gray-100 mb-4">Ads Settings</h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">CTR (%)</label>
              <input
                type="number"
                step="0.1"
                value={config.ads?.ctr || 1.0}
                onChange={(e) => updateConfig('ads.ctr', parseFloat(e.target.value))}
                className="input-field w-full"
                min="0.1"
                max="100"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">Min Time (seconds)</label>
              <input
                type="number"
                value={config.ads?.min_time || 30}
                onChange={(e) => updateConfig('ads.min_time', parseInt(e.target.value))}
                className="input-field w-full"
                min="1"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">Max Time (seconds)</label>
              <input
                type="number"
                value={config.ads?.max_time || 60}
                onChange={(e) => updateConfig('ads.max_time', parseInt(e.target.value))}
                className="input-field w-full"
                min="1"
              />
            </div>
          </div>
        </div>
      </div>

      {/* URLs Section */}
      <div className="card">
        <h3 className="text-lg font-semibold text-gray-100 mb-4">URL Configuration</h3>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Referrer Types</label>
            <div className="flex flex-wrap gap-4">
              {['direct', 'social', 'organic', 'random'].map((type) => (
                <label key={type} className="flex items-center">
                  <input
                    type="checkbox"
                    checked={config.referrer?.types?.includes(type) || false}
                    onChange={(e) => {
                      const types = config.referrer?.types || []
                      if (e.target.checked) {
                        updateConfig('referrer.types', [...types, type])
                      } else {
                        updateConfig('referrer.types', types.filter((t: string) => t !== type))
                      }
                    }}
                    className="mr-2"
                  />
                  <span className="text-sm text-gray-300 capitalize">{type}</span>
                </label>
              ))}
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Organic Keywords (one per line)</label>
            <textarea
              value={config.referrer?.organic_keywords || ''}
              onChange={(e) => updateConfig('referrer.organic_keywords', e.target.value)}
              className="input-field w-full h-24"
              placeholder="Enter keywords, one per line"
            />
          </div>
        </div>
      </div>
    </div>
  )
}