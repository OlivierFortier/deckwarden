import {
    callable,
    toaster
} from "@decky/api"
import { ButtonItem } from "@decky/ui";

const installBitwardenCli = callable<[], { success: boolean; error?: string }>("extract_bw_zip");

export function InstallButton() {

    return <ButtonItem layout="below" onClick={async () => {
        const result = await installBitwardenCli();
        toaster.toast({
            title: result.success ? "Success" : "Error",
            body: result.success ? "Bitwarden CLI installed." : result.error
        });
    }}>
        Install Bitwarden CLI
    </ButtonItem>
}