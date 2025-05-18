import React from 'react'
import { 
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  BarChart, Bar, PieChart, Pie, Cell
} from 'recharts'
import { motion } from 'framer-motion'

interface DashboardProps {
  clusterState: any
  logEntries: any[]
}

const Dashboard: React.FC<DashboardProps> = ({ clusterState, logEntries = [] }) => {
  // Generate some data for the charts based on log entries
  const getLogActivityData = () => {
    // Group log entries by term
    const entriesByTerm: Record<number, number> = {}
    logEntries.forEach(entry => {
      entriesByTerm[entry.term] = (entriesByTerm[entry.term] || 0) + 1
    })
    
    return Object.keys(entriesByTerm).map(term => ({
      term: `Term ${term}`,
      entries: entriesByTerm[Number(term)]
    }))
  }
  
  const getOperationTypesData = () => {
    // Count operation types
    const operations: Record<string, number> = {}
    logEntries.forEach(entry => {
      const op = entry.command.operation
      operations[op] = (operations[op] || 0) + 1
    })
    
    return Object.keys(operations).map(op => ({
      name: op,
      value: operations[op]
    }))
  }
  
  // Generate mock data if no log entries
  const logActivityData = logEntries.length > 0 
    ? getLogActivityData() 
    : [
        { term: 'Term 1', entries: 5 },
        { term: 'Term 2', entries: 8 },
        { term: 'Term 3', entries: 3 }
      ]
  
  const operationTypesData = logEntries.length > 0
    ? getOperationTypesData()
    : [
        { name: 'set', value: 10 },
        { name: 'get', value: 5 },
        { name: 'delete', value: 2 }
      ]
  
  const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042']
  
  // Status indicator animation
  const pulseAnimation = {
    scale: [1, 1.05, 1],
    transition: { 
      duration: 2,
      repeat: Infinity,
      repeatType: "loop" as const  // Διόρθωση: Βεβαιωθείτε ότι ο τύπος καθορίζεται σωστά
    }
  }
  
  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 h-full">
      {/* Status Card */}
      <motion.div 
        className="col-span-1 border dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 p-6 shadow-sm"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
      >
        <h3 className="text-lg font-medium mb-4">Cluster Status</h3>
        
        {clusterState ? (
          <div className="space-y-4">
            <div className="flex items-center">
              <motion.div 
                className={`w-4 h-4 rounded-full mr-2 ${
                  clusterState.state === 'leader' ? 'bg-leader' :
                  clusterState.state === 'candidate' ? 'bg-candidate' : 'bg-follower'
                }`}
                animate={pulseAnimation}
              />
              <span className="font-medium">Node: {clusterState.node_id}</span>
              <span className="ml-2 text-xs px-2 py-1 rounded-full bg-gray-100 dark:bg-gray-700">
                {clusterState.state.charAt(0).toUpperCase() + clusterState.state.slice(1)}
              </span>
            </div>
            
            <div className="grid grid-cols-2 gap-2 text-sm">
              <div>
                <span className="text-gray-500 dark:text-gray-400">Current Term:</span>
                <p className="font-medium">{clusterState.current_term}</p>
              </div>
              <div>
                <span className="text-gray-500 dark:text-gray-400">Leader:</span>
                <p className="font-medium">{clusterState.leader_id || 'None'}</p>
              </div>
              <div>
                <span className="text-gray-500 dark:text-gray-400">Commit Index:</span>
                <p className="font-medium">{clusterState.commit_index}</p>
              </div>
              <div>
                <span className="text-gray-500 dark:text-gray-400">Log Size:</span>
                <p className="font-medium">{clusterState.log_size}</p>
              </div>
            </div>
            
            <div className="mt-4">
              <h4 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2">Peers</h4>
              {clusterState.peers && Object.keys(clusterState.peers).length > 0 ? (
                <div className="space-y-2">
                  {Object.keys(clusterState.peers).map(peerId => (
                    <div key={peerId} className="flex items-center justify-between p-2 bg-gray-50 dark:bg-gray-700 rounded">
                      <span>{peerId}</span>
                      {clusterState.state === 'leader' && (
                        <div className="text-xs text-gray-500 dark:text-gray-400">
                          Next: {clusterState.peers[peerId]?.next_index || '?'}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-gray-500 dark:text-gray-400">No peers connected</p>
              )}
            </div>
          </div>
        ) : (
          <div className="animate-pulse space-y-4">
            <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-3/4"></div>
            <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-1/2"></div>
            <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-5/6"></div>
          </div>
        )}
      </motion.div>
      
      {/* Charts */}
      <motion.div 
        className="col-span-1 lg:col-span-2 border dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 p-6 shadow-sm"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.1 }}
      >
        <h3 className="text-lg font-medium mb-4">Log Activity</h3>
        
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={logActivityData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="term" />
              <YAxis />
              <Tooltip />
              <Legend />
              <Bar dataKey="entries" name="Number of Entries" fill="#0369a1" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </motion.div>
      
      {/* Recent Operations */}
      <motion.div 
        className="col-span-1 border dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 p-6 shadow-sm"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.2 }}
      >
        <h3 className="text-lg font-medium mb-4">Recent Operations</h3>
        
        {logEntries.length > 0 ? (
          <div className="space-y-2">
            {logEntries.slice(-5).reverse().map(entry => (
              <div 
                key={entry.index}
                className="p-2 bg-gray-50 dark:bg-gray-700 rounded text-sm"
              >
                <div className="flex justify-between">
                  <span className="font-medium">
                    {entry.command.operation.toUpperCase()}
                  </span>
                  <span className="text-xs text-gray-500 dark:text-gray-400">
                    Term {entry.term}, Index {entry.index}
                  </span>
                </div>
                {entry.command.key && (
                  <div className="mt-1">
                    <span className="text-gray-500 dark:text-gray-400">Key: </span>
                    <span>{entry.command.key}</span>
                    
                    {entry.command.value !== undefined && (
                      <>
                        <span className="mx-1 text-gray-400">→</span>
                        <span>{typeof entry.command.value === 'object' 
                          ? JSON.stringify(entry.command.value) 
                          : String(entry.command.value)}
                        </span>
                      </>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-gray-500 dark:text-gray-400">No operations recorded yet</p>
        )}
      </motion.div>
      
      {/* Operation Types */}
      <motion.div 
        className="col-span-1 lg:col-span-2 border dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 p-6 shadow-sm"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.3 }}
      >
        <h3 className="text-lg font-medium mb-4">Operation Types</h3>
        
        <div className="h-64 flex items-center justify-center">
          {operationTypesData.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={operationTypesData}
                  cx="50%"
                  cy="50%"
                  labelLine={false}
                  outerRadius={80}
                  fill="#8884d8"
                  dataKey="value"
                  label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                >
                  {operationTypesData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-sm text-gray-500 dark:text-gray-400">No operation data available</p>
          )}
        </div>
      </motion.div>
    </div>
  )
}

export default Dashboard