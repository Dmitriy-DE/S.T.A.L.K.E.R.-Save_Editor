const dynamicImport = (url) => import(url);

async function responseBody(responsePromise, url, reader) {
  const response = await responsePromise;
  if (!response.ok) {
    throw new Error(`Не удалось загрузить ${url}: HTTP ${response.status}`);
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
}) {
  const catalogs = await responseBody(fetchResource(catalogUrl), catalogUrl, "text");
  bridge.install_catalogs(catalogs);
}
