"""Command line entry point: `carfinder --help`."""

from __future__ import annotations

import json
import webbrowser
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Optional

import httpx
import typer
from pydantic import ValidationError

from carfinder import __version__
from carfinder.cache import Cache, default_path
from carfinder.catalog import build_catalog
from carfinder.models import SearchProfile
from carfinder.notify import send_telegram
from carfinder.profiles import default_dir, list_profiles, load_profile
from carfinder.search import run_search
from carfinder.sites import SITES, build_links
from carfinder.store import SearchResult, Store

app = typer.Typer(help="Search German used-car sites from one reusable profile.", no_args_is_help=True)

USER_AGENT = f"carfinder/{__version__} (personal car search tool)"

ProfilesDir = Annotated[
    Path, typer.Option("--profiles-dir", "-d", help="Folder with profile YAML files.")
]
ResultsDir = Annotated[Path, typer.Option("--results-dir", "-r", help="Where search results are stored.")]
MaxPages = Annotated[int, typer.Option("--max-pages", min=1, max=10, help="Result pages to read per site.")]
Notify = Annotated[bool, typer.Option("--notify", help="Send new listings to Telegram (needs env vars).")]


def http_client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=20, follow_redirects=True)


def fail(message: str) -> typer.Exit:
    typer.secho(message, fg="red", err=True)
    return typer.Exit(1)


@contextmanager
def user_errors():
    """Turn bad input into a one-line message instead of a traceback."""
    try:
        yield
    except (FileNotFoundError, ValueError, ValidationError) as exc:
        raise fail(str(exc)) from exc


def _resolve_name(directory: Path, name: str | None) -> str:
    if name:
        return name
    names = list_profiles(directory)
    if len(names) == 1:
        return names[0]
    raise fail(f"Pick a profile: {', '.join(names) or '(none found)'}")


def _print_result(result: SearchResult) -> None:
    typer.secho(f"{result.query.summary()}  [{result.id}]", bold=True)
    for site, error in result.errors.items():
        typer.secho(f"  {site}: {error}", fg="yellow")
    typer.echo(f"  {len(result.listings)} listings, {len(result.new_listings)} new")
    for car in result.listings[:10]:
        typer.echo(
            f"  {car.score:>3}  €{car.price_eur:>7,}  {car.year or '?':>4}  "
            f"{(car.mileage_km or 0):>7,} km  {car.source:<13} {car.title[:50]}"
        )


@app.command()
def profiles(directory: ProfilesDir = default_dir()) -> None:
    """List saved search profiles."""
    for name in list_profiles(directory):
        typer.echo(f"{name:<20} {load_profile(directory, name).summary()}")


@app.command()
def links(
    profile: Annotated[Optional[str], typer.Argument(help="Profile name (file name without .yaml).")] = None,
    open_: Annotated[bool, typer.Option("--open", "-o", help="Open every link in the browser.")] = False,
    site: Annotated[
        Optional[list[str]], typer.Option("--site", "-s", help=f"Only these sites: {', '.join(SITES)}.")
    ] = None,
    directory: ProfilesDir = default_dir(),
) -> None:
    """Print pre-filtered search links for every site."""
    with user_errors():
        search = load_profile(directory, _resolve_name(directory, profile))
        with http_client() as client:
            results = build_links(search, client, Cache(default_path()), only=site)

    typer.secho(search.summary(), bold=True)
    for link in results:
        typer.echo()
        typer.secho(link.name, fg="cyan", bold=True)
        if link.error:
            typer.secho(f"  error: {link.error}", fg="red")
            continue
        typer.echo(f"  {link.url}")
        for note in link.notes:
            typer.secho(f"  note: {note}", fg="yellow")
        if open_:
            webbrowser.open_new_tab(link.url)

    if any(link.error for link in results):
        raise typer.Exit(1)


@app.command()
def search(
    profile: Annotated[Optional[str], typer.Argument(help="Profile name; or use --query-json.")] = None,
    query_json: Annotated[Optional[str], typer.Option("--query-json", help="Search profile as JSON.")] = None,
    search_id: Annotated[Optional[str], typer.Option("--id", help="Results ID (12 hex chars).")] = None,
    results_dir: ResultsDir = Path("results"),
    max_pages: MaxPages = 3,
    notify: Notify = False,
    directory: ProfilesDir = default_dir(),
) -> None:
    """Fetch listings for one search and save them to the results folder."""
    with user_errors():
        if query_json:
            query = SearchProfile.model_validate(json.loads(query_json))
        else:
            query = load_profile(directory, _resolve_name(directory, profile))
        with http_client() as client:
            result = run_search(query, client, Cache(default_path()), Store(results_dir), search_id, max_pages)
            if notify:
                send_telegram(client, result)
    _print_result(result)


@app.command()
def refresh(results_dir: ResultsDir = Path("results"), max_pages: MaxPages = 3, notify: Notify = False) -> None:
    """Re-run every saved search (used by the scheduled GitHub Action)."""
    store = Store(results_dir)
    with http_client() as client:
        for saved in store.all():
            result = run_search(saved.query, client, Cache(default_path()), store, saved.id, max_pages)
            _print_result(result)
            if notify:
                send_telegram(client, result)


@app.command()
def delete(search_id: str, results_dir: ResultsDir = Path("results")) -> None:
    """Remove a saved search and its results."""
    with user_errors():
        if not Store(results_dir).delete(search_id):
            raise fail(f"No search {search_id}")
    typer.echo(f"Deleted {search_id}")


@app.command()
def catalog(out: Path = Path("site/data/catalog.json")) -> None:
    """Rebuild the make/model list used by the web UI (slow: one request per make)."""
    with http_client() as client:
        data = build_catalog(client)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    typer.echo(f"{len(data['makes'])} makes written to {out}")


if __name__ == "__main__":
    app()
