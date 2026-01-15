import {
    callable,
    toaster
} from "@decky/api"
import { ButtonItem } from "@decky/ui";

const installBwCli = callable<[], { success: boolean; path?: string; error?: string }>("install_bw_cli");

export function InstallButton() {

    return <ButtonItem layout="below" onClick={async () => {
        const result = await installBwCli();
        toaster.toast({
            title: result.success ? "Success" : "Error",
            body: result.success ? `Installed: ${result.path}` : result.error
        });
    }}>
        Install Bitwarden CLI
    </ButtonItem>
}