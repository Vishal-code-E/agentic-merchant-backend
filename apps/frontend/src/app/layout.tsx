import "./globals.css";
import { MerchantProvider } from "../lib/merchant-context";
import { Nav } from "./nav";

export const metadata = {
  title: "Agentic Merchant Dashboard",
  description: "Merchant onboarding, catalog, policies, and observability for the Razorpay Agentic Merchant Backend.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <MerchantProvider>
          <Nav />
          {children}
        </MerchantProvider>
      </body>
    </html>
  );
}
