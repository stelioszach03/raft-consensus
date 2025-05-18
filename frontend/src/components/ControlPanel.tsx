import React, { useState } from 'react'
import { motion } from 'framer-motion'
import axios from 'axios'
import { Send, Plus, Trash, Key, RefreshCw, AlertTriangle } from 'lucide-react'

const ControlPanel: React.FC = () => {
  const [key, setKey] = useState('')
  const [value, setValue] = useState('')
  const [operation, setOperation] = useState('set')
  const [isLoading, setIsLoading] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)
  
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsLoading(true)
    setError(null)
    setResult(null)
    
    try {
      const command = {
        operation,
        key,
        ...(operation === 'set' && { value }),
      }
      
      const response = await axios.post('/api/command', command)
      setResult(response.data)
      
      // Reset form if successful
      if (response.data.success && operation === 'set') {
        setKey('')
        setValue('')
      }
    } catch (err) {
      console.error('Error executing command:', err)
      setError('Failed to execute command. Please try again.')
    } finally {
      setIsLoading(false)
    }
  }
  
  const operationOptions = [
    { value: 'set', label: 'Set Key', icon: <Plus className="h-4 w-4 mr-2" /> },
    { value: 'get', label: 'Get Key', icon: <Key className="h-4 w-4 mr-2" /> },
    { value: 'delete', label: 'Delete Key', icon: <Trash className="h-4 w-4 mr-2" /> },
  ]

  return (
    <div className="flex flex-col h-full">
      <h2 className="text-xl font-semibold mb-4">Control Panel</h2>
      
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="border dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 p-6 shadow-sm">
          <h3 className="text-lg font-medium mb-4">Execute Command</h3>
          
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                Operation
              </label>
              <div className="grid grid-cols-3 gap-2">
                {operationOptions.map(option => (
                  <button
                    key={option.value}
                    type="button"
                    className={`flex items-center justify-center px-4 py-2 text-sm font-medium rounded-md ${
                      operation === option.value
                        ? 'bg-primary-100 text-primary-700 border-primary-300 dark:bg-primary-800 dark:text-primary-200 dark:border-primary-700'
                        : 'border border-gray-300 text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-700'
                    }`}
                    onClick={() => setOperation(option.value)}
                  >
                    {option.icon}
                    {option.label}
                  </button>
                ))}
              </div>
            </div>
            
            <div className="space-y-2">
              <label htmlFor="key" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                Key
              </label>
              <input
                type="text"
                id="key"
                value={key}
                onChange={e => setKey(e.target.value)}
                className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                required
              />
            </div>
            
            {operation === 'set' && (
              <div className="space-y-2">
                <label htmlFor="value" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                  Value
                </label>
                <input
                  type="text"
                  id="value"
                  value={value}
                  onChange={e => setValue(e.target.value)}
                  className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                  required
                />
              </div>
            )}
            
            <button
              type="submit"
              className="flex items-center justify-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={isLoading}
            >
              {isLoading ? (
                <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Send className="h-4 w-4 mr-2" />
              )}
              Execute Command
            </button>
          </form>
          
          {error && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="mt-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-md"
            >
              <div className="flex">
                <AlertTriangle className="h-5 w-5 text-red-400 dark:text-red-500 mr-2" />
                <span className="text-sm text-red-700 dark:text-red-400">{error}</span>
              </div>
            </motion.div>
          )}
          
          {result && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              className="mt-4 p-3 bg-gray-50 dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-md"
            >
              <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Response:</h4>
              <pre className="text-xs overflow-auto p-2 bg-gray-100 dark:bg-gray-800 rounded">
                {JSON.stringify(result, null, 2)}
              </pre>
            </motion.div>
          )}
        </div>
        
        <div className="border dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 p-6 shadow-sm">
          <h3 className="text-lg font-medium mb-4">Simulations</h3>
          <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
            These actions simulate different scenarios in a Raft cluster. Note that these are UI-only
            demonstrations and don't affect the actual cluster state.
          </p>
          
          <div className="space-y-3">
            <button
              type="button"
              className="w-full flex items-center justify-center px-4 py-2 border border-gray-300 dark:border-gray-600 text-sm font-medium rounded-md text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500"
              onClick={() => alert('This is a UI simulation - in a real implementation, this would trigger a node failure.')}
            >
              Simulate Node Failure
            </button>
            
            <button
              type="button"
              className="w-full flex items-center justify-center px-4 py-2 border border-gray-300 dark:border-gray-600 text-sm font-medium rounded-md text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500"
              onClick={() => alert('This is a UI simulation - in a real implementation, this would trigger a network partition.')}
            >
              Simulate Network Partition
            </button>
            
            <button
              type="button"
              className="w-full flex items-center justify-center px-4 py-2 border border-gray-300 dark:border-gray-600 text-sm font-medium rounded-md text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500"
              onClick={() => alert('This is a UI simulation - in a real implementation, this would force an election timeout.')}
            >
              Force Election Timeout
            </button>
          </div>
          
          <div className="mt-6">
            <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Documentation</h4>
            <div className="p-3 bg-gray-50 dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-md text-sm">
              <p className="mb-2">
                <strong>Set Key</strong>: Add or update a key-value pair in the distributed state machine.
              </p>
              <p className="mb-2">
                <strong>Get Key</strong>: Retrieve the value associated with a key.
              </p>
              <p className="mb-2">
                <strong>Delete Key</strong>: Remove a key-value pair from the state machine.
              </p>
              <p>
                All operations are forwarded to the current leader. If this node is not the leader,
                the request will be redirected automatically.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default ControlPanel