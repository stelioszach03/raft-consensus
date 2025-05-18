import React from 'react'
import { useTheme } from '@/context/ThemeContext'
import { Sun, Moon, Database } from 'lucide-react'

const Header: React.FC = () => {
  const { isDarkMode, toggleTheme } = useTheme()

  return (
    <header className="border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-sm">
      <div className="container mx-auto px-4 py-4 flex justify-between items-center">
        <div className="flex items-center space-x-2">
          <Database className="h-6 w-6 text-primary-500" />
          <h1 className="text-xl font-bold text-gray-900 dark:text-white">Raft Consensus</h1>
        </div>
        
        <div className="flex items-center space-x-4">
          <button
            onClick={toggleTheme}
            className="p-2 rounded-full hover:bg-gray-100 dark:hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-primary-500"
            aria-label="Toggle theme"
          >
            {isDarkMode ? (
              <Sun className="h-5 w-5 text-yellow-500" />
            ) : (
              <Moon className="h-5 w-5 text-gray-500" />
            )}
          </button>
        </div>
      </div>
    </header>
  )
}

export default Header