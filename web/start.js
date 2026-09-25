// Load the interface language before any module evaluates its copy tables.
import { initI18n, translateDom } from "./i18n.js";
import { initEffects } from "./effects.js";

await initI18n();
translateDom();
initEffects();
await import("./app.js");
