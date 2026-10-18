import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin();

/** @type {import('next').NextConfig} */
const nextConfig = {
  // "export" produces the static bundle deployed to Firebase Hosting;
  // "standalone" powers the containerized staging stack.
  output: process.env.NEXT_OUTPUT === "export" ? "export" : "standalone",
  reactStrictMode: true,
  // Emit directory-style routes (/km/index.html, /en/index.html) so Firebase
  // Hosting serves locales as directories alongside its catch-all behaviour.
  trailingSlash: true,
};

export default withNextIntl(nextConfig);
