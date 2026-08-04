import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import { readPreferences } from "./app/preferences";
import { applyThemeToDocument } from "./app/theme";
import { registerServiceWorker } from "./pwa";
import { startVitals } from "./perf/vitals";
import "./styles/index.css";

const root = document.getElementById("root");
if (!root) throw new Error("no #root element");

/* Vitals first: the observers have to exist before the paint they are meant to
   measure, and buffered entries only reach a listener that was already there. */
startVitals();

/* Then the theme, before React renders anything.
 *
 * data-theme, dir and lang go on <html>, and doing it here rather than in an
 * effect is what keeps somebody who chose night from seeing a frame of paper
 * first. An inline <script> in index.html would be a few milliseconds earlier
 * and is not available: vercel.json sets script-src 'self' with no
 * unsafe-inline and no hashes, so it would work in dev and be blocked in
 * production. tokens/modes.css covers the frame before this line runs.
 *
 * App reads the same preferences again for its own state. Two reads of one
 * localStorage key is cheaper than the alternative, which is a boot path that
 * has to hand a value from a module to a component before either exists. */
const preferences = readPreferences();
applyThemeToDocument(preferences.mode, preferences.locale);

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
