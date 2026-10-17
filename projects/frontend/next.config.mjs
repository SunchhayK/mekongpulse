/** @type {import('next').NextConfig} */
const nextConfig = {
  // "export" produces the static bundle deployed to Firebase Hosting;
  // "standalone" powers the containerized staging stack.
  output: process.env.NEXT_OUTPUT === "export" ? "export" : "standalone",
  reactStrictMode: true,
};

export default nextConfig;
