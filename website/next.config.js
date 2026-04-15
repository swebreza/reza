/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  images: {
    unoptimized: true,
  },
  experimental: {
    serverComponentsExternalPackages: ['shiki', 'rehype-pretty-code'],
  },
};

module.exports = nextConfig;
