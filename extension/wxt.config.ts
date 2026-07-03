import { defineConfig } from "wxt";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  manifestVersion: 3,
  extensionApi: "chrome",
  vite: () => ({
    plugins: [vue()],
  }),
  manifest: {
    name: "Agente de Atendimento",
    description: "Gera sugestões de resposta inteligentes para plataformas de atendimento",
    version: "1.0.0",
    permissions: ["storage", "activeTab", "scripting", "tabs", "alarms", "sidePanel", "contextMenus"],
    host_permissions: ["https://agente-de-atendimento.onrender.com/*", "<all_urls>"],
    web_accessible_resources: [{ resources: ["*"], matches: ["<all_urls>"] }],
    action: {
      default_title: "Agente de Atendimento",
    },
    side_panel: {
      default_path: "sidepanel.html",
    },
  },
});
