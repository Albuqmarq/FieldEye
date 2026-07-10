import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // "standalone" gera um servidor mínimo e autocontido para rodar no Docker.
  output: "standalone",
};

export default nextConfig;
