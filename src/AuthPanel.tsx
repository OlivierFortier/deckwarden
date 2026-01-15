import { useEffect, useState } from "react";
import { callable, toaster } from "@decky/api";
import { ButtonItem, Field, TextField, ToggleField } from "@decky/ui";

const getSavedPasswordStatus = callable<[], { saved: boolean }>("get_saved_password_status");
const savePassword = callable<[password: string], { success: boolean; error?: string }>("save_password");
const clearSavedPassword = callable<[], { success: boolean; error?: string }>("clear_saved_password");

export function AuthPanel() {
  const [rememberPassword, setRememberPassword] = useState(false);
  const [password, setPassword] = useState("");
  const [saved, setSaved] = useState(false);

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

  return (
    <>
      <ToggleField
        checked={rememberPassword}
        label="Remember password on this device (BW_PASSWORD env var)"
        onChange={(value) => handleToggle(Boolean(value))}
      />

      {rememberPassword ? (
        <>
          <TextField
            label="Master password"
            description="Stored in the BW_PASSWORD environment variable for the Bitwarden CLI."
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          <ButtonItem layout="below" onClick={handleSave}>
            Save password
          </ButtonItem>
          {saved ? (
            <Field label="Status" description="Saved to BW_PASSWORD for this device." />
          ) : null}
        </>
      ) : null}
    </>
  );
}
