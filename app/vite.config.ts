import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// 相对路径打包，方便 Tauri 和静态页面直接加载。
export default defineConfig({
  base: "./",
  plugins: [react()],
  test: { environment: "node" },
});
