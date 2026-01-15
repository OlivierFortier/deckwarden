import os
import shutil
import tempfile
import urllib.request
import urllib.error
import zipfile

# The decky plugin module is located at decky-loader/plugin
# For easy intellisense checkout the decky-loader code repo
# and add the `decky-loader/plugin/imports` path to `python.analysis.extraPaths` in `.vscode/settings.json`
import decky # type: ignore
import asyncio
from pathlib import Path

class Plugin:
    def _password_runtime_dir(self) -> Path:
        return Path(decky.DECKY_PLUGIN_RUNTIME_DIR) / "deckwarden"

    def _password_file(self) -> Path:
        return self._password_runtime_dir() / "saved_password.txt"

    def _password_env_var(self) -> str:
        return "BW_PASSWORD"

    def _ensure_runtime_dir(self) -> None:
        runtime_dir = self._password_runtime_dir()
        runtime_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(runtime_dir, 0o700)
        except OSError:
            pass

    def _get_password_env(self) -> str | None:
        return os.environ.get(self._password_env_var())

    def _set_password_env(self, password: str) -> None:
        os.environ[self._password_env_var()] = password

    def _clear_password_env(self) -> None:
        os.environ.pop(self._password_env_var(), None)

    def _load_saved_password(self) -> None:
        env_password = self._get_password_env()
        if env_password:
            self._saved_password = env_password
            return
        password_file = self._password_file()
        if not password_file.exists():
            self._saved_password = None
            return
        try:
            saved = password_file.read_text(encoding="utf-8")
            saved = saved.rstrip("\n")
            if saved:
                self._set_password_env(saved)
                self._saved_password = saved
            else:
                self._saved_password = None
        except OSError:
            self._saved_password = None

    # A normal method. It can be called from the TypeScript side using @decky/api.
    async def add(self, left: int, right: int) -> int:
        return left + right

    async def save_password(self, password: str) -> dict:
        if not password:
            return {"success": False, "error": "Password is empty"}
        try:
            self._set_password_env(password)
            self._ensure_runtime_dir()
            password_file = self._password_file()
            fd = os.open(password_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                os.write(fd, password.encode("utf-8"))
            finally:
                os.close(fd)
            try:
                os.chmod(password_file, 0o600)
            except OSError:
                pass
            self._saved_password = password
            return {"success": True}
        except OSError as exc:
            return {"success": False, "error": f"Failed to persist password: {exc}"}

    async def clear_saved_password(self) -> dict:
        self._saved_password = None
        self._clear_password_env()
        password_file = self._password_file()
        try:
            if password_file.exists():
                password_file.unlink()
        except OSError as exc:
            return {"success": False, "error": f"Failed to remove password: {exc}"}
        return {"success": True}

    async def get_saved_password_status(self) -> dict:
        if self._saved_password is not None:
            return {"saved": True}
        if self._get_password_env() is not None:
            return {"saved": True}
        password_file = self._password_file()
        return {"saved": password_file.exists()}

    async def long_running(self):
        await asyncio.sleep(15)
        # Passing through a bunch of random data, just as an example
        await decky.emit("timer_event", "Hello from the backend!", True, 2)

    # Asyncio-compatible long-running code, executed in a task when the plugin is loaded
    async def _main(self):
        self.loop = asyncio.get_event_loop()
        self._saved_password = None
        self._load_saved_password()
        decky.logger.info("Hello World!")

    # Function called first during the unload process, utilize this to handle your plugin being stopped, but not
    # completely removed
    async def _unload(self):
        decky.logger.info("Goodnight World!")
        self._saved_password = None
        pass

    # Function called after `_unload` during uninstall, utilize this to clean up processes and other remnants of your
    # plugin that may remain on the system
    async def _uninstall(self):
        decky.logger.info("Goodbye World!")
        await self.clear_saved_password()
        pass

    async def start_timer(self):
        self.loop.create_task(self.long_running())

    # Migrations that should be performed before entering `_main()`.
    async def _migration(self):
        decky.logger.info("Migrating")
        # Here's a migration example for logs:
        # - `~/.config/decky-template/template.log` will be migrated to `decky.decky_LOG_DIR/template.log`
        decky.migrate_logs(os.path.join(decky.DECKY_USER_HOME,
                                               ".config", "decky-template", "template.log"))
        # Here's a migration example for settings:
        # - `~/homebrew/settings/template.json` is migrated to `decky.decky_SETTINGS_DIR/template.json`
        # - `~/.config/decky-template/` all files and directories under this root are migrated to `decky.decky_SETTINGS_DIR/`
        decky.migrate_settings(
            os.path.join(decky.DECKY_HOME, "settings", "template.json"),
            os.path.join(decky.DECKY_USER_HOME, ".config", "decky-template"))
        # Here's a migration example for runtime data:
        # - `~/homebrew/template/` all files and directories under this root are migrated to `decky.decky_RUNTIME_DIR/`
        # - `~/.local/share/decky-template/` all files and directories under this root are migrated to `decky.decky_RUNTIME_DIR/`
        decky.migrate_runtime(
            os.path.join(decky.DECKY_HOME, "template"),
            os.path.join(decky.DECKY_USER_HOME, ".local", "share", "decky-template"))