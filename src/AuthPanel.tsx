import { useEffect, useState } from "react";
import { callable, toaster } from "@decky/api";
import { ButtonItem, Field, TextField, ToggleField, ConfirmModal, showModal } from "@decky/ui";
import { copyWithVerification } from "./utils/clipboard";

const getSavedPasswordStatus = callable<[], { saved: boolean; password?: string | null }>("get_saved_password_status");
const savePassword = callable<[password: string], { success: boolean; error?: string }>("save_password");
const clearSavedPassword = callable<[], { success: boolean; error?: string }>("clear_saved_password");
const getSavedEmailStatus = callable<[], { saved: boolean; email?: string | null }>("get_saved_email_status");
const saveEmail = callable<[email: string], { success: boolean; error?: string }>("save_email");
const clearSavedEmail = callable<[], { success: boolean; error?: string }>("clear_saved_email");
const loginAndSync = callable<
  [email: string, password: string, server: string, totpCode: string],
  { success: boolean; error?: string }
>("login_and_sync");
const syncVault = callable<[], { success: boolean; error?: string }>("bw_sync");
const listItems = callable<[search: string], { success: boolean; items?: { id: string; name: string }[]; error?: string }>(
  "bw_list_items"
);
const getItem = callable<[id: string], { success: boolean; item?: { id: string; name: string; username?: string; password?: string; totp?: string; uris?: string[] }; error?: string }>(
  "bw_get_item"
);
const getStatus = callable<[], { success: boolean; status?: { status?: string; userEmail?: string }; error?: string }>(
  "bw_status"
);
const lockVault = callable<[], { success: boolean; error?: string }>("bw_lock");
const logoutVault = callable<[], { success: boolean; error?: string }>("bw_logout");

