import os
import shutil
import tempfile
import urllib.request
import zipfile

# The decky plugin module is located at decky-loader/plugin
# For easy intellisense checkout the decky-loader code repo
# and add the `decky-loader/plugin/imports` path to `python.analysis.extraPaths` in `.vscode/settings.json`
import decky # type: ignore
import asyncio
from pathlib import Path

class Plugin:
    # A normal method. It can be called from the TypeScript side using @decky/api.
    async def add(self, left: int, right: int) -> int:
        return left + right

    async def long_running(self):
        await asyncio.sleep(15)
        # Passing through a bunch of random data, just as an example
        await decky.emit("timer_event", "Hello from the backend!", True, 2)

    # Asyncio-compatible long-running code, executed in a task when the plugin is loaded
    async def _main(self):
        self.loop = asyncio.get_event_loop()
        decky.logger.info("Hello World!")

    # Function called first during the unload process, utilize this to handle your plugin being stopped, but not
    # completely removed
    async def _unload(self):
        decky.logger.info("Goodnight World!")
        pass

    # Function called after `_unload` during uninstall, utilize this to clean up processes and other remnants of your
    # plugin that may remain on the system
    async def _uninstall(self):
        decky.logger.info("Goodbye World!")
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

    async def install_bw_cli(self) -> dict:
        defaults_path = Path(decky.DECKY_PLUGIN_DIR) / "defaults" / "bw"
        bundled_path = Path(decky.DECKY_PLUGIN_DIR) / "bin" / "bw"
        runtime_path = Path(decky.DECKY_PLUGIN_RUNTIME_DIR) / "bin" / "bw"
        download_url = "https://github.com/bitwarden/clients/releases/download/cli-v2025.12.1/bw-oss-linux-2025.12.1.zip"
        archive_name = Path(download_url).name
        defaults_archive = Path(decky.DECKY_PLUGIN_DIR) / "defaults" / archive_name
        bundled_archive = Path(decky.DECKY_PLUGIN_DIR) / "bin" / archive_name
        runtime_archive = Path(decky.DECKY_PLUGIN_RUNTIME_DIR) / "bin" / archive_name

        try:
            decky.logger.info("Starting install_bw_cli")
            if runtime_path.exists():
                bw_path = runtime_path
            elif defaults_path.exists():
                bw_path = defaults_path
            elif bundled_path.exists():
                bw_path = bundled_path
            else:
                bw_path = runtime_path

                def _extract_archive(archive_path: Path, target_path: Path):
                    decky.logger.info(f"Extracting bw from archive: {archive_path}")
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    with zipfile.ZipFile(archive_path) as zip_file:
                        members = [
                            member
                            for member in zip_file.infolist()
                            if not member.is_dir() and Path(member.filename).name == "bw"
                        ]
                        if not members:
                            raise FileNotFoundError("bw binary not found in archive.")

                        member = members[0]
                        with zip_file.open(member) as source, open(target_path, "wb") as dest:
                            shutil.copyfileobj(source, dest)

                def _download_archive(archive_path: Path):
                    decky.logger.info(f"Downloading bw archive to: {archive_path}")
                    archive_path.parent.mkdir(parents=True, exist_ok=True)
                    urllib.request.urlretrieve(download_url, archive_path)

                archive_path = None
                for candidate in (defaults_archive, bundled_archive, runtime_archive):
                    if candidate.exists():
                        archive_path = candidate
                        break

                if archive_path is None:
                    await asyncio.to_thread(_download_archive, runtime_archive)
                    archive_path = runtime_archive

                await asyncio.to_thread(_extract_archive, archive_path, bw_path)

            try:
                bw_path.chmod(0o755)
            except PermissionError:
                if bw_path != runtime_path:
                    runtime_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(bw_path, runtime_path)
                    runtime_path.chmod(0o755)
                    bw_path = runtime_path
                else:
                    raise

            decky.logger.info(f"bw CLI ready at {bw_path}")
            return {"success": True, "path": str(bw_path)}
        except Exception as exc:
            decky.logger.error(f"Failed to locate bundled Bitwarden CLI: {exc}")
            return {"success": False, "error": str(exc)}

    async def bw_serve(
        self,
        port: int = 8087,
        hostname: str = "localhost",
        disable_origin_protection: bool = False,
    ) -> dict:
        """
        Start the Bitwarden CLI local API server.

        Based on https://bitwarden.com/help/cli/#serve:
        bw serve --port <port> --hostname <hostname>
        Optional: --disable-origin-protection
        """
        if port <= 0:
            return {"success": False, "error": "Port must be a positive integer."}

        if getattr(self, "bw_serve_process", None) and self.bw_serve_process.returncode is None:
            return {
                "success": True,
                "status": "already_running",
                "pid": self.bw_serve_process.pid,
            }

        install_result = await self.install_bw_cli()
        if not install_result.get("success"):
            return install_result

        bw_path = install_result.get("path")
        if not bw_path:
            return {"success": False, "error": "Bitwarden CLI path not available."}

        args = [bw_path, "serve", "--port", str(port), "--hostname", hostname]
        if disable_origin_protection:
            args.append("--disable-origin-protection")

        try:
            self.bw_serve_process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            decky.logger.info(
                f"Started bw serve (pid={self.bw_serve_process.pid}) on {hostname}:{port}"
            )
            return {
                "success": True,
                "pid": self.bw_serve_process.pid,
                "port": port,
                "hostname": hostname,
                "disable_origin_protection": disable_origin_protection,
            }
        except Exception as exc:
            decky.logger.error(f"Failed to start bw serve: {exc}")
            return {"success": False, "error": str(exc)}
