import type { NextConfig } from "next";
import createNextIntlPlugin from 'next-intl/plugin';
import fs from 'fs';
import path from 'path';

const withNextIntl = createNextIntlPlugin('./i18n/request.ts');

const packageJson = JSON.parse(fs.readFileSync(path.resolve(__dirname, 'package.json'), 'utf-8'));

const nextConfig: NextConfig = {
  // Enable standalone output for Docker deployment
  output: 'standalone',
  env: {
    NEXT_PUBLIC_APP_VERSION: process.env.NEXT_PUBLIC_APP_VERSION || packageJson.version,
    NEXT_PUBLIC_BUILD_DATE: process.env.NEXT_PUBLIC_BUILD_DATE || new Date().toISOString().split('T')[0],
  },
  turbopack: {
    root: path.resolve(__dirname),
  },
  images: {
    dangerouslyAllowSVG: true,
    remotePatterns: [
      {
        protocol: 'http',
        hostname: 'localhost',
        port: '8000',
        pathname: '/api/v1/upload/**',
      },
      {
        protocol: 'http',
        hostname: '127.0.0.1',
        port: '8000',
        pathname: '/api/v1/upload/**',
      },
      {
        protocol: 'https',
        hostname: '**',
      },
    ],
  },
  // 允许开发环境访问本地图片
  allowedDevOrigins: ['http://localhost:8000', 'http://127.0.0.1:8000'],
  // API 代理转发
  async rewrites() {
    const backendUrl = process.env.BACKEND_INTERNAL_URL || 'http://localhost:8000';
    return [
      {
        source: '/api/:path*',
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

export default withNextIntl(nextConfig);
