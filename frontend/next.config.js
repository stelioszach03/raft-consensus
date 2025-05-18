/** @type {import('next').NextConfig} */
const nextConfig = {
    reactStrictMode: true,
    async rewrites() {
      return [
        {
          source: '/api/:path*',
          destination: 'http://localhost:8100/:path*', // Χρησιμοποιούμε τη θύρα 8100
        },
      ];
    },
  }
  
  module.exports = nextConfig