import "#instrumentation.ts"; // Set up Sentry

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { captureMessage, reactErrorHandler, setUser } from "@sentry/react";

import "@fontsource/roboto/300.css";
import "@fontsource/roboto/400.css";
import "@fontsource/roboto/500.css";
import "@fontsource/roboto/700.css";

import { getOrSetUserId } from "#helpers/userId.ts";

const userId = getOrSetUserId(); // Ensure a user ID is set

// Set the user in Sentry
setUser({
    id: userId,
});

import App from "./App.tsx";

const root = document.getElementById("root");

if (!root) {
    captureMessage("Root element not found", {
        level: "fatal",
    });
    throw new Error("Root element not found");
}

createRoot(root, {
    // Callback called when an error is thrown and not caught by an ErrorBoundary.
    onUncaughtError: reactErrorHandler((error, errorInfo) => {
        console.warn("Uncaught error", error, errorInfo.componentStack);
    }),
    // Callback called when React catches an error in an ErrorBoundary.
    onCaughtError: reactErrorHandler(),
    // Callback called when React automatically recovers from errors.
    onRecoverableError: reactErrorHandler(),
}).render(
    <StrictMode>
        <App />
    </StrictMode>,
);
