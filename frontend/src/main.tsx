import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./theme/tokens.css";
import "./theme/app.css";

const rootElement = document.getElementById("root");

if (!rootElement) {
  throw new Error("Operator frontend root element not found.");
}

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>
);
