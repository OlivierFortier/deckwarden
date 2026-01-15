import { useEffect, useState } from "react";
import { callable, toaster } from "@decky/api";
import { ButtonItem, Field, TextField, ToggleField } from "@decky/ui";

const getSavedPasswordStatus = callable<[], { saved: boolean }>("get_saved_password_status");
const savePassword = callable<[password: string], { success: boolean; error?: string }>("save_password");
const clearSavedPassword = callable<[], { success: boolean; error?: string }>("clear_saved_password");
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

export function AuthPanel() {
  const [rememberPassword, setRememberPassword] = useState(false);
  const [password, setPassword] = useState("");
  const [totpCode, setTotpCode] = useState("");
  const [email, setEmail] = useState("");
  const [useEuServer, setUseEuServer] = useState(false);
  const [saved, setSaved] = useState(false);
  const [statusText, setStatusText] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [items, setItems] = useState<{ id: string; name: string }[]>([]);
  const [selectedItem, setSelectedItem] = useState<string | null>(null);
  const [itemDetails, setItemDetails] = useState<{ username?: string; password?: string; totp?: string; uris?: string[] } | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let isMounted = true;
    getSavedPasswordStatus()
      .then((result) => {
        if (!isMounted) return;
        setSaved(Boolean(result.saved));
        setRememberPassword(Boolean(result.saved));
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
    getStatus()
      .then((result) => {
        if (!isMounted) return;
        if (result.success && result.status?.status) {
          setStatusText(`Vault status: ${result.status.status}`);
        }
      })
      .catch(() => {
        if (!isMounted) return;
        setStatusText(null);
      });
    return () => {
      isMounted = false;
    };
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
      setStatusText("Vault unlocked and synced.");
      toaster.toast({
        title: "Login complete",
        body: "Session refreshed and synced.",
      });
    } else {
      toaster.toast({
        title: "Login failed",
        body: result.error ?? "Failed to login",
      });
    }
  };

  const handleSync = async () => {
    setBusy(true);
    const result = await syncVault();
    setBusy(false);
    if (result.success) {
      setStatusText("Vault synced.");
      toaster.toast({
        title: "Synced",
        body: "Vault updated from server.",
      });
    } else {
      toaster.toast({
        title: "Sync failed",
        body: result.error ?? "Failed to sync",
      });
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
        checked={useEuServer}
        label="Use EU server (bitwarden.eu)"
        onChange={(value) => setUseEuServer(Boolean(value))}
      />

      <TextField
        label="Master password"
        description="Leave blank to use saved BW_PASSWORD. Needed to unlock your vault."
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
            <Field label="Username" description={itemDetails.username} />
          ) : null}
          {itemDetails.password ? (
            <Field label="Password" description={itemDetails.password} />
          ) : null}
          {itemDetails.totp ? (
            <Field label="TOTP" description={itemDetails.totp} />
          ) : null}
          {itemDetails.uris?.length ? (
            <Field label="URLs" description={itemDetails.uris.join("\n")} />
          ) : null}
        </>
      ) : null}
    </>
  );
}
