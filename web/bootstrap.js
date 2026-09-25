import { t } from "./i18n.js";

const dynamicImport = (url) => import(url);

async function responseBody(responsePromise, url, reader) {
  const response = await responsePromise;
  if (!response.ok) {
    throw new Error(t("Не удалось загрузить {0}: HTTP {1}", url, response.status));
  }
  return response[reader]();
}

export async function loadCoreResources({
  pyodideUrl,
  oozUrl,
  importModule = dynamicImport,
  fetchResource = globalThis.fetch.bind(globalThis),
}) {
  const oozPromise = importModule(oozUrl);
  const pyodideModulePromise = importModule(`${pyodideUrl}pyodide.mjs`);
  const bundlePromise = responseBody(fetchResource("pysrc.json"), "pysrc.json", "json");
  const bridgeSourcePromise = responseBody(
    fetchResource("web_bridge.py"),
    "web_bridge.py",
    "text",
  );
  const pyPromise = pyodideModulePromise.then(({ loadPyodide }) =>
    loadPyodide({ indexURL: pyodideUrl }));

  const [ooz, py, bundle, bridgeSource] = await Promise.all([
    oozPromise,
    pyPromise,
    bundlePromise,
    bridgeSourcePromise,
  ]);
  return { bridgeSource, bundle, ooz, py };
}

export async function installCatalogs({
  bridge,
  fetchResource = globalThis.fetch.bind(globalThis),
  catalogUrl = "catalogs.json",
  namesUrl = "catalog_names.json",
  s2ItemsUrl = "s2_items.json",
}) {
  const catalogs = await responseBody(fetchResource(catalogUrl), catalogUrl, "text");
  bridge.install_catalogs(catalogs);
  // Official names in every language; the page still works without them.
  try {
    const names = await responseBody(fetchResource(namesUrl), namesUrl, "text");
    bridge.install_official_names(names);
  } catch { /* catalog names stay in use */ }
  // S.T.A.L.K.E.R. 2 official names and icons; optional as well.
  try {
    const s2Items = await responseBody(fetchResource(s2ItemsUrl), s2ItemsUrl, "text");
    bridge.install_s2_items(s2Items);
  } catch { /* composed S2 names stay in use */ }
}
