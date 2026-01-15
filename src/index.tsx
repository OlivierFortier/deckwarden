import {
  ButtonItem,
  Dropdown,
  Field,
  PanelSection,
  PanelSectionRow,
  TextField,
  ToggleField,
  staticClasses
} from "@decky/ui";
import {
  addEventListener,
  callable,
  removeEventListener,
  definePlugin,
  toaster,
  // routerHook
} from "@decky/api"
import { FaShip } from "react-icons/fa";
import { InstallButton } from "./InstallButton";
import { useState } from "react";

type BwServeResponse = {
  success: boolean;
  pid?: number;
  port?: number;
  hostname?: string;
  status?: string;
  error?: string;
};

type BwHttpResponse = {
  success: boolean;
  status?: number;
  statusText?: string;
  body?: string;
  error?: string;
  url?: string;
};

const bwServe = callable<[number, string, boolean], BwServeResponse>("bw_serve");
const bwHttpRequest = callable<
  [string, string, number, string, string | null],
  BwHttpResponse
>("bw_http_request");
const DeckyButtonItem = ButtonItem;


function Content() {
  const [hostname, setHostname] = useState("localhost");
  const [port, setPort] = useState("8087");
  const [disableOriginProtection, setDisableOriginProtection] = useState(true);
  const [serveStatus, setServeStatus] = useState<string>("stopped");
  const [serveError, setServeError] = useState<string>("");
  const [apiPath, setApiPath] = useState("/status");
  const [apiMethod, setApiMethod] = useState("GET");
  const [apiBody, setApiBody] = useState("");
  const [apiResponse, setApiResponse] = useState("");
  const [busy, setBusy] = useState(false);

  const apiMethodOptions = [
    { data: "GET", label: "GET" },
    { data: "POST", label: "POST" },
    { data: "PUT", label: "PUT" },
    { data: "PATCH", label: "PATCH" },
    { data: "DELETE", label: "DELETE" },
  ];
  const selectedApiMethodOption =
    apiMethodOptions.find((option) => option.data === apiMethod) ?? apiMethodOptions[0];

  const normalizePath = (value: string) => (value.startsWith("/") ? value : `/${value}`);

  const startServe = async () => {
    if (busy) return;
    const parsedPort = Number(port);
    if (!Number.isInteger(parsedPort) || parsedPort <= 0) {
      toaster.toast({
        title: "Invalid port",
        body: "Port must be a positive integer.",
      });
      return;
    }

    try {
      setBusy(true);
      setServeError("");
      const result = await bwServe(parsedPort, hostname, disableOriginProtection);
      if (result.success) {
        setServeStatus(result.status ?? "running");
        toaster.toast({
          title: "Bitwarden API started",
          body: `Listening on ${result.hostname ?? hostname}:${result.port ?? parsedPort}`,
        });
      } else {
        setServeStatus("error");
        setServeError(result.error ?? "Unknown error");
        toaster.toast({
          title: "Failed to start API",
          body: result.error ?? "Unknown error",
        });
      }
    } catch (error) {
      setServeStatus("error");
      setServeError(String(error));
      toaster.toast({
        title: "Failed to start API",
        body: String(error),
      });
    } finally {
      setBusy(false);
    }
  };

  const callApi = async () => {
    if (busy) return;
    const parsedPort = Number(port);
    if (!Number.isInteger(parsedPort) || parsedPort <= 0) {
      toaster.toast({
        title: "Invalid port",
        body: "Port must be a positive integer.",
      });
      return;
    }

    try {
      setBusy(true);
      const result = await bwHttpRequest(
        apiMethod,
        hostname,
        parsedPort,
        normalizePath(apiPath),
        apiBody.trim() ? apiBody : null
      );
      const text = result.body ?? "";
      let formatted = text;
      try {
        formatted = JSON.stringify(JSON.parse(text), null, 2);
      } catch {
        // keep raw text
      }
      setApiResponse(formatted);
      toaster.toast({
        title: result.success ? "API request complete" : "API request failed",
        body: result.status
          ? `${result.status} ${result.statusText ?? ""}`.trim()
          : result.error ?? "Request failed",
      });
    } catch (error) {
      setApiResponse(String(error));
      toaster.toast({
        title: "API request error",
        body: String(error),
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <PanelSection title="Bitwarden CLI">
      <PanelSectionRow>
        <InstallButton/>
      </PanelSectionRow>

      <PanelSectionRow>
        <div style={{ display: "grid", gap: "8px", width: "100%" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px" }}>
            <TextField
              label="Hostname"
              value={hostname}
              description="e.g. localhost"
              onChange={(event) => setHostname(event.target.value)}
            />
            <TextField
              label="Port"
              value={port}
              description="1-65535"
              mustBeNumeric
              rangeMin={1}
              onChange={(event) => setPort(event.target.value)}
            />
          </div>
          <ToggleField
            label="Disable origin protection (required for UI requests)"
            checked={disableOriginProtection}
            onChange={setDisableOriginProtection}
          />
          <DeckyButtonItem layout="below" onClick={startServe} disabled={busy}>
            Start Bitwarden API (bw serve)
          </DeckyButtonItem>
          <div style={{ fontSize: "0.85rem", opacity: 0.8 }}>
            Status: {serveStatus}
          </div>
          {serveError ? (
            <div style={{ fontSize: "0.85rem", color: "#f55" }}>
              Error: {serveError}
            </div>
          ) : null}
        </div>
      </PanelSectionRow>

      <PanelSectionRow>
        <div style={{ display: "grid", gap: "8px", width: "100%" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px" }}>
            <Field label="Method">
              <Dropdown
                rgOptions={apiMethodOptions}
                selectedOption={selectedApiMethodOption}
                onChange={(option) => setApiMethod(option.data)}
              />
            </Field>
            <TextField
              label="Path"
              value={apiPath}
              description="e.g. /status"
              onChange={(event) => setApiPath(event.target.value)}
            />
          </div>
          <TextField
            label="JSON body (optional)"
            value={apiBody}
            onChange={(event) => setApiBody(event.target.value)}
            bShowClearAction
          />
          <DeckyButtonItem layout="below" onClick={callApi} disabled={busy}>
            Call API
          </DeckyButtonItem>
          <TextField
            label="Response"
            value={apiResponse}
            disabled
            bShowCopyAction
          />
        </div>
      </PanelSectionRow>

      {/* <PanelSectionRow>
        <div style={{ display: "flex", justifyContent: "center" }}>
          <img src={logo} />
        </div>
      </PanelSectionRow> */}

      {/*<PanelSectionRow>
        <ButtonItem
          layout="below"
          onClick={() => {
            Navigation.Navigate("/decky-plugin-test");
            Navigation.CloseSideMenus();
          }}
        >
          Router
        </ButtonItem>
      </PanelSectionRow>*/}
    </PanelSection>
  );
};

export default definePlugin(() => {
  console.log("Template plugin initializing, this is called once on frontend startup")

  // serverApi.routerHook.addRoute("/decky-plugin-test", DeckyPluginRouterTest, {
  //   exact: true,
  // });

  // Add an event listener to the "timer_event" event from the backend
  const listener = addEventListener<[
    test1: string,
    test2: boolean,
    test3: number
  ]>("timer_event", (test1, test2, test3) => {
    console.log("Template got timer_event with:", test1, test2, test3)
    toaster.toast({
      title: "template got timer_event",
      body: `${test1}, ${test2}, ${test3}`
    });
  });

  return {
    // The name shown in various decky menus
    name: "Test Plugin",
    // The element displayed at the top of your plugin's menu
    titleView: <div className={staticClasses.Title}>Decky Example Plugin</div>,
    // The content of your plugin's menu
    content: <Content />,
    // The icon displayed in the plugin list
    icon: <FaShip />,
    // The function triggered when your plugin unloads
    onDismount() {
      console.log("Unloading")
      removeEventListener("timer_event", listener);
      // serverApi.routerHook.removeRoute("/decky-plugin-test");
    },
  };
});
