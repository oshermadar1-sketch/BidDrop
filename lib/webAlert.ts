// lib/webAlert.ts
// On web, react-native-web's Alert.alert does nothing, so errors and confirmations were
// silently dropped. Route them to the browser's alert/confirm dialogs instead.
import { Alert, Platform, type AlertButton } from "react-native";

if (Platform.OS === "web" && typeof window !== "undefined") {
  Alert.alert = (title?: string, message?: string, buttons?: AlertButton[]) => {
    const text = [title, message].filter(Boolean).join("\n\n");
    const list = buttons ?? [];

    if (list.length <= 1) {
      window.alert(text);
      list[0]?.onPress?.();
      return;
    }

    // Two or more buttons: OK runs the main (non-cancel) action, Cancel runs the cancel one.
    const cancel = list.find((b) => b.style === "cancel");
    const main =
      [...list].reverse().find((b) => b.style !== "cancel") ??
      list[list.length - 1];
    if (window.confirm(text)) main.onPress?.();
    else cancel?.onPress?.();
  };
}
