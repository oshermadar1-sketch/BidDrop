// app/+html.tsx
// The HTML shell of the web export. Besides the usual viewport it declares the page as an
// installable web app: on iPhone, "Add to Home Screen" in Safari then gives BidDrop an
// icon, a title and a full-screen window without the browser bars. The icons and the
// manifest live in /public and are copied to the site root by `expo export`.
import { ScrollViewStyleReset } from "expo-router/html";
import type { PropsWithChildren } from "react";

export default function Root({ children }: PropsWithChildren) {
  return (
    <html lang="he">
      <head>
        <meta charSet="utf-8" />
        <meta httpEquiv="X-UA-Compatible" content="IE=edge" />
        <meta
          name="viewport"
          content="width=device-width, initial-scale=1, shrink-to-fit=no, viewport-fit=cover"
        />
        <title>BidDrop</title>
        <meta name="application-name" content="BidDrop" />
        <meta name="theme-color" content="#9bac70" />

        {/* iOS home-screen web app */}
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-title" content="BidDrop" />
        <meta name="apple-mobile-web-app-status-bar-style" content="default" />
        <link rel="apple-touch-icon" href="/apple-touch-icon.png" />

        {/* Android / Chrome */}
        <meta name="mobile-web-app-capable" content="yes" />
        <link rel="manifest" href="/manifest.json" />
        <link rel="icon" type="image/png" sizes="192x192" href="/icon-192.png" />

        <ScrollViewStyleReset />
        <style dangerouslySetInnerHTML={{ __html: "html, body { background: #ffffff; }" }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
