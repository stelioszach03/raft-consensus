import React, { useState } from 'react'
import { motion } from 'framer-motion'
import { Search } from 'lucide-react'

interface LogEntry {
  index: number
  term: number
  command: {
    operation: string
    key?: string
    value?: any
  }
}

interface LogViewProps {
  entries: LogEntry[]
}

const LogView: React.FC<LogViewProps> = ({ entries = [] }) => {
  const [filter, setFilter] = useState('')
  
  // Filter entries
  const filteredEntries = entries.filter(entry => {
    if (!filter) return true
    
    const searchLower = filter.toLowerCase()
    const commandStr = JSON.stringify(entry.command).toLowerCase()
    
    return (
      entry.index.toString().includes(searchLower) ||
      entry.term.toString().includes(searchLower) ||
      commandStr.includes(searchLower)
    )
  })

  return (
    <div className="flex flex-col h-full">
      <h2 className="text-xl font-semibold mb-4">Log Entries</h2>
      
      <div className="mb-4 relative">
        <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
          <Search className="h-5 w-5 text-gray-400" />
        </div>
        <input
          type="text"
          placeholder="Search log entries..."
          className="pl-10 w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 shadow-sm focus:border-primary-500 focus:ring-primary-500 text-sm p-2"
          value={filter}
          onChange={e => setFilter(e.target.value)}
        />
      </div>
      
      {entries.length === 0 ? (
        <div className="flex-1 flex items-center justify-center">
          <p className="text-gray-500 dark:text-gray-400">No log entries available</p>
        </div>
      ) : (
        <div className="flex-1 border dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
              <thead className="bg-gray-50 dark:bg-gray-700">
                <tr>
                  <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                    Index
                  </th>
                  <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                    Term
                  </th>
                  <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                    Operation
                  </th>
                  <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                    Key
                  </th>
                  <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                    Value
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                {filteredEntries.map((entry, i) => (
                  <motion.tr 
                    key={entry.index}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.3, delay: i * 0.03 }}
                    className={i % 2 === 0 ? 'bg-white dark:bg-gray-800' : 'bg-gray-50 dark:bg-gray-700'}
                  >
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900 dark:text-white">
                      {entry.index}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-300">
                      {entry.term}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-300">
                      {entry.command.operation}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-300">
                      {entry.command.key || '-'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-300">
                      {entry.command.value !== undefined 
                        ? (typeof entry.command.value === 'object' 
                          ? JSON.stringify(entry.command.value) 
                          : String(entry.command.value))
                        : '-'}
                    </td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

export default LogView