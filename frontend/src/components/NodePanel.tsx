import React from 'react'
import { Clock, Database, Server } from 'lucide-react'

interface NodePanelProps {
  node: any
}

const NodePanel: React.FC<NodePanelProps> = ({ node }) => {
  if (!node) return null
  
  // Map state to color
  const getStateColor = (state: string) => {
    switch (state) {
      case 'leader': return 'bg-leader'
      case 'candidate': return 'bg-candidate'
      case 'follower': return 'bg-follower'
      default: return 'bg-gray-400'
    }
  }
  
  // Convert timestamp to readable format
  const formatTimestamp = (timestamp: number) => {
    if (!timestamp) return 'N/A'
    
    const date = new Date(timestamp * 1000)
    const now = new Date()
    const diffSeconds = Math.floor((now.getTime() - date.getTime()) / 1000)
    
    if (diffSeconds < 60) return `${diffSeconds}s ago`
    if (diffSeconds < 3600) return `${Math.floor(diffSeconds / 60)}m ago`
    if (diffSeconds < 86400) return `${Math.floor(diffSeconds / 3600)}h ago`
    
    return date.toLocaleString()
  }

  return (
    <div className="flex items-center space-x-6 text-sm">
      <div className="flex items-center">
        <Server className="h-4 w-4 mr-2 text-gray-400" />
        <span className="text-gray-500 dark:text-gray-400 mr-1">Node:</span>
        <span className="font-medium">{node.node_id}</span>
      </div>
      
      <div className="flex items-center">
        <div className={`w-3 h-3 rounded-full mr-2 ${getStateColor(node.state)}`} />
        <span className="text-gray-500 dark:text-gray-400 mr-1">State:</span>
        <span className="font-medium">{node.state.charAt(0).toUpperCase() + node.state.slice(1)}</span>
      </div>
      
      <div className="flex items-center">
        <Database className="h-4 w-4 mr-2 text-gray-400" />
        <span className="text-gray-500 dark:text-gray-400 mr-1">Term:</span>
        <span className="font-medium">{node.current_term}</span>
      </div>
      
      <div className="flex items-center">
        <Clock className="h-4 w-4 mr-2 text-gray-400" />
        <span className="text-gray-500 dark:text-gray-400 mr-1">Last heartbeat:</span>
        <span className="font-medium">{formatTimestamp(node.last_heartbeat)}</span>
      </div>
    </div>
  )
}

export default NodePanel