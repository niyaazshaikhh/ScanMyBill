/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  ...(process.env.VERCEL ? {} : { output: 'standalone' }),
  experimental: {
    typedRoutes: false
  }
};

export default nextConfig;
