export async function copyToClipboard(text: string): Promise<boolean> {
  if (!text) {
    return false;
  }

  if (navigator?.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // Fall through to legacy copy path.
    }
  }

  const textArea = document.createElement("textarea");
  textArea.value = text;
  textArea.style.position = "fixed";
  textArea.style.top = "-1000px";
  textArea.style.opacity = "0";
  textArea.setAttribute("readonly", "true");
  document.body.appendChild(textArea);

  try {
    textArea.focus();
    textArea.select();
    return Boolean(document.execCommand("copy"));
  } catch {
    return false;
  } finally {
    document.body.removeChild(textArea);
  }
}

export async function verifyCopy(expectedText: string): Promise<boolean> {
  try {
    if (!navigator?.clipboard?.readText) {
      return true;
    }
    const readBack = await navigator.clipboard.readText();
    return readBack === expectedText;
  } catch {
    return true;
  }
}

export async function copyWithVerification(text: string): Promise<{ success: boolean; verified: boolean }> {
  const success = await copyToClipboard(text);
  if (!success) {
    return { success: false, verified: false };
  }
  const verified = await verifyCopy(text);
  return { success, verified };
}
