import {
  PanelSection,
  PanelSectionRow,
  staticClasses
} from "@decky/ui";
import {
  addEventListener,
  removeEventListener,
  definePlugin,
  toaster,
  // routerHook
} from "@decky/api"
import { FaShip } from "react-icons/fa";
import { InstallButton } from "./ExampleDeckyComponent";

function Content() {
  return (
    <PanelSection title="Deckwarden">
      <PanelSectionRow>
        <InstallButton/>
      </PanelSectionRow>
    </PanelSection>
  );
};

export default definePlugin(() => {
  console.log("Template plugin initializing, this is called once on frontend startup")

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
    name: "Deckwarden",
    // The element displayed at the top of your plugin's menu
    titleView: <div className={staticClasses.Title}>Deckwarden</div>,
    // The content of your plugin's menu
    content: <Content />,
    // The icon displayed in the plugin list
    icon: <FaShip />,
    // The function triggered when your plugin unloads
    onDismount() {
      console.log("Unloading Deckwarden")
      removeEventListener("timer_event", listener);
    },
  };
});
