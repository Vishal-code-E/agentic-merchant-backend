import { IBM_Plex_Sans, Space_Grotesk } from "next/font/google";
import "./globals.css";
import { MerchantProvider } from "../lib/merchant-context";
import { Sidebar } from "./sidebar";
import { ComplianceBanner } from "./components/compliance-banner";

// Self-hosted by Next at build time — no runtime CDN request. Space Grotesk
// carries headings/buttons/brand (display); Plex Sans carries body/forms/tables.
const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  variable: "--font-display",
  display: "swap",
});

const plexSans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-body",
  display: "swap",
});

export const metadata = {
  title: "Agentic Merchant Dashboard",
  description:
    "Onboard a Razorpay merchant, publish its catalog, set checkout guardrails, and watch AI agents transact against them — with a full audit trail.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${spaceGrotesk.variable} ${plexSans.variable}`}>
      <body>
        <MerchantProvider>
          <div className="app-shell">
            <Sidebar />
            <div className="app-main">
              <ComplianceBanner />
              {children}
            </div>
          </div>
        </MerchantProvider>
      </body>
    </html>
  );
}
