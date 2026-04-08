

import { createRoot } from "react-dom/client";
import App from "./App.tsx";
import "./index.css";

console.log("main.tsx: Starting app render...");

const rootElement = document.getElementById("root");
console.log("main.tsx: Root element:", rootElement);

if (rootElement) {
  try {
    const root = createRoot(rootElement);
    console.log("main.tsx: Root created, rendering App...");
    root.render(<App />);
    console.log("main.tsx: App rendered successfully");
  } catch (error) {
    console.error("main.tsx: Error rendering app:", error);
    // Force throw to trigger window.onerror
    throw error;
  }
} else {
  console.error("main.tsx: Root element not found!");
}
