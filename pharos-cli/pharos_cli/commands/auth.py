"""Authentication commands for Pharos CLI."""

import json
import threading
import time
import webbrowser
from typing import Optional
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, urlencode
import uuid
import secrets

import typer
from rich import print
from rich.panel import Panel

from pharos_cli.config.settings import load_config, save_config, get_config_path
from pharos_cli.client.api_client import get_api_client, save_tokens_to_config
from pharos_cli.client.exceptions import AuthenticationError
from pharos_cli.utils.console import get_console

auth_app = typer.Typer(
    name="auth",
    help="Authentication commands for Pharos CLI",
)


@auth_app.callback()
def auth_callback():
    """Authentication commands for Pharos CLI."""
    pass


# OAuth2 callback server
class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler for OAuth2 callback."""

    def log_message(self, format, *args):
        """Suppress default logging."""
        pass

    def do_GET(self):
        """Handle GET request (OAuth2 callback)."""
        parsed = urlparse(self.path)
        if parsed.path == "/callback":
            params = parse_qs(parsed.query)

            # Store the authorization code or error
            OAuthCallbackHandler.auth_code = params.get("code", [None])[0]
            OAuthCallbackHandler.error = params.get("error", [None])[0]
            OAuthCallbackHandler.error_description = params.get("error_description", [None])[0]

            # Send success response
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"""
            <html>
            <head><title>Authentication Successful</title></head>
            <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                <h1 style="color: #10b981;">Authentication Successful!</h1>
                <p>You can close this window and return to the terminal.</p>
            </body>
            </html>
            """)

            # Signal that we received the callback
            OAuthCallbackHandler.callback_received.set()
        else:
            self.send_response(404)
            self.end_headers()

    @classmethod
    def reset(cls):
        """Reset class variables for a new OAuth flow."""
        cls.auth_code = None
        cls.error = None
        cls.error_description = None
        cls.callback_received = threading.Event()


def start_callback_server(port: int) -> HTTPServer:
    """Start the OAuth2 callback server.

    Args:
        port: Port to listen on

    Returns:
        The HTTP server instance
    """
    OAuthCallbackHandler.reset()
    server = HTTPServer(("127.0.0.1", port), OAuthCallbackHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


@auth_app.command("login")
def login(
    api_key: Optional[str] = typer.Option(
        None,
        "--api-key",
        "-k",
        help="API key for authentication",
    ),
    url: Optional[str] = typer.Option(
        None,
        "--url",
        "-u",
        help="API URL (for first-time setup)",
    ),
    oauth: bool = typer.Option(
        False,
        "--oauth",
        "-o",
        help="Use OAuth2 interactive login (opens browser)",
    ),
    provider: str = typer.Option(
        "google",
        "--provider",
        "-p",
        help="OAuth2 provider (google, github)",
    ),
) -> None:
    """Login to Pharos.

    Use --api-key for API key authentication or --oauth for interactive browser-based authentication.
    """
    console = get_console()

    # Load existing config
    config = load_config()

    # If URL is provided, save it
    if url:
        profile = config.get_active_profile()
        profile.api_url = url
        save_config(config)
        console.print(f"[green]API URL set to:[/green] {url}")

    if oauth:
        # OAuth2 interactive login
        _handle_oauth_login(config, provider, console)
    elif api_key:
        # API key login
        _handle_api_key_login(config, api_key, console)
    else:
        # No authentication method specified
        console.print(Panel(
            "[yellow]No authentication method specified.[/yellow]\n\n"
            "Please use one of the following:\n"
            "  • [cyan]--api-key[/cyan] - API key authentication\n"
            "  • [cyan]--oauth[/cyan] - Interactive OAuth2 login (opens browser)\n\n"
            "For API key login:\n"
            "  [dim]pharos auth login --api-key YOUR_API_KEY[/dim]\n\n"
            "For OAuth2 login:\n"
            "  [dim]pharos auth login --oauth[/dim]\n\n"
            "Get your API key from: https://pharos.onrender.com/settings/api-keys",
            title="Authentication Required",
            border_style="yellow"
        ))
        raise typer.Exit(1)


def _handle_api_key_login(config, api_key: str, console) -> None:
    """Handle API key authentication."""
    try:
        import keyring

        profile = config.get_active_profile()
        profile.api_key = api_key
        profile.refresh_token = None
        profile.token_expires_at = None
        keyring.set_password("pharos-cli", config.active_profile, api_key)
        save_config(config)
        console.print("[green]API key saved securely![/green]")
    except Exception as e:
        console.print(f"[red]Error saving API key:[/red] {e}")
        raise typer.Exit(1)

    # Verify authentication
    try:
        client = get_api_client(config)
        response = client.get("/api/v1/auth/whoami")
        console.print(f"[green]Logged in as:[/green] {response.get('username', 'Unknown')}")
    except AuthenticationError:
        console.print("[yellow]Authentication failed. Please provide a valid API key.[/yellow]")
        console.print("Get your API key from: https://pharos.onrender.com/settings/api-keys")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


def _handle_oauth_login(config, provider: str, console) -> None:
    """Handle OAuth2 interactive login."""
    # Validate provider
    if provider not in ["google", "github"]:
        console.print(f"[red]Invalid OAuth provider: {provider}[/red]")
        console.print("Supported providers: google, github")
        raise typer.Exit(1)

    profile = config.get_active_profile()
    api_url = profile.api_url.rstrip("/")

    # Generate PKCE code verifier and challenge
    code_verifier = secrets.token_urlsafe(32)
    code_challenge = secrets.token_urlsafe(32)

    # Generate state for CSRF protection
    state = secrets.token_urlsafe(16)

    # Start callback server
    callback_port = 8765
    try:
        server = start_callback_server(callback_port)
    except Exception as e:
        console.print(f"[red]Failed to start callback server: {e}[/red]")
        raise typer.Exit(1)

    # Build OAuth2 authorization URL
    redirect_uri = f"http://127.0.0.1:{callback_port}/callback"
    auth_url = f"{api_url}/auth/{provider}?{urlencode({
        'redirect_uri': redirect_uri,
        'state': state,
        'code_challenge': code_challenge,
        'code_challenge_method': 'S256',
        'response_type': 'code'
    })}"

    console.print(Panel(
        f"[green]Opening browser for OAuth2 authentication...[/green]\n\n"
        f"If the browser doesn't open, visit:\n"
        f"[cyan]{auth_url}[/cyan]\n\n"
        f"Provider: [bold]{provider.title()}[/bold]",
        title="OAuth2 Login",
        border_style="green"
    ))

    # Open browser
    try:
        webbrowser.open(auth_url)
    except Exception as e:
        console.print(f"[yellow]Could not open browser: {e}[/yellow]")
        console.print(f"Please visit: {auth_url}")

    # Wait for callback
    console.print("[dim]Waiting for authentication...[/dim]")

    try:
        # Wait up to 60 seconds for callback
        callback_received = OAuthCallbackHandler.callback_received.wait(timeout=60)

        if not callback_received:
            console.print("[red]Authentication timed out. Please try again.[/red]")
            server.shutdown()
            raise typer.Exit(1)

        # Check for errors
        if OAuthCallbackHandler.error:
            error_msg = OAuthCallbackHandler.error_description or OAuthCallbackHandler.error
            console.print(f"[red]Authentication failed: {error_msg}[/red]")
            server.shutdown()
            raise typer.Exit(1)

        # Get authorization code
        auth_code = OAuthCallbackHandler.auth_code
        if not auth_code:
            console.print("[red]No authorization code received.[/red]")
            server.shutdown()
            raise typer.Exit(1)

        # Exchange code for tokens
        console.print("[dim]Exchanging authorization code for tokens...[/dim]")

        import httpx

        token_url = f"{api_url}/auth/{provider}/callback"
        with httpx.Client() as client:
            token_response = client.post(
                token_url,
                data={
                    "grant_type": "authorization_code",
                    "code": auth_code,
                    "redirect_uri": redirect_uri,
                    "code_verifier": code_verifier,
                }
            )

            if token_response.status_code != 200:
                console.print(f"[red]Token exchange failed: {token_response.text}[/red]")
                server.shutdown()
                raise typer.Exit(1)

            token_data = token_response.json()
            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")
            expires_in = token_data.get("expires_in", 1800)

        # Save tokens to config
        save_tokens_to_config(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
            config=config
        )

        # Also save to keyring for API key compatibility
        try:
            import keyring
            keyring.set_password("pharos-cli", config.active_profile, access_token)
        except Exception:
            pass  # Keyring is optional

        console.print("[green]OAuth2 authentication successful![/green]")

        # Verify authentication
        try:
            client = get_api_client(config)
            response = client.get("/api/v1/auth/whoami")
            console.print(f"[green]Logged in as:[/green] {response.get('username', 'Unknown')}")
        except Exception:
            pass  # Verification is optional

    finally:
        server.shutdown()


@auth_app.command("logout")
def logout() -> None:
    """Logout from Pharos and clear stored credentials."""
    console = get_console()

    try:
        import keyring

        config = load_config()

        # Try to revoke token on server (best effort)
        try:
            client = get_api_client(config)
            client.post("/auth/logout")
        except Exception:
            pass  # Server-side logout is optional

        # Clear keyring
        try:
            keyring.delete_password("pharos-cli", config.active_profile)
        except Exception:
            pass  # Keyring may not have the credential

        # Clear config
        profile = config.get_active_profile()
        profile.api_key = None
        profile.refresh_token = None
        profile.token_expires_at = None
        save_config(config)

        console.print("[green]Logged out successfully![/green]")
    except Exception as e:
        console.print(f"[red]Error during logout:[/red] {e}")
        raise typer.Exit(1)


@auth_app.command("whoami")
def whoami() -> None:
    """Show current user and authentication status."""
    console = get_console()

    try:
        client = get_api_client()
        response = client.get("/api/v1/auth/whoami")

        console.print(f"[bold]User Information[/bold]")
        console.print(f"  Username: {response.get('username', 'N/A')}")
        console.print(f"  Email: {response.get('email', 'N/A')}")
        console.print(f"  ID: {response.get('id', 'N/A')}")

        # Show token status
        config = load_config()
        profile = config.get_active_profile()

        if profile.token_expires_at:
            import time as time_module
            remaining = profile.token_expires_at - int(time_module.time())
            if remaining > 0:
                minutes = remaining // 60
                seconds = remaining % 60
                console.print(f"\n[bold]Token Status[/bold]")
                console.print(f"  Token expires in: {minutes}m {seconds}s")
            else:
                console.print(f"\n[bold]Token Status[/bold]")
                console.print(f"  [yellow]Token has expired, refresh needed[/yellow]")

    except AuthenticationError:
        console.print("[red]Not authenticated. Run 'pharos auth login' first.[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@auth_app.command("status")
def auth_status() -> None:
    """Show authentication status."""
    console = get_console()

    config = load_config()
    profile = config.get_active_profile()

    console.print("[bold]Authentication Status[/bold]")

    if profile.api_key:
        console.print("  Status: [green]Authenticated[/green]")
        console.print(f"  API URL: {profile.api_url}")

        # Show token type
        if profile.refresh_token:
            console.print("  Token type: [cyan]OAuth2 (with refresh token)[/cyan]")
        else:
            console.print("  Token type: [cyan]API Key[/cyan]")

        # Show token expiration
        if profile.token_expires_at:
            import time as time_module
            remaining = profile.token_expires_at - int(time_module.time())
            if remaining > 0:
                minutes = remaining // 60
                seconds = remaining % 60
                console.print(f"  Token expires in: {minutes}m {seconds}s")
            else:
                console.print("  Token status: [yellow]Expired[/yellow]")
    else:
        console.print("  Status: [yellow]Not authenticated[/yellow]")
        console.print("  Run 'pharos auth login --api-key YOUR_KEY' to authenticate")
        console.print("  Or use 'pharos auth login --oauth' for interactive login")