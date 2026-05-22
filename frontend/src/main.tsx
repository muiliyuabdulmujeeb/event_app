import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";

import { AppErrorScreen } from "./components/AppErrorScreen";
import { validateAppEnv } from "./config/env";
import "./styles.css";

const container = document.getElementById("root");

if (!container) {
  throw new Error("The frontend root container could not be found.");
}

const root = ReactDOM.createRoot(container);

void bootstrap();

async function bootstrap() {
  const envValidation = validateAppEnv();

  if (!envValidation.success) {
    root.render(
      <React.StrictMode>
        <AppErrorScreen
          title="Frontend configuration is incomplete"
          message={envValidation.message}
          issues={envValidation.issues}
        />
      </React.StrictMode>,
    );
    return;
  }

  try {
    const [{ default: App }, { queryClient }] = await Promise.all([
      import("./App"),
      import("./lib/queryClient"),
    ]);

    root.render(
      <React.StrictMode>
        <QueryClientProvider client={queryClient}>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </QueryClientProvider>
      </React.StrictMode>,
    );
  } catch (error) {
    const details =
      error instanceof Error && error.message
        ? [error.message]
        : ["Unknown frontend startup failure."];

    root.render(
      <React.StrictMode>
        <AppErrorScreen
          title="Frontend startup failed"
          message="The app could not finish loading. Review the validation details below, then restart the frontend."
          issues={details}
        />
      </React.StrictMode>,
    );
  }
}
