import os
import shutil
import tempfile
import urllib.request
import urllib.error
import zipfile
import json
import re
import subprocess
import hashlib
import base64

# The decky plugin module is located at decky-loader/plugin
# For easy intellisense checkout the decky-loader code repo
# and add the `decky-loader/plugin/imports` path to `python.analysis.extraPaths` in `.vscode/settings.json`
import decky # type: ignore
import asyncio
from pathlib import Path

class Plugin:
    def _bw_binary_path(self) -> Path:
        return Path(decky.DECKY_PLUGIN_DIR) / "bin" / "bw"

    def _password_runtime_dir(self) -> Path:
        return Path(decky.DECKY_PLUGIN_RUNTIME_DIR) / "deckwarden"

    def _email_settings_dir(self) -> Path:
        return Path(decky.DECKY_PLUGIN_SETTINGS_DIR) / "deckwarden"

    def _password_file(self) -> Path:
        return self._password_runtime_dir() / "saved_password.txt"

    def _email_file(self) -> Path:
        return self._email_settings_dir() / "saved_email.txt"

    def _password_env_var(self) -> str:
        return "BW_PASSWORD"

    def _session_file(self) -> Path:
        return self._password_runtime_dir() / "bw_session.txt"

    def _session_env_var(self) -> str:
        return "BW_SESSION"

    def _ensure_runtime_dir(self) -> None:
        runtime_dir = self._password_runtime_dir()
        runtime_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(runtime_dir, 0o700)
        except OSError:
            pass

    def _ensure_settings_dir(self) -> None:
        settings_dir = self._email_settings_dir()
        settings_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(settings_dir, 0o700)
        except OSError:
            pass

    def _get_password_env(self) -> str | None:
        return os.environ.get(self._password_env_var())

    def _set_password_env(self, password: str) -> None:
        os.environ[self._password_env_var()] = password

    def _clear_password_env(self) -> None:
        os.environ.pop(self._password_env_var(), None)

    def _get_session_env(self) -> str | None:
        return os.environ.get(self._session_env_var())

    def _set_session_env(self, session: str) -> None:
        os.environ[self._session_env_var()] = session

    def _clear_session_env(self) -> None:
        os.environ.pop(self._session_env_var(), None)

    def _get_encryption_key(self) -> str:
        """Generate deterministic encryption key from plugin directory and user."""
        base = f"{decky.DECKY_PLUGIN_DIR}:{decky.DECKY_USER}"
        key_hash = hashlib.sha256(base.encode()).digest()
        return base64.b64encode(key_hash).decode('ascii')[:32]

    def _encrypt_password(self, password: str) -> bytes:
        """Encrypt password using OpenSSL AES-256-CBC."""
        try:
            key = self._get_encryption_key()
            result = subprocess.run(
                ['openssl', 'enc', '-aes-256-cbc', '-salt', '-pbkdf2', '-a', '-pass', f'pass:{key}'],
                input=password.encode('utf-8'),
                capture_output=True,
                check=True
            )
            return result.stdout
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            decky.logger.error(f"Encryption failed: {e}")
            # Fallback to base64 encoding if openssl not available
            return base64.b64encode(password.encode('utf-8'))

    def _decrypt_password(self, encrypted_data: bytes) -> str | None:
        """Decrypt password using OpenSSL AES-256-CBC."""
        try:
            key = self._get_encryption_key()
            result = subprocess.run(
                ['openssl', 'enc', '-aes-256-cbc', '-d', '-pbkdf2', '-a', '-pass', f'pass:{key}'],
                input=encrypted_data,
                capture_output=True,
                check=True
            )
            return result.stdout.decode('utf-8')
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            decky.logger.error(f"Decryption failed: {e}")
            # Fallback to base64 decoding if openssl not available
            try:
                return base64.b64decode(encrypted_data).decode('utf-8')
            except Exception:
                return None

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
            encrypted_data = password_file.read_bytes()
            if encrypted_data:
                decrypted = self._decrypt_password(encrypted_data)
                if decrypted:
                    self._set_password_env(decrypted)
                    self._saved_password = decrypted
                else:
                    self._saved_password = None
            else:
                self._saved_password = None
        except OSError:
            self._saved_password = None

    def _load_saved_email(self) -> None:
        email_file = self._email_file()
        if not email_file.exists():
            self._saved_email = None
            return
        try:
            saved = email_file.read_text(encoding="utf-8").strip()
            self._saved_email = saved or None
        except OSError:
            self._saved_email = None

    def _load_saved_session(self) -> None:
        env_session = self._get_session_env()
        if env_session:
            self._session = env_session
            return
        session_file = self._session_file()
        if not session_file.exists():
            self._session = None
            return
        try:
            saved = session_file.read_text(encoding="utf-8").strip()
            if saved:
                self._set_session_env(saved)
                self._session = saved
            else:
                self._session = None
        except OSError:
            self._session = None

    def _save_session(self, session: str) -> None:
        self._ensure_runtime_dir()
        session_file = self._session_file()
        fd = os.open(session_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, session.encode("utf-8"))
        finally:
            os.close(fd)
        try:
            os.chmod(session_file, 0o600)
        except OSError:
            pass

    def _clear_saved_session(self) -> None:
        self._session = None
        self._clear_session_env()
        session_file = self._session_file()
        try:
            if session_file.exists():
                session_file.unlink()
        except OSError:
            pass

    def _get_cached_session(self) -> str | None:
        if self._session:
            return self._session
        env_session = self._get_session_env()
        if env_session:
            self._session = env_session
            return env_session
        session_file = self._session_file()
        if session_file.exists():
            try:
                saved = session_file.read_text(encoding="utf-8").strip()
                if saved:
                    self._set_session_env(saved)
                    self._session = saved
                    return saved
            except OSError:
                return None
        return None

    def _parse_session_from_output(self, output: str) -> str | None:
        if not output:
            return None
        match = re.search(r"BW_SESSION=\"?([A-Za-z0-9+/=]+)\"?", output)
        if match:
            return match.group(1)
        output = output.strip()
        if output and all(ch.isalnum() or ch in "+/=" for ch in output):
            return output
        return None

    async def _run_bw(
        self,
        args: list[str],
        input_text: str | None = None,
        session: str | None = None,
        env: dict[str, str] | None = None,
    ) -> dict:
        bw_path = self._bw_binary_path()
        if not bw_path.exists() or not bw_path.is_file():
            return {"success": False, "error": f"Bitwarden CLI not found at {bw_path}"}

        run_env = os.environ.copy()
        if env:
            run_env.update(env)
        if session:
            run_env[self._session_env_var()] = session

        process = await asyncio.create_subprocess_exec(
            str(bw_path),
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE if input_text is not None else None,
            env=run_env,
        )
        stdout, stderr = await process.communicate(
            input_text.encode("utf-8") if input_text is not None else None
        )
        out_text = stdout.decode("utf-8", errors="replace") if stdout else ""
        err_text = stderr.decode("utf-8", errors="replace") if stderr else ""
        if process.returncode != 0:
            return {
                "success": False,
                "error": err_text.strip() or out_text.strip() or "Bitwarden CLI error",
                "code": process.returncode,
            }
        return {"success": True, "stdout": out_text, "stderr": err_text}

    # A normal method. It can be called from the TypeScript side using @decky/api.
    async def add(self, left: int, right: int) -> int:
        return left + right

    async def bw_status(self) -> dict:
        result = await self._run_bw(["status"])
        if not result.get("success"):
            return result
        try:
            data = json.loads(result.get("stdout", "") or "{}")
        except json.JSONDecodeError:
            return {"success": False, "error": "Failed to parse bw status output"}
        return {"success": True, "status": data}

    async def bw_sync(self) -> dict:
        session = self._get_cached_session()
        if not session:
            return {"success": False, "error": "No active session. Please login."}
        result = await self._run_bw(["sync"], session=session)
        if not result.get("success"):
            return result
        return {"success": True, "output": result.get("stdout", "").strip()}

    async def bw_list_items(self, search: str) -> dict:
        search = (search or "").strip()
        if not search:
            return {"success": True, "items": []}
        session = self._get_cached_session()
        if not session:
            return {"success": False, "error": "No active session. Please login."}
        result = await self._run_bw(["list", "items", "--search", search], session=session)
        if not result.get("success"):
            return result
        try:
            items = json.loads(result.get("stdout", "") or "[]")
        except json.JSONDecodeError:
            return {"success": False, "error": "Failed to parse bw list output"}
        summaries = []
        for item in items or []:
            if not isinstance(item, dict):
                continue
            item_id = item.get("id")
            name = item.get("name")
            if item_id and name:
                summaries.append({"id": item_id, "name": name})
        return {"success": True, "items": summaries}

    async def bw_get_item(self, item_id: str) -> dict:
        item_id = (item_id or "").strip()
        if not item_id:
            return {"success": False, "error": "Missing item id"}
        session = self._get_cached_session()
        if not session:
            return {"success": False, "error": "No active session. Please login."}
        result = await self._run_bw(["get", "item", item_id], session=session)
        if not result.get("success"):
            return result
        try:
            item = json.loads(result.get("stdout", "") or "{}")
        except json.JSONDecodeError:
            return {"success": False, "error": "Failed to parse bw get item output"}

        login = item.get("login") or {}
        uris = []
        for uri in (login.get("uris") or []):
            if isinstance(uri, dict) and uri.get("uri"):
                uris.append(uri.get("uri"))

        totp_code = None
        totp_result = await self._run_bw(["get", "totp", item_id], session=session)
        if totp_result.get("success"):
            totp_code = (totp_result.get("stdout", "") or "").strip() or None

        return {
            "success": True,
            "item": {
                "id": item.get("id"),
                "name": item.get("name"),
                "username": login.get("username"),
                "password": login.get("password"),
                "totp": totp_code,
                "uris": uris,
            },
        }

    async def bw_config_server(self, server: str) -> dict:
        server_value = (server or "").strip().lower()
        if server_value == "us":
            server_url = "https://vault.bitwarden.com"
        elif server_value == "eu":
            server_url = "https://vault.bitwarden.eu"
        else:
            return {"success": False, "error": "Server must be 'us' or 'eu'"}
        result = await self._run_bw(["config", "server", server_url])
        if not result.get("success"):
            return result
        return {"success": True, "server": server_url}

    async def login_and_sync(self, email: str, password: str, server: str, totp_code: str | None = None) -> dict:
        email = (email or "").strip()
        password = (password or "").strip()
        totp_code = (totp_code or "").strip()

        effective_email = email or self._saved_email

        config_result = await self.bw_config_server(server)
        if not config_result.get("success"):
            return config_result

        effective_password = password or self._saved_password or self._get_password_env()
        if not effective_password:
            return {"success": False, "error": "Missing password"}

        if effective_password:
            self._set_password_env(effective_password)

        status_result = await self._run_bw(["status"])
        status = {}
        if status_result.get("success"):
            try:
                status = json.loads(status_result.get("stdout", "") or "{}")
            except json.JSONDecodeError:
                status = {}

        if status.get("status") == "unauthenticated":
            if not effective_email:
                return {"success": False, "error": "Email required for login"}
            login_args = ["login", effective_email, effective_password]
            if totp_code:
                login_args.extend(["--method", "0", "--code", totp_code])
            login_result = await self._run_bw(login_args)
            if not login_result.get("success"):
                return login_result

        unlock_result = await self._run_bw(["unlock", "--passwordenv", "BW_PASSWORD"], session=None)
        if not unlock_result.get("success"):
            return unlock_result

        session = self._parse_session_from_output(unlock_result.get("stdout", "") or "")
        if not session:
            return {"success": False, "error": "Failed to retrieve session key"}

        self._session = session
        self._set_session_env(session)
        self._save_session(session)

        sync_result = await self._run_bw(["sync"], session=session)
        if not sync_result.get("success"):
            return sync_result

        return {"success": True}

    async def bw_lock(self) -> dict:
        session = self._get_cached_session()
        result = await self._run_bw(["lock"], session=session)
        self._clear_saved_session()
        if not result.get("success"):
            return result
        return {"success": True}

    async def bw_logout(self) -> dict:
        session = self._get_cached_session()
        result = await self._run_bw(["logout"], session=session)
        self._clear_saved_session()
        await self.clear_saved_password()
        await self.clear_saved_email()
        if not result.get("success"):
            return result
        return {"success": True}

    async def extract_bw_zip(self) -> dict:
        zip_name = "bw-oss-linux-2025.12.1.zip"
        bin_dir = Path(decky.DECKY_PLUGIN_DIR) / "bin"
        zip_path = bin_dir / zip_name
        if not zip_path.exists():
            return {"success": False, "error": f"Zip not found: {zip_path}"}
        try:
            with zipfile.ZipFile(zip_path) as archive:
                members = archive.infolist()
                for member in members:
                    member_path = Path(member.filename)
                    if member_path.is_absolute() or ".." in member_path.parts:
                        return {
                            "success": False,
                            "error": f"Unsafe path in zip: {member.filename}",
                        }
                for member in members:
                    dest_path = bin_dir / member.filename
                    if member.is_dir():
                        if dest_path.exists() and dest_path.is_file():
                            dest_path.unlink()
                        dest_path.mkdir(parents=True, exist_ok=True)
                        continue
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    if dest_path.exists():
                        if dest_path.is_dir():
                            shutil.rmtree(dest_path)
                        else:
                            dest_path.unlink()
                    with archive.open(member) as src, open(dest_path, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    if dest_path.name == "bw":
                        try:
                            os.chmod(dest_path, 0o755)
                        except OSError:
                            pass
            bw_path = bin_dir / "bw"
            if not bw_path.exists() or not bw_path.is_file():
                return {"success": False, "error": "Extracted zip but bw binary is missing"}
            return {"success": True}
        except zipfile.BadZipFile:
            return {"success": False, "error": "Invalid zip file"}
        except OSError as exc:
            return {"success": False, "error": f"Failed to extract zip: {exc}"}

    async def save_password(self, password: str) -> dict:
        if not password:
            return {"success": False, "error": "Password is empty"}
        try:
            self._set_password_env(password)
            self._ensure_runtime_dir()
            password_file = self._password_file()
            encrypted_data = self._encrypt_password(password)
            fd = os.open(password_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                os.write(fd, encrypted_data)
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

    async def save_email(self, email: str) -> dict:
        email = (email or "").strip()
        if not email:
            return {"success": False, "error": "Email is empty"}
        try:
            self._ensure_settings_dir()
            email_file = self._email_file()
            fd = os.open(email_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                os.write(fd, email.encode("utf-8"))
            finally:
                os.close(fd)
            try:
                os.chmod(email_file, 0o600)
            except OSError:
                pass
            self._saved_email = email
            return {"success": True}
        except OSError as exc:
            return {"success": False, "error": f"Failed to persist email: {exc}"}

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

    async def clear_saved_email(self) -> dict:
        self._saved_email = None
        email_file = self._email_file()
        try:
            if email_file.exists():
                email_file.unlink()
        except OSError as exc:
            return {"success": False, "error": f"Failed to remove email: {exc}"}
        return {"success": True}

    async def get_saved_password_status(self) -> dict:
        if self._saved_password is not None:
            return {"saved": True, "password": self._saved_password}
        env_password = self._get_password_env()
        if env_password is not None:
            return {"saved": True, "password": env_password}
        password_file = self._password_file()
        if password_file.exists():
            try:
                encrypted_data = password_file.read_bytes()
                decrypted = self._decrypt_password(encrypted_data)
                if decrypted:
                    return {"saved": True, "password": decrypted}
            except OSError:
                pass
        return {"saved": False, "password": None}

    async def get_saved_email_status(self) -> dict:
        if self._saved_email is not None:
            return {"saved": True, "email": self._saved_email}
        email_file = self._email_file()
        if email_file.exists():
            try:
                saved = email_file.read_text(encoding="utf-8").strip()
                return {"saved": bool(saved), "email": saved or None}
            except OSError:
                return {"saved": False, "email": None}
        return {"saved": False, "email": None}

    async def long_running(self):
        await asyncio.sleep(15)
        # Passing through a bunch of random data, just as an example
        await decky.emit("timer_event", "Hello from the backend!", True, 2)

    # Asyncio-compatible long-running code, executed in a task when the plugin is loaded
    async def _main(self):
        self.loop = asyncio.get_event_loop()
        self._saved_password = None
        self._saved_email = None
        self._session = None
        self._load_saved_password()
        self._load_saved_email()
        self._load_saved_session()
        decky.logger.info("Hello World!")

    # Function called first during the unload process, utilize this to handle your plugin being stopped, but not
    # completely removed
    async def _unload(self):
        decky.logger.info("Goodnight World!")
        self._saved_password = None
        await self._run_bw(["lock"], session=self._get_cached_session())
        self._clear_saved_session()
        pass

    # Function called after `_unload` during uninstall, utilize this to clean up processes and other remnants of your
    # plugin that may remain on the system
    async def _uninstall(self):
        decky.logger.info("Goodbye World!")
        await self.clear_saved_password()
        await self.clear_saved_email()
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