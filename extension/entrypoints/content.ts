import { defineContentScript } from "wxt/sandbox";

export default defineContentScript({
  matches: ["<all_urls>"],
  main() {
    const root = document.createElement("div");
    root.id = "agente-atendimento-root";
    root.style.cssText =
      "position:fixed;bottom:20px;right:20px;z-index:2147483647;";
    document.body.appendChild(root);
  },
});
