import React from 'react'
import Header from './Header'
import { useTheme } from '@/context/ThemeContext'

interface LayoutProps {
  children: React.ReactNode
}

const Layout: React.FC<LayoutProps> = ({ children }) => {
  const { isDarkMode } = useTheme()

  return (
    <div className={`min-h-screen flex flex-col ${isDarkMode ? 'dark bg-gray-900 text-white' : 'bg-gray-50 text-gray-900'}`}>
      <Header />
      <main className="flex-1 container mx-auto p-4">
        {children}
      </main>
      <footer className="py-4 border-t border-gray-200 dark:border-gray-700">
        <div className="container mx-auto px-4 text-center text-sm text-gray-500 dark:text-gray-400">
          Raft Consensus Algorithm Visualization © {new Date().getFullYear()}
        </div>
      </footer>
    </div>
  )
}

export default Layout