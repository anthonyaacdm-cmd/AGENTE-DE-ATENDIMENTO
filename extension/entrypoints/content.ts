import { defineContentScript } from "wxt/sandbox";

export default defineContentScript({
  matches: ["<all_urls>"],
  main() {
    // Content script vazio - a interação é feita via:
    // - Ícone da extensão na toolbar (abre sidepanel)
    // - Clique direito → "Analisar com Agente de Atendimento"
    // - Popup da extensão
  },
});
