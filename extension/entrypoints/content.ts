import { defineContentScript } from "wxt/sandbox";

export default defineContentScript({
  matches: ["<all_urls>"],
  main() {
    if (document.getElementById("agente-atendimento-root")) return;

    const root = document.createElement("div");
    root.id = "agente-atendimento-root";
    root.style.cssText = "position:fixed;bottom:24px;right:24px;z-index:2147483647;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;";

    const btn = document.createElement("button");
    btn.id = "agente-floating-btn";
    btn.style.cssText =
      "width:52px;height:52px;border-radius:50%;border:none;background:linear-gradient(135deg,#4f46e5,#7c3aed);color:white;font-size:22px;cursor:pointer;box-shadow:0 4px 16px rgba(79,70,229,0.4);transition:transform 0.2s,box-shadow 0.2s;display:flex;align-items:center;justify-content:center;";
    btn.textContent = "G";
    btn.title = "Agente de Atendimento";
    btn.onmouseenter = () => {
      btn.style.transform = "scale(1.1)";
      btn.style.boxShadow = "0 6px 24px rgba(79,70,229,0.6)";
    };
    btn.onmouseleave = () => {
      btn.style.transform = "scale(1)";
      btn.style.boxShadow = "0 4px 16px rgba(79,70,229,0.4)";
    };
    btn.onclick = async () => {
      try {
        await chrome.sidePanel.open({ windowId: (await chrome.windows.getCurrent()).id });
      } catch {
        try {
          await chrome.runtime.sendMessage({ type: "OPEN_SIDEPANEL" });
        } catch {
          window.open(chrome.runtime.getURL("popup.html"), "agente", "width=480,height=640");
        }
      }
    };

    root.appendChild(btn);
    document.body.appendChild(root);
  },
});
