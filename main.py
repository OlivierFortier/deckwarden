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

    async def _run_bw(
        self,
        args: list[str],
        *,
        session: str | None = None,
        input_text: str | None = None,
        extra_env: dict[str, str] | None = None,
        pretty: bool = False,
        raw: bool = False,
        response: bool = False,
        quiet: bool = False,
        nointeraction: bool = False,
    ) -> dict:
        install_result = await self.install_bw_cli()
        if not install_result.get("success"):
            return install_result

        bw_path = install_result.get("path")
        if not bw_path:
            return {"success": False, "error": "Bitwarden CLI path not available."}

        cmd = [bw_path, *args]
        if session:
            cmd.extend(["--session", session])
        if pretty:
            cmd.append("--pretty")
        if raw:
            cmd.append("--raw")
        if response:
            cmd.append("--response")
        if quiet:
            cmd.append("--quiet")
        if nointeraction:
            cmd.append("--nointeraction")

        env = None
        if extra_env:
            env = os.environ.copy()
            env.update(extra_env)

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE if input_text is not None else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            stdout, stderr = await process.communicate(
                input_text.encode() if input_text is not None else None
            )
            return {
                "success": process.returncode == 0,
                "returncode": process.returncode,
                "stdout": stdout.decode(errors="replace"),
                "stderr": stderr.decode(errors="replace"),
            }
        except Exception as exc:
            decky.logger.error(f"Failed to run bw command: {exc}")
            return {"success": False, "error": str(exc)}

    async def bw_status(
        self,
        session: str | None = None,
        *,
        pretty: bool = False,
        raw: bool = False,
        response: bool = False,
    ) -> dict:
        return await self._run_bw(
            ["status"],
            session=session,
            pretty=pretty,
            raw=raw,
            response=response,
        )

    async def bw_login(
        self,
        email: str | None = None,
        password: str | None = None,
        *,
        method: int | None = None,
        code: str | None = None,
        apikey: bool = False,
        sso: bool = False,
        nointeraction: bool = False,
    ) -> dict:
        args = ["login"]
        if apikey:
            args.append("--apikey")
        if sso:
            args.append("--sso")
        if email is not None:
            args.append(email)
        if password is not None:
            args.append(password)
        if method is not None:
            args.extend(["--method", str(method)])
        if code is not None:
            args.extend(["--code", code])
        return await self._run_bw(args, nointeraction=nointeraction)

    async def bw_unlock(
        self,
        *,
        session: str | None = None,
        passwordenv: str | None = None,
        passwordfile: str | None = None,
        nointeraction: bool = False,
    ) -> dict:
        args = ["unlock"]
        if passwordenv:
            args.extend(["--passwordenv", passwordenv])
        if passwordfile:
            args.extend(["--passwordfile", passwordfile])
        return await self._run_bw(args, session=session, nointeraction=nointeraction)

    async def bw_lock(self) -> dict:
        return await self._run_bw(["lock"], nointeraction=True)

    async def bw_logout(self) -> dict:
        return await self._run_bw(["logout"], nointeraction=True)

    async def bw_sync(self, *, last: bool = False) -> dict:
        args = ["sync"]
        if last:
            args.append("--last")
        return await self._run_bw(args, nointeraction=True)

    async def bw_list(
        self,
        entity: str,
        *,
        session: str | None = None,
        search: str | None = None,
        url: str | None = None,
        folderid: str | None = None,
        collectionid: str | None = None,
        organizationid: str | None = None,
        trash: bool | None = None,
    ) -> dict:
        args = ["list", entity]
        if search:
            args.extend(["--search", search])
        if url:
            args.extend(["--url", url])
        if folderid:
            args.extend(["--folderid", folderid])
        if collectionid:
            args.extend(["--collectionid", collectionid])
        if organizationid:
            args.extend(["--organizationid", organizationid])
        if trash is not None:
            args.extend(["--trash", str(trash).lower()])
        return await self._run_bw(args, session=session)

    async def bw_get(
        self,
        entity: str,
        identifier: str,
        *,
        session: str | None = None,
        organizationid: str | None = None,
        output: str | None = None,
    ) -> dict:
        args = ["get", entity, identifier]
        if organizationid:
            args.extend(["--organizationid", organizationid])
        if output:
            args.extend(["--output", output])
        return await self._run_bw(args, session=session)

    async def bw_create(
        self,
        entity: str,
        *,
        session: str | None = None,
        encoded_json: str | None = None,
        file: str | None = None,
        itemid: str | None = None,
        organizationid: str | None = None,
    ) -> dict:
        args = ["create", entity]
        if encoded_json is not None:
            args.append(encoded_json)
        if file:
            args.extend(["--file", file])
        if itemid:
            args.extend(["--itemid", itemid])
        if organizationid:
            args.extend(["--organizationid", organizationid])
        return await self._run_bw(args, session=session)

    async def bw_edit(
        self,
        entity: str,
        identifier: str,
        *,
        session: str | None = None,
        encoded_json: str | None = None,
        organizationid: str | None = None,
    ) -> dict:
        args = ["edit", entity, identifier]
        if encoded_json is not None:
            args.append(encoded_json)
        if organizationid:
            args.extend(["--organizationid", organizationid])
        return await self._run_bw(args, session=session)

    async def bw_delete(
        self,
        entity: str,
        identifier: str,
        *,
        session: str | None = None,
        permanent: bool = False,
        organizationid: str | None = None,
    ) -> dict:
        args = ["delete", entity, identifier]
        if permanent:
            args.append("--permanent")
        if organizationid:
            args.extend(["--organizationid", organizationid])
        return await self._run_bw(args, session=session)

    async def bw_restore(
        self,
        entity: str,
        identifier: str,
        *,
        session: str | None = None,
    ) -> dict:
        args = ["restore", entity, identifier]
        return await self._run_bw(args, session=session)

    async def bw_send(
        self,
        *,
        session: str | None = None,
        name: str | None = None,
        delete_in_days: int | None = None,
        hidden_text: str | None = None,
        file_path: str | None = None,
        password: str | None = None,
    ) -> dict:
        args = ["send"]
        if name:
            args.extend(["-n", name])
        if delete_in_days is not None:
            args.extend(["-d", str(delete_in_days)])
        if hidden_text:
            args.extend(["--hidden", hidden_text])
        if file_path:
            args.extend(["-f", file_path])
        if password:
            args.extend(["--password", password])
        return await self._run_bw(args, session=session)

    async def bw_receive(
        self,
        send_url: str,
        *,
        session: str | None = None,
        password: str | None = None,
    ) -> dict:
        args = ["receive", send_url]
        if password:
            args.extend(["--password", password])
        return await self._run_bw(args, session=session)

    async def bw_move(
        self,
        itemid: str,
        organizationid: str,
        *,
        session: str | None = None,
        encoded_json: str | None = None,
    ) -> dict:
        args = ["move", itemid, organizationid]
        if encoded_json is not None:
            args.append(encoded_json)
        return await self._run_bw(args, session=session)

    async def bw_confirm_org_member(
        self,
        member_id: str,
        organizationid: str,
        *,
        session: str | None = None,
    ) -> dict:
        args = ["confirm", "org-member", member_id, "--organizationid", organizationid]
        return await self._run_bw(args, session=session)

    async def bw_device_approval(
        self,
        action: str,
        *,
        session: str | None = None,
        organizationid: str | None = None,
        request_id: str | None = None,
    ) -> dict:
        args = ["device-approval", action]
        if organizationid:
            args.extend(["--organizationid", organizationid])
        if request_id:
            args.append(request_id)
        return await self._run_bw(args, session=session)

    async def bw_config_server(
        self,
        *,
        server: str | None = None,
        web_vault: str | None = None,
        api: str | None = None,
        identity: str | None = None,
        icons: str | None = None,
        notifications: str | None = None,
        events: str | None = None,
        key_connector: str | None = None,
    ) -> dict:
        args = ["config", "server"]
        if server:
            args.append(server)
        else:
            if web_vault:
                args.extend(["--web-vault", web_vault])
            if api:
                args.extend(["--api", api])
            if identity:
                args.extend(["--identity", identity])
            if icons:
                args.extend(["--icons", icons])
            if notifications:
                args.extend(["--notifications", notifications])
            if events:
                args.extend(["--events", events])
            if key_connector:
                args.extend(["--key-connector", key_connector])
        return await self._run_bw(args)

    async def bw_generate(
        self,
        *,
        session: str | None = None,
        lowercase: bool = False,
        uppercase: bool = False,
        number: bool = False,
        special: bool = False,
        length: int | None = None,
        passphrase: bool = False,
        separator: str | None = None,
        words: int | None = None,
        capitalize: bool = False,
        include_number: bool = False,
    ) -> dict:
        args = ["generate"]
        if lowercase:
            args.append("--lowercase")
        if uppercase:
            args.append("--uppercase")
        if number:
            args.append("--number")
        if special:
            args.append("--special")
        if length is not None:
            args.extend(["--length", str(length)])
        if passphrase:
            args.append("--passphrase")
        if separator:
            args.extend(["--separator", separator])
        if words is not None:
            args.extend(["--words", str(words)])
        if capitalize:
            args.append("--capitalize")
        if include_number:
            args.append("--includeNumber")
        return await self._run_bw(args, session=session)

    async def bw_export(
        self,
        *,
        session: str | None = None,
        output: str | None = None,
        format: str | None = None,
        password: str | None = None,
        organizationid: str | None = None,
        raw: bool = False,
    ) -> dict:
        args = ["export"]
        if output:
            args.extend(["--output", output])
        if format:
            args.extend(["--format", format])
        if password:
            args.extend(["--password", password])
        if organizationid:
            args.extend(["--organizationid", organizationid])
        return await self._run_bw(args, session=session, raw=raw)

    async def bw_import(
        self,
        format: str,
        path: str,
        *,
        session: str | None = None,
        organizationid: str | None = None,
    ) -> dict:
        args = ["import"]
        if organizationid:
            args.extend(["--organizationid", organizationid])
        args.extend([format, path])
        return await self._run_bw(args, session=session)

    async def bw_update(self) -> dict:
        return await self._run_bw(["update"], nointeraction=True)

    async def bw_encode(self, input_text: str) -> dict:
        return await self._run_bw(["encode"], input_text=input_text)

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
            await asyncio.sleep(0.5)
            if self.bw_serve_process.returncode is not None:
                stdout, stderr = await self.bw_serve_process.communicate()
                error_text = stderr.decode(errors="replace").strip()
                output_text = stdout.decode(errors="replace").strip()
                detail = error_text or output_text or "bw serve exited early"
                decky.logger.error(f"bw serve exited early: {detail}")
                return {"success": False, "error": detail}
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

    async def bw_http_request(
        self,
        method: str,
        hostname: str,
        port: int,
        path: str,
        body: str | None = None,
    ) -> dict:
        if port <= 0:
            return {"success": False, "error": "Port must be a positive integer."}

        if not path.startswith("/"):
            path = f"/{path}"

        url = f"http://{hostname}:{port}{path}"
        payload = body.encode("utf-8") if body and body.strip() else None
        headers = {}
        if payload is not None:
            headers["Content-Type"] = "application/json"

        request = urllib.request.Request(url, data=payload, method=method, headers=headers)

        def _perform_request():
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, response.reason, response.read().decode(
                    "utf-8", errors="replace"
                )

        try:
            status, reason, text = await asyncio.to_thread(_perform_request)
            return {
                "success": True,
                "status": status,
                "statusText": reason,
                "body": text,
                "url": url,
            }
        except urllib.error.HTTPError as exc:
            try:
                text = exc.read().decode("utf-8", errors="replace")
            except Exception:
                text = ""
            return {
                "success": False,
                "status": exc.code,
                "statusText": exc.reason,
                "body": text,
                "error": str(exc),
                "url": url,
            }
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            return {"success": False, "error": str(reason), "url": url}
        except Exception as exc:
            return {"success": False, "error": str(exc), "url": url}
