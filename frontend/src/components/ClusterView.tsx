import React, { useEffect, useRef } from 'react'
import { motion } from 'framer-motion'
import { useTheme } from '@/context/ThemeContext'

interface ClusterViewProps {
  clusterState: any
}

const ClusterView: React.FC<ClusterViewProps> = ({ clusterState }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const { isDarkMode } = useTheme()
  
  useEffect(() => {
    if (!clusterState || !canvasRef.current) return
    
    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    
    // Clear canvas
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    
    // Calculate positions
    const centerX = canvas.width / 2
    const centerY = canvas.height / 2
    const radius = Math.min(centerX, centerY) - 50
    
    // Get all nodes
    const nodes = [clusterState]
    if (clusterState.peers) {
      Object.keys(clusterState.peers).forEach(peerId => {
        nodes.push({
          node_id: peerId,
          state: "follower", // Assume peer is follower unless we know otherwise
          ...clusterState.peers[peerId]
        })
      })
    }
    
    // Draw connections
    ctx.lineWidth = 2
    ctx.strokeStyle = isDarkMode ? 'rgba(156, 163, 175, 0.3)' : 'rgba(156, 163, 175, 0.5)'
    
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const angle1 = (i * 2 * Math.PI) / nodes.length
        const angle2 = (j * 2 * Math.PI) / nodes.length
        
        const x1 = centerX + radius * Math.cos(angle1)
        const y1 = centerY + radius * Math.sin(angle1)
        const x2 = centerX + radius * Math.cos(angle2)
        const y2 = centerY + radius * Math.sin(angle2)
        
        ctx.beginPath()
        ctx.moveTo(x1, y1)
        ctx.lineTo(x2, y2)
        ctx.stroke()
      }
    }
    
    // Highlight leader connections
    if (clusterState.state === 'leader') {
      ctx.lineWidth = 3
      ctx.strokeStyle = isDarkMode ? 'rgba(16, 185, 129, 0.6)' : 'rgba(16, 185, 129, 0.8)'
      
      const leaderIndex = 0 // The current node is always first
      const leaderAngle = (leaderIndex * 2 * Math.PI) / nodes.length
      const leaderX = centerX + radius * Math.cos(leaderAngle)
      const leaderY = centerY + radius * Math.sin(leaderAngle)
      
      for (let i = 1; i < nodes.length; i++) {
        const angle = (i * 2 * Math.PI) / nodes.length
        const x = centerX + radius * Math.cos(angle)
        const y = centerY + radius * Math.sin(angle)
        
        ctx.beginPath()
        ctx.moveTo(leaderX, leaderY)
        ctx.lineTo(x, y)
        ctx.stroke()
        
        // Draw arrow
        const dx = x - leaderX
        const dy = y - leaderY
        const length = Math.sqrt(dx * dx + dy * dy)
        const unitX = dx / length
        const unitY = dy / length
        
        const arrowX = leaderX + unitX * (length - 30)
        const arrowY = leaderY + unitY * (length - 30)
        
        ctx.beginPath()
        ctx.moveTo(arrowX, arrowY)
        ctx.lineTo(
          arrowX - unitX * 15 + unitY * 8,
          arrowY - unitY * 15 - unitX * 8
        )
        ctx.lineTo(
          arrowX - unitX * 15 - unitY * 8,
          arrowY - unitY * 15 + unitX * 8
        )
        ctx.closePath()
        ctx.fillStyle = isDarkMode ? 'rgba(16, 185, 129, 0.6)' : 'rgba(16, 185, 129, 0.8)'
        ctx.fill()
      }
    }
    
  }, [clusterState, isDarkMode])
  
  if (!clusterState) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-gray-500 dark:text-gray-400">Loading cluster information...</p>
      </div>
    )
  }
  
  // Map state to color
  const getStateColor = (state: string) => {
    switch (state) {
      case 'leader': return 'bg-leader'
      case 'candidate': return 'bg-candidate'
      case 'follower': return 'bg-follower'
      default: return 'bg-gray-400'
    }
  }
  
  // Map state to text
  const getStateText = (state: string) => {
    switch (state) {
      case 'leader': return 'Leader'
      case 'candidate': return 'Candidate'
      case 'follower': return 'Follower'
      default: return 'Unknown'
    }
  }
  
  return (
    <div className="flex flex-col h-full">
      <h2 className="text-xl font-semibold mb-4">Cluster Visualization</h2>
      
      <div className="flex-1 flex flex-col lg:flex-row gap-4">
        <div className="flex-1 border dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 p-4 shadow-sm">
          <div className="mb-4">
            <h3 className="text-lg font-medium">Network View</h3>
            <p className="text-sm text-gray-500 dark:text-gray-400">Visual representation of the Raft cluster</p>
          </div>
          
          <div className="relative h-80 w-full">
            <canvas 
              ref={canvasRef} 
              width={500} 
              height={300} 
              className="absolute inset-0 w-full h-full"
            />
            
            {/* Node circles positioned absolutely */}
            <div className="absolute inset-0">
              {/* Current node */}
              <motion.div 
                className={`absolute w-16 h-16 rounded-full flex items-center justify-center text-white font-medium shadow-lg ${getStateColor(clusterState.state)}`}
                style={{ 
                  left: '50%', 
                  top: '50%',
                  marginLeft: '-2rem',
                  marginTop: '-2rem',
                }}
                initial={{ scale: 0.8 }}
                animate={{ scale: 1 }}
                transition={{ duration: 0.5 }}
              >
                {clusterState.node_id}
              </motion.div>
              
              {/* Peer nodes */}
              {clusterState.peers && Object.keys(clusterState.peers).map((peerId, index) => {
                const angle = ((index + 1) * 2 * Math.PI) / (Object.keys(clusterState.peers).length + 1)
                const radius = 120 // Distance from center
                const x = Math.cos(angle) * radius + 250 - 32 // 250 is center, 32 is half of node width
                const y = Math.sin(angle) * radius + 150 - 32 // 150 is center, 32 is half of node height
                
                return (
                  <motion.div 
                    key={peerId}
                    className={`absolute w-16 h-16 rounded-full flex items-center justify-center text-white font-medium shadow-lg bg-follower`}
                    style={{ left: `${x}px`, top: `${y}px` }}
                    initial={{ scale: 0.8, opacity: 0 }}
                    animate={{ scale: 1, opacity: 1 }}
                    transition={{ duration: 0.5, delay: index * 0.1 }}
                  >
                    {peerId}
                  </motion.div>
                )
              })}
            </div>
          </div>
        </div>
        
        <div className="lg:w-80 border dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 p-4 shadow-sm">
          <h3 className="text-lg font-medium mb-3">Cluster Status</h3>
          
          <div className="space-y-4">
            <div>
              <h4 className="text-sm font-medium text-gray-500 dark:text-gray-400">Current Node</h4>
              <div className="flex items-center mt-1">
                <div className={`w-3 h-3 rounded-full mr-2 ${getStateColor(clusterState.state)}`}></div>
                <span className="font-medium">{clusterState.node_id}</span>
                <span className="ml-2 text-xs px-2 py-1 rounded-full bg-gray-100 dark:bg-gray-700">
                  {getStateText(clusterState.state)}
                </span>
              </div>
            </div>
            
            <div>
              <h4 className="text-sm font-medium text-gray-500 dark:text-gray-400">Term</h4>
              <p className="font-medium">{clusterState.current_term}</p>
            </div>
            
            <div>
              <h4 className="text-sm font-medium text-gray-500 dark:text-gray-400">Leader</h4>
              <p className="font-medium">{clusterState.leader_id || 'None'}</p>
            </div>
            
            <div>
              <h4 className="text-sm font-medium text-gray-500 dark:text-gray-400">Voted For</h4>
              <p className="font-medium">{clusterState.voted_for || 'None'}</p>
            </div>
            
            <div>
              <h4 className="text-sm font-medium text-gray-500 dark:text-gray-400">Commit Index</h4>
              <p className="font-medium">{clusterState.commit_index}</p>
            </div>
            
            <div>
              <h4 className="text-sm font-medium text-gray-500 dark:text-gray-400">Log Size</h4>
              <p className="font-medium">{clusterState.log_size} entries</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default ClusterView