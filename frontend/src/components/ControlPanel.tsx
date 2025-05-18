import React, { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import axios from 'axios'
import { Send, Plus, Trash, Key, RefreshCw, AlertTriangle, Clock } from 'lucide-react'

const ControlPanel: React.FC = () => {
  const [key, setKey] = useState('')
  const [value, setValue] = useState('')
  const [operation, setOperation] = useState('set')
  const [isLoading, setIsLoading] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)
  
  // Προσθήκα κατάστασης για τις προσομοιώσεις
  const [isSimulationRunning, setIsSimulationRunning] = useState(false)
  const [simulationMessage, setSimulationMessage] = useState<string | null>(null)
  const [simulationCountdown, setSimulationCountdown] = useState(0)
  
  // Το countdown για τις προσομοιώσεις
  useEffect(() => {
    if (simulationCountdown > 0) {
      const timer = setTimeout(() => {
        setSimulationCountdown(simulationCountdown - 1)
      }, 1000)
      return () => clearTimeout(timer)
    } else if (simulationCountdown === 0 && isSimulationRunning) {
      setIsSimulationRunning(false)
      setSimulationMessage(null)
    }
  }, [simulationCountdown, isSimulationRunning])
  
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
      
      // Προσθήκη retry λογικής
      let retries = 0
      const maxRetries = 3
      let success = false
      let response
      
      while (!success && retries < maxRetries) {
        try {
          response = await axios.post('/command', command)
          success = response.data.success
          
          if (!success && response.data.retry) {
            retries++
            await new Promise(resolve => setTimeout(resolve, 500))
          } else {
            break
          }
        } catch (err) {
          retries++
          await new Promise(resolve => setTimeout(resolve, 500))
        }
      }
      
      if (success && response) {
        setResult(response.data)
        
        // Reset form if successful
        if (operation === 'set') {
          setKey('')
          setValue('')
        }
      } else {
        setError(response?.data?.error || 'Failed to execute command after multiple attempts')
        setResult(response?.data)
      }
    } catch (err) {
      console.error('Error executing command:', err)
      setError('Failed to execute command. Please try again.')
    } finally {
      setIsLoading(false)
    }
  }
  
  // Νέες λειτουργίες για προσομοιώσεις με προστασία από ταυτόχρονη εκτέλεση
  const handleNodeFailure = async () => {
    if (isSimulationRunning) {
      alert('Simulation already in progress. Please wait.')
      return
    }

    try {
      setIsSimulationRunning(true)
      setSimulationMessage('Node failure simulation in progress...')
      setSimulationCountdown(10)  // 10 second countdown
      
      const response = await axios.post('/simulation/node-failure')
      if (response.data.success) {
        setSimulationMessage(response.data.message || 'Node failure simulated')
      } else {
        setSimulationMessage(response.data.message || 'Failed to simulate node failure')
        setSimulationCountdown(2) // Short countdown for failure
      }
    } catch (err) {
      console.error('Error simulating node failure:', err)
      setSimulationMessage('Failed to simulate node failure')
      setSimulationCountdown(2) // Short countdown for error
    }
  }
  
  const handleNetworkPartition = async () => {
    if (isSimulationRunning) {
      alert('Simulation already in progress. Please wait.')
      return
    }

    try {
      setIsSimulationRunning(true)
      setSimulationMessage('Network partition simulation in progress...')
      setSimulationCountdown(15)  // 15 second countdown
      
      const response = await axios.post('/simulation/network-partition')
      if (response.data.success) {
        setSimulationMessage(response.data.message || 'Network partition simulated')
      } else {
        setSimulationMessage(response.data.message || 'Failed to simulate network partition')
        setSimulationCountdown(2) // Short countdown for failure
      }
    } catch (err) {
      console.error('Error simulating network partition:', err)
      setSimulationMessage('Failed to simulate network partition')
      setSimulationCountdown(2) // Short countdown for error
    }
  }
  
  const handleForceElection = async () => {
    if (isSimulationRunning) {
      alert('Simulation already in progress. Please wait.')
      return
    }

    try {
      setIsSimulationRunning(true)
      setSimulationMessage('Forcing election timeout...')
      setSimulationCountdown(10)  // 10 second countdown
      
      const response = await axios.post('/simulation/force-election')
      if (response.data.success) {
        setSimulationMessage(response.data.message || 'Election timeout forced')
      } else {
        setSimulationMessage(response.data.message || 'Failed to force election timeout')
        setSimulationCountdown(2) // Short countdown for failure
      }
    } catch (err) {
      console.error('Error forcing election timeout:', err)
      setSimulationMessage('Failed to force election timeout')
      setSimulationCountdown(2) // Short countdown for error
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
              disabled={isLoading || isSimulationRunning}
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
            These actions simulate different scenarios in a Raft cluster. They will affect the actual cluster state.
          </p>
          
          {/* Μήνυμα κατάστασης προσομοίωσης */}
          <AnimatePresence>
            {isSimulationRunning && simulationMessage && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                className="mb-4 p-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-md"
              >
                <div className="flex items-center">
                  <Clock className="h-5 w-5 text-blue-400 dark:text-blue-500 mr-2" />
                  <div>
                    <span className="text-sm text-blue-700 dark:text-blue-400">{simulationMessage}</span>
                    {simulationCountdown > 0 && (
                      <div className="text-xs text-blue-500 dark:text-blue-300 mt-1">
                        Simulation will complete in {simulationCountdown} seconds
                      </div>
                    )}
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
          
          <div className="space-y-3">
            <button
              type="button"
              className={`w-full flex items-center justify-center px-4 py-2 border ${
                isSimulationRunning
                ? 'border-gray-200 dark:border-gray-800 text-gray-400 dark:text-gray-600 cursor-not-allowed'
                : 'border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
              } text-sm font-medium rounded-md focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500`}
              onClick={handleNodeFailure}
              disabled={isSimulationRunning}
            >
              Simulate Node Failure
            </button>
            
            <button
              type="button"
              className={`w-full flex items-center justify-center px-4 py-2 border ${
                isSimulationRunning
                ? 'border-gray-200 dark:border-gray-800 text-gray-400 dark:text-gray-600 cursor-not-allowed'
                : 'border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
              } text-sm font-medium rounded-md focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500`}
              onClick={handleNetworkPartition}
              disabled={isSimulationRunning}
            >
              Simulate Network Partition
            </button>
            
            <button
              type="button"
              className={`w-full flex items-center justify-center px-4 py-2 border ${
                isSimulationRunning
                ? 'border-gray-200 dark:border-gray-800 text-gray-400 dark:text-gray-600 cursor-not-allowed'
                : 'border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
              } text-sm font-medium rounded-md focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500`}
              onClick={handleForceElection}
              disabled={isSimulationRunning}
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