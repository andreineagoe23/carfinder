// Minimal GitHub REST client: trigger the search workflow and read results from the
// `results` branch. Reading works without a token on a public repo; triggering needs one.

const API = "https://api.github.com";
export const RESULTS_BRANCH = "results";
export const WORKFLOW = "search.yml";

export class GitHubError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

export class GitHub {
  constructor(repo, token) {
    this.repo = repo;
    this.token = token;
  }

  async request(path, { method = "GET", body, accept = "application/vnd.github+json" } = {}) {
    const headers = { Accept: accept, "X-GitHub-Api-Version": "2022-11-28" };
    if (this.token) headers.Authorization = `Bearer ${this.token}`;
    if (body) headers["Content-Type"] = "application/json";
    const response = await fetch(`${API}/repos/${this.repo}${path}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
      cache: "no-store",
    });
    if (!response.ok) {
      let detail = "";
      try {
        detail = (await response.json()).message || "";
      } catch {}
      throw new GitHubError(`GitHub ${response.status}${detail ? `: ${detail}` : ""}`, response.status);
    }
    return response;
  }

  /** JSON file from the results branch, or null if it doesn't exist yet. */
  async readResults(path) {
    try {
      const response = await this.request(`/contents/${path}?ref=${RESULTS_BRANCH}`, {
        accept: "application/vnd.github.raw+json",
      });
      return await response.json();
    } catch (err) {
      if (err.status === 404) return null;
      throw err;
    }
  }

  async dispatch(inputs) {
    await this.request(`/actions/workflows/${WORKFLOW}/dispatches`, {
      method: "POST",
      body: { ref: "main", inputs },
    });
  }

  /** The newest search-workflow run created at or after `since`, if any. */
  async runSince(since) {
    const response = await this.request(
      `/actions/workflows/${WORKFLOW}/runs?event=workflow_dispatch&per_page=5`,
    );
    const { workflow_runs: runs = [] } = await response.json();
    return runs.find((run) => new Date(run.created_at) >= since) || null;
  }
}

/** owner/repo when served from <owner>.github.io/<repo>/, else null. */
export function repoFromLocation(loc = window.location) {
  const match = loc.hostname.match(/^([^.]+)\.github\.io$/i);
  if (!match) return null;
  const first = loc.pathname.split("/").filter(Boolean)[0];
  return `${match[1]}/${first || `${match[1]}.github.io`}`;
}
