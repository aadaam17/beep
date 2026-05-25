"""Textual application entrypoint for Beep interactive mode."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header

from storage.session import clear_session, load_session
from ui.screens.home import HomeScreen
from ui.screens.login import LoginView


class BeepApp(App[None]):
    """Terminal-native Beep application."""

    TITLE = "Beep"
    SUB_TITLE = "Interactive social shell"
    CSS = """
    Screen {
        layout: vertical;
    }

    #app-root {
        height: 1fr;
    }

    #shell-root {
        height: 1fr;
    }

    #home-layout {
        height: 1fr;
    }

    #sidebar-nav {
        height: 1fr;
        margin-top: 1;
    }

    #post-screen-title, #post-screen-body {
        padding: 1 2;
    }
    """
    BINDINGS = [
        Binding("l", "logout_session", "Logout"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._last_session_signature: tuple[str, str] | None = None

    def compose(self) -> ComposeResult:
        """Render the persistent application shell."""

        with Vertical(id="app-root"):
            yield LoginView(id="login-root")
            with Vertical(id="shell-root"):
                yield Header(show_clock=True)
                yield HomeScreen()
                yield Footer()

    def on_mount(self) -> None:
        """Show login or home depending on the current session."""

        self._last_session_signature = self._session_signature()
        if self._last_session_signature is None:
            self.show_login_shell()
        else:
            self.show_authenticated_shell()
        self.set_interval(1.0, self._sync_external_session)

    def on_screen_resume(self, screen: Screen) -> None:
        """Refresh the home screen when returning from subviews."""

        if isinstance(screen, HomeScreen) and self.query_one("#shell-root", Vertical).display:
            screen.action_refresh_feed()

    def show_authenticated_shell(self) -> None:
        """Display the interactive shell after successful auth."""

        self.query_one("#login-root", LoginView).display = False
        shell_root = self.query_one("#shell-root", Vertical)
        shell_root.display = True
        self._last_session_signature = self._session_signature()
        home = self.query_one(HomeScreen)
        home.action_refresh_feed()
        home.focus()

    def show_login_shell(self) -> None:
        """Display the startup login/recovery view."""

        self.query_one("#shell-root", Vertical).display = False
        login = self.query_one("#login-root", LoginView)
        login.display = True
        self._last_session_signature = None
        login.focus_primary_input()

    def action_logout_session(self) -> None:
        """Log out from anywhere in the interactive UI."""

        session = load_session()
        if session is None:
            return

        clear_session()
        self.show_login_shell()

    def _session_signature(self) -> tuple[str, str] | None:
        """Return the current persisted session in a comparable form."""

        session = load_session()
        if session is None:
            return None
        return (session["username"], session["pubkey"])

    def _sync_external_session(self) -> None:
        """Reflect command-mode login/logout changes inside the Textual app."""

        signature = self._session_signature()
        if signature == self._last_session_signature:
            return

        if signature is None:
            self.show_login_shell()
            return

        self.show_authenticated_shell()


def launch_shell_app() -> None:
    """Launch the Textual Beep shell."""

    BeepApp().run()
