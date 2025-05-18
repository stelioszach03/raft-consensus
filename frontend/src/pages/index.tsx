import { useEffect, useState } from 'react'
import Head from 'next/head'
import Layout from '@/components/Layout'
import ClusterView from '@/components/ClusterView'
import LogView from '@/components/LogView'
import ControlPanel from '@/components/ControlPanel'
import { useTheme } from '@/context/ThemeContext'
import Dashboard from '@/components/Dashboard'
import NodePanel from '@/components/NodePanel'
import WebSocketManager from '@/utils/WebSocketManager'

export default function Home() {
  const { isDarkMode } = useTheme()
  const [activeTab, setActiveTab] = useState('dashboard')
  const [wsManager, setWsManager] = useState<WebSocketManager | null>(null)
  const [clusterState, setClusterState] = useState(null)
  const [logEntries, setLogEntries] = useState([])
  
  useEffect(() => {
    console.log('Initializing WebSocket connection')
    // Initialize WebSocket connection - use port 8100 instead of 8000
    const manager = new WebSocketManager('ws://localhost:8100/ws')
    
    manager.onMessage((message) => {
      console.log('Received message:', message)
      if (message.type === 'state') {
        setClusterState(message.data)
      } else if (message.type === 'log') {
        setLogEntries(message.data.entries)
      }
    })
    
    setWsManager(manager)
    
    return () => {
      manager.disconnect()
    }
  }, [])

  return (
    <>
      <Head>
        <title>Raft Consensus Visualization</title>
        <meta name="description" content="Interactive visualization of the Raft consensus algorithm" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <link rel="icon" href="/favicon.ico" />
      </Head>
      <Layout>
        <div className="flex flex-col h-full">
          <nav className="flex border-b border-gray-200 dark:border-gray-700">
            <button
              className={`px-4 py-2 font-medium ${
                activeTab === 'dashboard'
                  ? 'text-primary-600 border-b-2 border-primary-500 dark:text-primary-400'
                  : 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300'
              }`}
              onClick={() => setActiveTab('dashboard')}
            >
              Dashboard
            </button>
            <button
              className={`px-4 py-2 font-medium ${
                activeTab === 'cluster'
                  ? 'text-primary-600 border-b-2 border-primary-500 dark:text-primary-400'
                  : 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300'
              }`}
              onClick={() => setActiveTab('cluster')}
            >
              Cluster
            </button>
            <button
              className={`px-4 py-2 font-medium ${
                activeTab === 'logs'
                  ? 'text-primary-600 border-b-2 border-primary-500 dark:text-primary-400'
                  : 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300'
              }`}
              onClick={() => setActiveTab('logs')}
            >
              Logs
            </button>
            <button
              className={`px-4 py-2 font-medium ${
                activeTab === 'control'
                  ? 'text-primary-600 border-b-2 border-primary-500 dark:text-primary-400'
                  : 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300'
              }`}
              onClick={() => setActiveTab('control')}
            >
              Control
            </button>
          </nav>
          
          <div className="flex-1 p-4 overflow-auto">
            {activeTab === 'dashboard' && <Dashboard clusterState={clusterState} logEntries={logEntries} />}
            {activeTab === 'cluster' && <ClusterView clusterState={clusterState} />}
            {activeTab === 'logs' && <LogView entries={logEntries} />}
            {activeTab === 'control' && <ControlPanel />}
          </div>
          
          {clusterState && (
            <div className="border-t border-gray-200 dark:border-gray-700 p-4">
              <NodePanel node={clusterState} />
            </div>
          )}
        </div>
      </Layout>
    </>
  )
}