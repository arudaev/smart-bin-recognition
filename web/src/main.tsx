import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import { registerServiceWorker } from "./pwa";
import { startVitals } from "./perf/vitals";
import "./styles/index.css";

const root = document.getElementById("root");
if (!root) throw new Error("no #root element");

/* Vitals first: the observers have to exist before the paint they are meant to
   measure, and buffered entries only reach a listener that was already there. */
startVitals();

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

/* Registration waits for load. The worker's install fetches the whole precache
   list, and doing that while the first screen is still arriving competes for
   exactly the connection this product assumes is bad. */
window.addEventListener("load", () => {
  void registerServiceWorker();
});
