import { EnvHttpProxyAgent, setGlobalDispatcher } from "undici";

export function configureProxy(): void {
  // Node fetch does not otherwise honor the user's HTTP(S)_PROXY settings.
  if (
    process.env.HTTP_PROXY ||
    process.env.HTTPS_PROXY ||
    process.env.http_proxy ||
    process.env.https_proxy
  ) {
    setGlobalDispatcher(
      new EnvHttpProxyAgent({
        noProxy: [
          process.env.NO_PROXY || process.env.no_proxy,
          "localhost",
          "127.0.0.1",
          "::1",
        ]
          .filter(Boolean)
          .join(","),
      }),
    );
  }
}
