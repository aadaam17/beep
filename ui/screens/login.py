"""Startup login and recovery view for the Textual Beep app."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Input, Label, Static

from storage.profile import authenticate, create_user, get_user, update_user
from storage.restore import restore_from_file, restore_from_mnemonic
from storage.session import save_session


class LoginView(Static):
    """Centered login and recovery form shown before the shell."""

    DEFAULT_CSS = """
    LoginView {
        height: 1fr;
        width: 1fr;
        align: center middle;
    }

    #login-card {
        width: 68;
        max-width: 92;
        padding: 1 2;
        border: round $panel;
        background: $surface;
    }

    #login-title {
        content-align: center middle;
        text-style: bold;
        margin-bottom: 0;
    }

    .login-copy {
        margin-top: 1;
        margin-bottom: 0;
        color: $text-muted;
    }

    .login-input {
        margin-top: 0;
    }

    #login-status {
        margin-top: 1;
        min-height: 2;
    }
    """

    def compose(self) -> ComposeResult:
        """Render the startup auth form."""

        with Vertical(id="login-card"):
            yield Label("Welcome to Beep", id="login-title")
            yield Static(
                "Log in with your username and password, or recover from a mnemonic or backup.",
                classes="login-copy",
            )
            yield Input(
                placeholder="Username",
                id="login-username",
                classes="login-input",
            )
            yield Input(
                placeholder="Password / local password / backup password",
                password=True,
                id="login-password",
                classes="login-input",
            )
            yield Static(
                "Press Enter in the password field to log in or create the account.",
                classes="login-copy",
            )
            yield Static(
                "Mnemonic recovery",
                classes="login-copy",
            )
            yield Input(
                placeholder="Mnemonic seed phrase",
                id="login-mnemonic",
                classes="login-input",
            )
            yield Static(
                "Backup restore",
                classes="login-copy",
            )
            yield Input(
                placeholder="Backup file path",
                id="login-backup-path",
                classes="login-input",
            )
            yield Static("", id="login-status")

    def on_mount(self) -> None:
        """Focus the username field when the view appears."""

        self.focus_primary_input()

    def focus_primary_input(self) -> None:
        """Focus the username field for quick login."""

        self.query_one("#login-username", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Map Enter on each field to the matching auth action."""

        if event.input.id == "login-username":
            self.query_one("#login-password", Input).focus()
            return
        if event.input.id == "login-password":
            self._submit_login_or_register()
            return
        if event.input.id == "login-mnemonic":
            self._submit_mnemonic_recovery()
            return
        if event.input.id == "login-backup-path":
            self._submit_backup_recovery()

    def _submit_login_or_register(self) -> None:
        """Authenticate an existing user or create a new one on first use."""

        username = self._input_value("login-username").lower()
        password = self._input_value("login-password")
        if not username or not password:
            self._set_status("Enter both username and password to log in.")
            return

        try:
            existing_user = get_user(username)
            if existing_user is None:
                user = create_user(username, password)
                save_session(user["username"], user["pubkey"])
                self._set_status(f"Account created for @{user['username']}.")
            else:
                user = authenticate(username, password)
                user = update_user(user["username"], user)
                save_session(user["username"], user["pubkey"])
                self._set_status(f"Logged in as @{user['username']}.")
        except Exception as exc:
            self._set_status(f"Login failed: {exc}")
            return

        self._enter_shell()

    def _submit_mnemonic_recovery(self) -> None:
        """Recover an account from mnemonic seed."""

        mnemonic = self._input_value("login-mnemonic")
        password = self._input_value("login-password")
        username = self._input_value("login-username") or None
        if not mnemonic:
            self._set_status("Enter a mnemonic seed phrase first.")
            return
        if not password:
            self._set_status("Enter a local password to store the recovered account.")
            return

        try:
            result = restore_from_mnemonic(
                mnemonic,
                local_password=password,
                username=username,
                auto_login=True,
            )
        except Exception as exc:
            self._set_status(f"Mnemonic recovery failed: {exc}")
            return

        restored_username = str(result["username"])
        self._set_status(f"Recovered @{restored_username} from mnemonic.")
        self._enter_shell()

    def _submit_backup_recovery(self) -> None:
        """Restore an account from an encrypted backup file."""

        path = self._input_value("login-backup-path")
        password = self._input_value("login-password")
        if not path:
            self._set_status("Enter the backup file path first.")
            return
        if not password:
            self._set_status("Enter the backup password first.")
            return

        try:
            result = restore_from_file(path, password, auto_login=True)
        except Exception as exc:
            self._set_status(f"Backup restore failed: {exc}")
            return

        restored_username = str(result["username"])
        self._set_status(f"Restored @{restored_username} from backup.")
        self._enter_shell()

    def _input_value(self, input_id: str) -> str:
        """Return a trimmed input value."""

        return self.query_one(f"#{input_id}", Input).value.strip()

    def _set_status(self, message: str) -> None:
        """Render a small status/error message."""

        self.query_one("#login-status", Static).update(message)

    def _enter_shell(self) -> None:
        """Switch from the login view into the authenticated shell."""

        if hasattr(self.app, "show_authenticated_shell"):
            self.app.show_authenticated_shell()
