import { ragBaseUrl } from "../../config/models.js";

/** Single HTTP boundary for the Python sidecar. Status/body remain caller-owned. */
export function requestKnowledge(
  path: string,
  options?: RequestInit,
): Promise<Response> {
  return fetch(`${ragBaseUrl}${path}`, options);
}
