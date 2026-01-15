import {
    callable,
    toaster
} from "@decky/api"
import { ButtonItem } from "@decky/ui";

const callFunctionFromBackend = callable<[], { success: boolean; path?: string; error?: string }>("my_backend_function");

export function InstallButton() {

    return <ButtonItem layout="below" onClick={async () => {
        const result = await callFunctionFromBackend();
        toaster.toast({
            title: result.success ? "Success" : "Error",
            body: result.success ? `Installed: ${result.path}` : result.error
        });
    }}>
        Install Bitwarden CLI
    </ButtonItem>
}