export function AuthPanel() {
  const [rememberPassword, setRememberPassword] = useState(false);
  const [rememberEmail, setRememberEmail] = useState(false);
  const [password, setPassword] = useState("");
  const [totpCode, setTotpCode] = useState("");
  const [email, setEmail] = useState("");
  const [useEuServer, setUseEuServer] = useState(false);
  const [saved, setSaved] = useState(false);
  const [savedEmail, setSavedEmail] = useState(false);
  const [statusText, setStatusText] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [items, setItems] = useState<{ id: string; name: string }[]>([]);
  const [selectedItem, setSelectedItem] = useState<string | null>(null);
  const [itemDetails, setItemDetails] = useState<{ username?: string; password?: string; totp?: string; uris?: string[] } | null>(null);
  const [busy, setBusy] = useState(false);

  const resetVaultState = () => {
    setItems([]);
    setSelectedItem(null);
    setItemDetails(null);
  };

  const statusLabel = (status: string) => {
    const normalized = status.toLowerCase();
    const icon = normalized === "unlocked" ? "🔓" : normalized === "locked" ? "🔒" : "⚠️";
    return `${icon} Vault status: ${status}`;
  };

  const refreshStatus = async () => {
    try {
      const result = await getStatus();
      if (result.success && result.status?.status) {
        const status = result.status.status;
        setStatusText(statusLabel(status));
        if (status.toLowerCase() !== "unlocked") {
          resetVaultState();
        }
      } else {
        setStatusText(null);
      }
    } catch {
      setStatusText(null);
    }
  };

  const shouldRefreshStatus = (error?: string) => {
    if (!error) return false;
    const normalized = error.toLowerCase();
    return normalized.includes("no active session") || normalized.includes("unauthenticated") || normalized.includes("locked");
  };

  useEffect(() => {
    let isMounted = true;
    getSavedPasswordStatus()
      .then((result) => {
        if (!isMounted) return;
        setSaved(Boolean(result.saved));
        setRememberPassword(Boolean(result.saved));
        if (result.password) {
          setPassword(result.password);
        }
      })
      .catch(() => {
        if (!isMounted) return;
        setSaved(false);
        setRememberPassword(false);
      });

    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    let isMounted = true;
    getSavedEmailStatus()
      .then((result) => {
        if (!isMounted) return;
        setSavedEmail(Boolean(result.saved));
        setRememberEmail(Boolean(result.saved));
        if (result.email) {
          setEmail(result.email);
        }
      })
      .catch(() => {
        if (!isMounted) return;
        setSavedEmail(false);
        setRememberEmail(false);
      });

    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    refreshStatus();
  }, []);

  const handleToggle = async (nextValue: boolean) => {
    setRememberPassword(nextValue);
    if (!nextValue) {
      const result = await clearSavedPassword();
      if (!result.success) {
        toaster.toast({
          title: "Error",
          body: result.error ?? "Failed to clear saved password",
        });
      }
      setSaved(false);
      setPassword("");
    }
  };

  const handleToggleEmail = async (nextValue: boolean) => {
    setRememberEmail(nextValue);
    if (!nextValue) {
      const result = await clearSavedEmail();
      if (!result.success) {
        toaster.toast({
          title: "Error",
          body: result.error ?? "Failed to clear saved email",
        });
      }
      setSavedEmail(false);
      setEmail("");
    }
  };

  const handleSave = async () => {
    if (!password.trim()) {
      toaster.toast({
        title: "Missing password",
        body: "Enter your password before saving.",
      });
      return;
    }

    const result = await savePassword(password);
    if (result.success) {
      setSaved(true);
      setPassword("");
      toaster.toast({
        title: "Password saved",
        body: "Saved on this device.",
      });
    } else {
      toaster.toast({
        title: "Error",
        body: result.error ?? "Failed to save password",
      });
    }
  };

  const handleLogin = async () => {
    setBusy(true);
    const server = useEuServer ? "eu" : "us";
    const result = await loginAndSync(email.trim(), password.trim(), server, totpCode.trim());
    setBusy(false);
    setTotpCode("");
    if (result.success) {
      if (rememberEmail && email.trim()) {
        const saveResult = await saveEmail(email.trim());
        if (saveResult.success) {
          setSavedEmail(true);
        } else {
          toaster.toast({
            title: "Email not saved",
            body: saveResult.error ?? "Failed to save email",
          });
        }
      }
      await refreshStatus();
      toaster.toast({
        title: "Login complete",
        body: "Session refreshed and synced.",
      });
    } else {
      toaster.toast({
        title: "Login failed",
        body: result.error ?? "Failed to login",
      });
      if (shouldRefreshStatus(result.error)) {
        await refreshStatus();
      }
    }
  };

  const handleSync = async () => {
    setBusy(true);
    const result = await syncVault();
    setBusy(false);
    if (result.success) {
      await refreshStatus();
      toaster.toast({
        title: "Synced",
        body: "Vault updated from server.",
      });
    } else {
      toaster.toast({
        title: "Sync failed",
        body: result.error ?? "Failed to sync",
      });
      if (shouldRefreshStatus(result.error)) {
        await refreshStatus();
      }
    }
  };

  const handleSearch = async () => {
    const query = searchQuery.trim();
    if (!query) {
      setItems([]);
      setSelectedItem(null);
      setItemDetails(null);
      return;
    }
    setBusy(true);
    const result = await listItems(query);
    setBusy(false);
    if (result.success) {
      setItems(result.items ?? []);
      setSelectedItem(null);
      setItemDetails(null);
    } else {
      toaster.toast({
        title: "Search failed",
        body: result.error ?? "Failed to search items",
      });
      if (shouldRefreshStatus(result.error)) {
        await refreshStatus();
      }
    }
  };

  const handleSelectItem = async (id: string) => {
    setSelectedItem(id);
    setBusy(true);
    const result = await getItem(id);
    setBusy(false);
    if (result.success && result.item) {
      setItemDetails({
        username: result.item.username,
        password: result.item.password,
        totp: result.item.totp,
        uris: result.item.uris,
      });
    } else {
      setItemDetails(null);
      toaster.toast({
        title: "Error",
        body: result.error ?? "Failed to load item",
      });
      if (shouldRefreshStatus(result.error)) {
        await refreshStatus();
      }
    }
  };

  const handleLock = async () => {
    setBusy(true);
    const result = await lockVault();
    setBusy(false);
    if (result.success) {
      resetVaultState();
      await refreshStatus();
      toaster.toast({
        title: "Vault locked",
        body: "Session cleared for this device.",
      });
    } else {
      toaster.toast({
        title: "Lock failed",
        body: result.error ?? "Failed to lock vault",
      });
      if (shouldRefreshStatus(result.error)) {
        await refreshStatus();
      }
    }
  };

  const handleLogout = async () => {
    const confirmed = await new Promise<boolean>((resolve) => {
      showModal(
        <ConfirmModal
          strTitle="Log out of Bitwarden?"
          strDescription="This will remove the session and all saved credentials from this device."
          strOKButtonText="Log out"
          strCancelButtonText="Cancel"
          onOK={() => resolve(true)}
          onCancel={() => resolve(false)}
        />
      );
    });
    if (!confirmed) {
      return;
    }
    setBusy(true);
    const result = await logoutVault();
    setBusy(false);
    if (result.success) {
      resetVaultState();
      setEmail("");
      setPassword("");
      setSaved(false);
      setSavedEmail(false);
      setRememberEmail(false);
      setRememberPassword(false);
      await refreshStatus();
      toaster.toast({
        title: "Logged out",
        body: "Credentials removed for this device.",
      });
    } else {
      toaster.toast({
        title: "Logout failed",
        body: result.error ?? "Failed to logout",
      });
      if (shouldRefreshStatus(result.error)) {
        await refreshStatus();
      }
    }
  };

  const handleCopy = async (value: string, label: string) => {
    if (!value) {
      toaster.toast({
        title: "Nothing to copy",
        body: `No ${label.toLowerCase()} available.`,
      });
      return;
    }

    const { success, verified } = await copyWithVerification(value);
    if (success) {
      toaster.toast({
        title: "Copied",
        body: verified ? `${label} copied to clipboard.` : `${label} copied (verification unavailable).`,
      });
    } else {
      toaster.toast({
        title: "Copy failed",
        body: `Unable to copy ${label.toLowerCase()}.`,
      });
    }
  };

  return (
    <>
      <ToggleField
        checked={rememberPassword}
        label="Remember password on this device (BW_PASSWORD env var)"
        onChange={(value) => handleToggle(Boolean(value))}
      />

      <TextField
        label="Bitwarden email"
        value={email}
        onChange={(event) => setEmail(event.target.value)}
      />

      <ToggleField
        checked={rememberEmail}
        label="Remember email on this device"
        onChange={(value) => handleToggleEmail(Boolean(value))}
      />

      <ToggleField
        checked={useEuServer}
        label="Use EU server (bitwarden.eu)"
        onChange={(value) => setUseEuServer(Boolean(value))}
      />

      <TextField
        label="Master password"
        description="Leave blank to use saved BW_PASSWORD. Needed to unlock your vault."
        bIsPassword={true}
        type="password"
        value={password}
        onChange={(event) => setPassword(event.target.value)}
      />

      <TextField
        label="2FA code (authenticator)"
        description="Optional. Only needed if your account requires 2FA on login."
        value={totpCode}
        onChange={(event) => setTotpCode(event.target.value)}
      />

      <ButtonItem layout="below" onClick={handleLogin} disabled={busy}>
        Login + Auto Sync
      </ButtonItem>
      <ButtonItem layout="below" onClick={handleSync} disabled={busy}>
        Sync now
      </ButtonItem>
      <ButtonItem layout="below" onClick={handleLock} disabled={busy}>
        Lock Vault
      </ButtonItem>
      <ButtonItem layout="below" onClick={handleLogout} disabled={busy}>
        Logout
      </ButtonItem>

      {statusText ? <Field label="Status" description={statusText} /> : null}

      {rememberPassword ? (
        <>
          <ButtonItem layout="below" onClick={handleSave}>
            Save password
          </ButtonItem>
          {saved ? (
            <Field label="Status" description="Saved to BW_PASSWORD for this device." />
          ) : null}
        </>
      ) : null}

      {rememberEmail && savedEmail ? (
        <Field label="Email" description="Saved to this device." />
      ) : null}

      <TextField
        label="Search vault items"
        description="Enter a search string to find login items."
        value={searchQuery}
        onChange={(event) => setSearchQuery(event.target.value)}
      />
      <ButtonItem layout="below" onClick={handleSearch} disabled={busy}>
        Search
      </ButtonItem>

      {items.length ? (
        <>
          {items.map((item) => (
            <ButtonItem key={item.id} layout="below" onClick={() => handleSelectItem(item.id)}>
              {item.name}
            </ButtonItem>
          ))}
        </>
      ) : null}

      {selectedItem && itemDetails ? (
        <>
          {itemDetails.username ? (
            <>
              <Field label="Username" description={itemDetails.username} />
              <ButtonItem
                layout="below"
                onClick={() => handleCopy(itemDetails.username ?? "", "Username")}
                disabled={busy}
              >
                Copy username
              </ButtonItem>
            </>
          ) : null}
          {itemDetails.password ? (
            <>
              <Field label="Password" description={itemDetails.password} />
              <ButtonItem
                layout="below"
                onClick={() => handleCopy(itemDetails.password ?? "", "Password")}
                disabled={busy}
              >
                Copy password
              </ButtonItem>
            </>
          ) : null}
          {itemDetails.totp ? (
            <>
              <Field label="TOTP" description={itemDetails.totp} />
              <ButtonItem
                layout="below"
                onClick={() => handleCopy(itemDetails.totp ?? "", "TOTP")}
                disabled={busy}
              >
                Copy TOTP
              </ButtonItem>
            </>
          ) : null}
          {itemDetails.uris?.length ? (
            <>
              {itemDetails.uris.map((uri, index) => (
                <div key={`${uri}-${index}`}>
                  <Field label={`URL ${index + 1}`} description={uri} />
                  <ButtonItem
                    layout="below"
                    onClick={() => handleCopy(uri, `URL ${index + 1}`)}
                    disabled={busy}
                  >
                    {`Copy URL ${index + 1}`}
                  </ButtonItem>
                </div>
              ))}
            </>
          ) : null}
        </>
      ) : null}
    </>
  );
}
