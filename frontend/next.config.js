/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'export',
  reactStrictMode: true,
  // Οι rewrites δεν λειτουργούν με output: 'export'
}

module.exports = nextConfig