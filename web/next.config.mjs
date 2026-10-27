/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  async rewrites() {
    // Intended frontend -> backend route: browser calls /api/*, Next proxies
    // server-side to the FastAPI service. No credentials in the browser.
    return [{ source: "/api/:path*", destination: `${process.env.API_INTERNAL_URL ?? "http://api:8000"}/:path*` }];
  },
};

export default nextConfig;
